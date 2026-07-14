import os
import sys
import subprocess
import threading
import queue
import re
import json
import time
import shutil
import tempfile

# Windows-specific flag to prevent cmd console windows from spawning
CREATE_NO_WINDOW = 0x08000000

# Processing engine modes. AUTO resolves to the best real mode at encode time.
ENGINE_CPU = "cpu"
ENGINE_GPU = "gpu"
ENGINE_HYBRID = "hybrid"
ENGINE_AUTO = "auto"
ENGINES = (ENGINE_CPU, ENGINE_GPU, ENGINE_HYBRID, ENGINE_AUTO)

# ETA smoothing: exponential moving average factor and gating thresholds.
# ETA is hidden ("Estimating...") until the pass has enough signal to be honest.
ETA_EMA_ALPHA = 0.15
ETA_MIN_PASS_PROGRESS = 5.0   # percent of the current pass
ETA_MIN_SAMPLE_SECONDS = 10.0  # wall seconds of samples in the current pass

# Predefined presets optimized for WebM outputs only (libvpx-vp9 and libsvtav1).
# Names are user-facing: task first, codec/resolution second. app.py logic keys
# off the "AV1" and "Audio Only" substrings - keep those stable when renaming.
PRESETS = {
    "LMS Upload - VP9 1080p (Recommended)": {
        "codec": "libvpx-vp9",
        "args": ["-crf", "32", "-b:v", "0", "-deadline", "good", "-cpu-used", "2", "-row-mt", "1", "-tile-columns", "2", "-threads", "16", "-lag-in-frames", "25", "-auto-alt-ref", "1"],
        "audio_args": ["-c:a", "libopus", "-b:a", "96k"],
        "resolution": None,
        "extension": ".webm"
    },
    "High Quality - VP9 1080p": {
        "codec": "libvpx-vp9",
        "args": ["-crf", "22", "-b:v", "0", "-deadline", "good", "-cpu-used", "2", "-row-mt", "1", "-tile-columns", "2", "-threads", "16", "-lag-in-frames", "25", "-auto-alt-ref", "1"],
        "audio_args": ["-c:a", "libopus", "-b:a", "128k"],
        "resolution": None,
        "extension": ".webm"
    },
    "Balanced - VP9 1080p": {
        "codec": "libvpx-vp9",
        "args": ["-crf", "30", "-b:v", "0", "-deadline", "good", "-cpu-used", "2", "-row-mt", "1", "-tile-columns", "2", "-threads", "16", "-lag-in-frames", "25", "-auto-alt-ref", "1"],
        "audio_args": ["-c:a", "libopus", "-b:a", "96k"],
        "resolution": None,
        "extension": ".webm"
    },
    "Small Size - VP9 720p": {
        "codec": "libvpx-vp9",
        "args": ["-crf", "38", "-b:v", "0", "-deadline", "good", "-cpu-used", "2", "-row-mt", "1", "-tile-columns", "2", "-threads", "16", "-lag-in-frames", "25", "-auto-alt-ref", "1"],
        "audio_args": ["-c:a", "libopus", "-b:a", "64k"],
        "resolution": (1280, 720),
        "extension": ".webm"
    },
    "Ultra Small - VP9 720p (Slow Internet)": {
        "codec": "libvpx-vp9",
        "args": ["-crf", "42", "-b:v", "0", "-deadline", "good", "-cpu-used", "2", "-row-mt", "1", "-tile-columns", "2", "-threads", "16", "-lag-in-frames", "25", "-auto-alt-ref", "1"],
        "audio_args": ["-c:a", "libopus", "-b:a", "64k"],
        "resolution": (1280, 720),
        "extension": ".webm"
    },
    "Experimental AV1 - 1080p (Smallest, Slower)": {
        "codec": "libsvtav1",
        "args": ["-crf", "32", "-preset", "8", "-g", "240"],
        "audio_args": ["-c:a", "libopus", "-b:a", "96k"],
        "resolution": None,
        "extension": ".webm"
    },
    "Audio Only - Opus (No Video)": {
        "codec": None,
        "args": ["-vn"],
        "audio_args": ["-c:a", "libopus", "-b:a", "64k"],
        "resolution": None,
        "extension": ".webm"
    }
}

# The audio-only preset name is referenced across the UI - single source of truth.
AUDIO_ONLY_PRESET = "Audio Only - Opus (No Video)"


def estimate_typical_output_bitrate(preset_name, crf=None, src_height=1080):
    """
    Rough expected output bitrate (bps) for a preset on film-like content.
    Used to warn when the input is already compressed below what the preset
    will produce (re-encoding such files usually makes them LARGER).
    Anchor: measured on this app's own presets - VP9 CRF 32 produced
    3.1 Mbps on 1920x800 film (Tears of Steel), i.e. ~4.5 Mbps at 1080p.
    Rate roughly halves per +6 CRF and scales superlinearly with height.
    """
    preset = PRESETS.get(preset_name)
    if not preset or preset["codec"] is None:
        return 0
    base_crf = 32
    if "-crf" in preset["args"]:
        base_crf = int(preset["args"][preset["args"].index("-crf") + 1])
    eff_crf = crf if crf is not None else base_crf
    out_h = preset["resolution"][1] if preset["resolution"] else min(src_height or 1080, 1080)
    rate = 4_500_000 * (out_h / 1080.0) ** 1.4 * (2 ** ((32 - eff_crf) / 6.0))
    if preset["codec"] == "libsvtav1":
        rate *= 0.75  # AV1 needs fewer bits for the same quality
    return int(rate)


def get_ffmpeg_path():
    """
    Finds the absolute path of ffmpeg. Handles Windows and macOS.
    If running inside a PyInstaller frozen application, uses the executable folder.
    """
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        
    ext = ".exe" if sys.platform == "win32" else ""
    local_ffmpeg = os.path.join(app_dir, f"ffmpeg{ext}")
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    if sys.platform == "darwin":
        paths = ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]
        for p in paths:
            if os.path.exists(p):
                return p

    return "ffmpeg"

def get_ffprobe_path():
    """
    Finds the absolute path of ffprobe.
    If running inside a PyInstaller frozen application, uses the executable folder.
    """
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        
    ext = ".exe" if sys.platform == "win32" else ""
    local_ffprobe = os.path.join(app_dir, f"ffprobe{ext}")
    if os.path.exists(local_ffprobe):
        return local_ffprobe

    system_ffprobe = shutil.which("ffprobe")
    if system_ffprobe:
        return system_ffprobe

    if sys.platform == "darwin":
        paths = ["/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe", "/usr/bin/ffprobe"]
        for p in paths:
            if os.path.exists(p):
                return p

    return "ffprobe"

def detect_hardware_encoders():
    """
    Returns generic hardware encoders compiled in FFmpeg.
    """
    encoders = {
        "nvenc": False,
        "qsv": False,
        "amf": False,
        "videotoolbox": False
    }
    try:
        ffmpeg_bin = get_ffmpeg_path()
        out = subprocess.check_output(
            [ffmpeg_bin, "-encoders"],
            creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0,
            stderr=subprocess.STDOUT
        ).decode("utf-8", errors="ignore")
        
        if "nvenc" in out:
            encoders["nvenc"] = True
        if "qsv" in out:
            encoders["qsv"] = True
        if "amf" in out:
            encoders["amf"] = True
        if "videotoolbox" in out:
            encoders["videotoolbox"] = True
    except Exception as e:
        print(f"Error detecting hardware encoders: {e}")
    return encoders

# Hardware / Hybrid Constants
HYBRID_MIN_HEIGHT = 1080

HW_PARAMS = {
    "cuda": {
        "accel_args": ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"],
        "scaler": "scale_cuda",
        "download_filter": "hwdownload,format=nv12,format=yuv420p"
    },
    "qsv": {
        "accel_args": ["-hwaccel", "qsv", "-hwaccel_output_format", "qsv"],
        "scaler": "scale_qsv",
        "download_filter": "hwdownload,format=nv12,format=yuv420p"
    },
    "d3d11va": {
        "accel_args": ["-hwaccel", "d3d11va", "-hwaccel_output_format", "d3d11"],
        "scaler": None,
        "download_filter": "hwdownload,format=nv12,format=yuv420p"
    },
    "vaapi": {
        "accel_args": ["-hwaccel", "vaapi", "-hwaccel_output_format", "vaapi"],
        "scaler": "scale_vaapi",
        "download_filter": "hwdownload,format=nv12,format=yuv420p"
    }
}

_cached_hardware_encoders = None

def detect_active_hardware_webm_encoders():
    """
    Checks which GPU WebM hardware encoders are supported by the active graphics card
    by running a tiny test conversion. Caches the result to prevent redundant checks.
    """
    global _cached_hardware_encoders
    if _cached_hardware_encoders is not None:
        return _cached_hardware_encoders

    ffmpeg_bin = get_ffmpeg_path()
    supported = {
        "av1_nvenc": False,
        "av1_qsv": False,
        "vp9_qsv": False,
        "av1_amf": False,
        "vp9_videotoolbox": False,
        "av1_videotoolbox": False
    }
    
    try:
        out = subprocess.check_output(
            [ffmpeg_bin, "-encoders"],
            creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0,
            stderr=subprocess.STDOUT
        ).decode("utf-8", errors="ignore")
    except Exception:
        return supported

    for enc in list(supported.keys()):
        if enc in out:
            cmd = [
                ffmpeg_bin, "-y", 
                "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1",
                "-vframes", "1",
                "-c:v", enc, 
                "-f", "null", "-"
            ]
            try:
                res = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    timeout=10.0
                )
                stderr_output = res.stderr.decode("utf-8", errors="ignore")
                if res.returncode == 0:
                    unsupported_phrases = ["no capable devices", "cannot load", "failed to create", "driver not found", "not supported"]
                    if not any(p in stderr_output.lower() for p in unsupported_phrases):
                        supported[enc] = True
            except Exception:
                pass
                
    _cached_hardware_encoders = supported
    return supported

# Decode-probe results cached per (accelerator, source codec): the first probe
# pays the cold GPU/driver init cost once, later files with the same codec skip it.
_decode_probe_cache = {}

def probe_hw_decode(input_path, accel_name, codec_name=None):
    """
    Probes if the input file can be decoded using a specific hardware accelerator
    (e.g. cuda, qsv, d3d11va). First run uses a LONG timeout: on Linux the first
    CUDA context creation alone can take several seconds (cold driver init), and
    the old 4s timeout caused false "no GPU" fallbacks on Ubuntu.
    """
    if not os.path.exists(input_path):
        return False
    cache_key = (accel_name, codec_name) if codec_name else None
    if cache_key and cache_key in _decode_probe_cache:
        return _decode_probe_cache[cache_key]

    ffmpeg_bin = get_ffmpeg_path()
    cmd = [
        ffmpeg_bin, "-y",
        "-hwaccel", accel_name,
        "-i", input_path,
        "-vframes", "10",
        "-f", "null", "-"
    ]
    # 20s for the first-ever probe of this accel, 8s once it has warmed up
    warmed = any(k[0] == accel_name for k in _decode_probe_cache)
    timeout = 8.0 if warmed else 20.0
    result = False
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0,
            timeout=timeout
        )
        stderr_output = res.stderr.decode("utf-8", errors="ignore").lower()
        if res.returncode == 0:
            unsupported_phrases = [
                "failed to start", "cannot load", "no hardware",
                "device not found", "error initialize", "failed to setup",
                "failed setup for format", "device creation failed",
                "hardware device setup failed", "no device available"
            ]
            if not any(p in stderr_output for p in unsupported_phrases):
                result = True
    except Exception:
        result = False
    if cache_key:
        _decode_probe_cache[cache_key] = result
    return result

def detect_supported_decode_accel(input_path, codec_name=None):
    """
    Returns the first hardware accelerator (from ['cuda', 'qsv', 'd3d11va'])
    that can successfully decode the input file. Returns None if none are supported.
    """
    accels = ["cuda", "qsv", "d3d11va"] if os.name == 'nt' else ["cuda", "vaapi", "qsv"]
    for accel in accels:
        if probe_hw_decode(input_path, accel, codec_name):
            return accel
    return None

_hw_decode_available_cache = None

def is_hw_decode_available():
    """
    Checks if any hardware decoding accelerator (cuda, qsv, d3d11va / vaapi) is
    available on the system. Uses a short lavfi source; result is cached.
    """
    global _hw_decode_available_cache
    if _hw_decode_available_cache is not None:
        return _hw_decode_available_cache
    ffmpeg_bin = get_ffmpeg_path()
    accels = ["cuda", "qsv", "d3d11va"] if os.name == 'nt' else ["cuda", "vaapi", "qsv"]
    found = False
    for accel in accels:
        cmd = [
            ffmpeg_bin, "-y",
            "-hwaccel", accel,
            "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1",
            "-vframes", "1",
            "-f", "null", "-"
        ]
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0,
                timeout=15.0
            )
            if res.returncode == 0:
                found = True
                break
        except Exception:
            pass
    _hw_decode_available_cache = found
    return found


def gpu_diagnostics():
    """
    Staged GPU capability report used by the System Details dialog.
    Returns an ordered list of (check_name, passed_bool_or_None, detail_string).
    None = check not applicable on this platform.
    """
    checks = []
    ffmpeg_bin = get_ffmpeg_path()
    flags = CREATE_NO_WINDOW if os.name == 'nt' else 0

    # 1. nvidia-smi (driver present?)
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.check_output(
                [smi, "--query-gpu=name,driver_version", "--format=csv,noheader"],
                creationflags=flags, timeout=10.0
            ).decode("utf-8", errors="ignore").strip().splitlines()
            checks.append(("NVIDIA driver", True, out[0] if out else "detected"))
        except Exception as e:
            checks.append(("NVIDIA driver", False, f"nvidia-smi failed: {e}"))
    else:
        checks.append(("NVIDIA driver", None, "nvidia-smi not found (no NVIDIA GPU or driver)"))

    # 2. Linux: NVDEC runtime library (comes from libnvidia-decode-*, not CUDA)
    if sys.platform.startswith("linux"):
        try:
            out = subprocess.check_output(["ldconfig", "-p"], timeout=10.0).decode("utf-8", errors="ignore")
            has_cuvid = "libnvcuvid.so" in out
            checks.append(("libnvcuvid (NVDEC runtime)", has_cuvid,
                           "found" if has_cuvid else "missing - install libnvidia-decode-<driver-version>"))
        except Exception:
            checks.append(("libnvcuvid (NVDEC runtime)", None, "ldconfig unavailable"))

    # 3. FFmpeg hwaccels compiled in
    try:
        out = subprocess.check_output([ffmpeg_bin, "-hide_banner", "-hwaccels"],
                                      stderr=subprocess.STDOUT, creationflags=flags,
                                      timeout=10.0).decode("utf-8", errors="ignore")
        accel_list = [l.strip() for l in out.splitlines()[1:] if l.strip()]
        checks.append(("FFmpeg hwaccels", bool(accel_list), ", ".join(accel_list) or "none"))
    except Exception as e:
        checks.append(("FFmpeg hwaccels", False, str(e)))

    # 4. FFmpeg WebM-capable hardware encoders compiled + actually working
    active = detect_active_hardware_webm_encoders()
    working = [k for k, v in active.items() if v]
    checks.append(("GPU WebM encoders (working)", bool(working),
                   ", ".join(working) if working
                   else "none - NVIDIA VP9 encode does not exist; AV1 needs RTX 40+/Arc"))

    # 5. Hardware decode (hybrid mode feed)
    dec = is_hw_decode_available()
    checks.append(("GPU decode (hybrid mode)", dec,
                   "available - hybrid GPU decode + CPU encode possible" if dec
                   else "unavailable - pure CPU pipeline"))

    return checks

def get_gpu_encoder_params(codec, preset_args, hardware_info, crf_override=None):
    """
    Maps standard CPU codec requests to accelerated hardware WebM encoders.
    All outputs are strictly locked to .webm. No MP4 container is allowed.
    """
    crf = 32
    if crf_override is not None:
        crf = crf_override
    else:
        if "-crf" in preset_args:
            idx = preset_args.index("-crf")
            crf = int(preset_args[idx + 1])

    # Check active hardware capabilities
    active_hw = detect_active_hardware_webm_encoders()
    
    # QP Quality Compensation: subtract 5 from CRF to compensate for GPU encoder deficits
    comp_crf = max(10, crf - 5)
    
    # 1. NVIDIA NVENC (RTX 40-series+ hardware AV1 WebM)
    if active_hw.get("av1_nvenc"):
        qp_val = max(10, min(45, comp_crf))
        return {
            "codec": "av1_nvenc",
            "args": ["-rc", "constqp", "-qp", str(qp_val), "-preset", "p4"],
            "audio_args": ["-c:a", "libopus", "-b:a", "128k"],
            "extension": ".webm"
        }
        
    # 2. Intel QSV (AV1 / VP9 hardware WebM)
    if active_hw.get("av1_qsv"):
        q_val = max(10, min(45, comp_crf))
        return {
            "codec": "av1_qsv",
            "args": ["-global_quality", str(q_val), "-preset", "medium"],
            "audio_args": ["-c:a", "libopus", "-b:a", "128k"],
            "extension": ".webm"
        }
    if active_hw.get("vp9_qsv"):
        q_val = max(10, min(45, comp_crf))
        return {
            "codec": "vp9_qsv",
            "args": ["-global_quality", str(q_val), "-preset", "medium"],
            "audio_args": ["-c:a", "libopus", "-b:a", "128k"],
            "extension": ".webm"
        }
        
    # 3. AMD AMF (RX 7000+ hardware AV1 WebM)
    if active_hw.get("av1_amf"):
        qp_val = max(10, min(45, comp_crf))
        return {
            "codec": "av1_amf",
            "args": ["-rc", "cqp", "-qp_i", str(qp_val), "-qp_p", str(qp_val)],
            "audio_args": ["-c:a", "libopus", "-b:a", "128k"],
            "extension": ".webm"
        }
        
    # 4. macOS VideoToolbox (Apple Silicon WebM encoders)
    if active_hw.get("av1_videotoolbox"):
        q_val = max(10, min(100, int(100 - (comp_crf * 1.5))))
        return {
            "codec": "av1_videotoolbox",
            "args": ["-q:v", str(q_val)],
            "audio_args": ["-c:a", "libopus", "-b:a", "128k"],
            "extension": ".webm"
        }
    if active_hw.get("vp9_videotoolbox"):
        q_val = max(10, min(100, int(100 - (comp_crf * 1.5))))
        return {
            "codec": "vp9_videotoolbox",
            "args": ["-q:v", str(q_val)],
            "audio_args": ["-c:a", "libopus", "-b:a", "128k"],
            "extension": ".webm"
        }
        
    return None

def resolve_engine(task, preset):
    """
    Resolves the user-selected engine (cpu/gpu/hybrid/auto) to what the hardware
    can actually do, sets task.resolved_engine, and returns gpu_params (only for
    true GPU WebM encoding). The selection changes the real FFmpeg command:
    - cpu:    software decode + software encode
    - gpu:    requires a working hardware WebM encoder, else honest CPU fallback
    - hybrid: hardware decode/scale + software encode, else CPU
    - auto:   gpu if real encoder exists, hybrid if decode accel works (>=1080p),
              else cpu
    """
    eng = getattr(task, "engine", None)
    if eng not in ENGINES:
        eng = ENGINE_AUTO if getattr(task, "use_gpu", False) else ENGINE_CPU
    meta = task.metadata
    codec_name = meta.get("codec_name")

    # Audio-only presets never need a video engine
    if preset.get("codec") is None or eng == ENGINE_CPU:
        task.resolved_engine = ENGINE_CPU
        return None

    hardware = detect_active_hardware_webm_encoders()

    if eng == ENGINE_GPU:
        gpu_params = get_gpu_encoder_params(preset["codec"], preset["args"], hardware, task.crf_override)
        if gpu_params:
            task.resolved_engine = ENGINE_GPU
            return gpu_params
        # UI warns and asks before start; the backend still guarantees WebM out
        task.resolved_engine = ENGINE_CPU
        return None

    if eng == ENGINE_HYBRID:
        accel = detect_supported_decode_accel(task.input_path, codec_name)
        if accel:
            task.hybrid_accel = accel
            task.resolved_engine = ENGINE_HYBRID
        else:
            task.resolved_engine = ENGINE_CPU
        return None

    # AUTO
    gpu_params = get_gpu_encoder_params(preset["codec"], preset["args"], hardware, task.crf_override)
    if gpu_params:
        task.resolved_engine = ENGINE_GPU
        return gpu_params
    if meta.get("height", 0) >= HYBRID_MIN_HEIGHT:
        accel = detect_supported_decode_accel(task.input_path, codec_name)
        if accel:
            task.hybrid_accel = accel
            task.resolved_engine = ENGINE_HYBRID
            return None
    task.resolved_engine = ENGINE_CPU
    return None


def validate_ffmpeg_command(cmd):
    """
    Validates that the output file path ends with .webm (or is a null device for passes)
    and that no non-WebM encoders/codecs or output containers are specified.
    """
    # 1. Output path validation (always the last argument)
    output_path = cmd[-1].lower()
    if not (output_path.endswith(".webm") or output_path in ["nul", "/dev/null"]):
        return False, f"Output file '{cmd[-1]}' must be a .webm file or null device."

    # 2. Iterative codec parameter checking
    for i in range(len(cmd) - 1):
        arg = cmd[i].lower()
        val = cmd[i+1].lower()
        
        # Check video codec parameters
        if arg in ["-c:v", "-codec:v", "-vcodec"]:
            if not any(vc in val for vc in ["vp8", "vp9", "libvpx", "libsvtav1", "av1"]):
                return False, f"Non-WebM video codec '{cmd[i+1]}' detected."
                
        # Check audio codec parameters
        if arg in ["-c:a", "-codec:a", "-acodec"]:
            if not any(ac in val for ac in ["opus", "vorbis", "libopus", "libvorbis", "none"]):
                return False, f"Non-WebM audio codec '{cmd[i+1]}' detected."
                
    return True, ""

def get_metadata(file_path):
    """
    Retrieves video metadata duration, width, height, bitrate, and size,
    as well as HDR/color space parameters.
    """
    if not os.path.exists(file_path):
        return {
            "duration": 0.0, "width": 0, "height": 0, "bitrate": 0, "size_bytes": 0,
            "color_space": None, "color_transfer": None, "color_primaries": None
        }
        
    try:
        ffprobe_bin = get_ffprobe_path()
        dur_cmd = [
            ffprobe_bin, "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            file_path
        ]
        duration_str = subprocess.check_output(
            dur_cmd, 
            creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0
        ).decode().strip()
        duration = float(duration_str) if duration_str else 0.0

        vid_cmd = [
            ffprobe_bin, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,bit_rate,color_space,color_transfer,color_primaries,pix_fmt,avg_frame_rate,r_frame_rate",
            "-of", "json",
            file_path
        ]
        vid_out = subprocess.check_output(
            vid_cmd, 
            creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0
        ).decode()
        
        width = 0
        height = 0
        bitrate = 0
        color_space = None
        color_transfer = None
        color_primaries = None
        pix_fmt = None
        fps = 0.0
        codec_name = None

        if vid_out.strip():
            vid_data = json.loads(vid_out)
            if "streams" in vid_data and len(vid_data["streams"]) > 0:
                stream = vid_data["streams"][0]
                codec_name = stream.get("codec_name")
                width = stream.get("width", 0)
                height = stream.get("height", 0)
                bitrate = int(stream.get("bit_rate", 0)) if stream.get("bit_rate") else 0
                color_space = stream.get("color_space")
                color_transfer = stream.get("color_transfer")
                color_primaries = stream.get("color_primaries")
                pix_fmt = stream.get("pix_fmt")
                rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/0"
                try:
                    num, den = rate.split("/")
                    fps = (float(num) / float(den)) if float(den) else 0.0
                except Exception:
                    fps = 0.0
            
        if bitrate == 0:
            fmt_cmd = [
                ffprobe_bin, "-v", "error",
                "-show_entries", "format=bit_rate",
                "-of", "json",
                file_path
            ]
            fmt_out = subprocess.check_output(
                fmt_cmd, 
                creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0
            ).decode()
            if fmt_out.strip():
                fmt_data = json.loads(fmt_out)
                if "format" in fmt_data:
                    bitrate = int(fmt_data["format"].get("bit_rate", 0)) if fmt_data["format"].get("bit_rate") else 0

        return {
            "duration": duration,
            "width": width,
            "height": height,
            "bitrate": bitrate,
            "size_bytes": os.path.getsize(file_path),
            "color_space": color_space,
            "color_transfer": color_transfer,
            "color_primaries": color_primaries,
            "pix_fmt": pix_fmt,
            "fps": fps,
            "codec_name": codec_name
        }
    except Exception as e:
        print(f"Error fetching metadata for {file_path}: {e}")
        return {
            "duration": 0.0, 
            "width": 0, 
            "height": 0, 
            "bitrate": 0, 
            "size_bytes": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            "color_space": None,
            "color_transfer": None,
            "color_primaries": None,
            "pix_fmt": None,
            "fps": 0.0,
            "codec_name": None
        }

def build_ffmpeg_command(task, preset, gpu_params, pass_num=None, passlog_path=None, force_software_decode=False):
    ffmpeg_bin = get_ffmpeg_path()
    cmd = [ffmpeg_bin, "-y"]
    
    # 1. Hardware decode acceleration (engine-aware)
    use_cuda_accel = False
    use_hybrid = False
    accel_type = None

    meta = task.metadata
    height = meta.get("height", 0)
    fps_cap = getattr(task, "fps_cap", None)
    eng = getattr(task, "resolved_engine", None)
    if eng is None:
        eng = ENGINE_AUTO if getattr(task, "use_gpu", False) else ENGINE_CPU

    if eng != ENGINE_CPU and not force_software_decode:
        if gpu_params:
            # True HW encoding mode: also decode on GPU when the file allows it
            if gpu_params["codec"] == "av1_nvenc":
                if probe_hw_decode(task.input_path, "cuda", meta.get("codec_name")):
                    cmd.extend(["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"])
                    use_cuda_accel = True
        elif eng in (ENGINE_HYBRID, ENGINE_AUTO):
            # Explicit HYBRID honors the user's choice at any resolution;
            # AUTO keeps the >=1080p gate (hwdownload overhead is not worth
            # it on small frames).
            if eng == ENGINE_HYBRID or height >= HYBRID_MIN_HEIGHT:
                accel_type = getattr(task, "hybrid_accel", None)
                if not accel_type:
                    accel_type = detect_supported_decode_accel(task.input_path, meta.get("codec_name"))
                if accel_type:
                    use_hybrid = True
                    task.hybrid_active = True
                    task.hybrid_accel = accel_type
                    cmd.extend(HW_PARAMS[accel_type]["accel_args"])
                else:
                    task.hybrid_active = False
            else:
                task.hybrid_active = False
    else:
        task.hybrid_active = False

    cmd.append("-i")
    cmd.append(task.input_path)
    
    # 2. VFR frame rate sync & stream mapping
    # Map only video + audio streams: WebM cannot carry arbitrary subtitle/data
    # tracks, so "-map 0" would make muxing fail on inputs that have them.
    cmd.extend(["-fps_mode", "passthrough", "-map", "0:v:0?", "-map", "0:a?"])
    
    # 3. Apply resolution scale & preserve HDR tags / download layers
    filters = []
    if use_hybrid:
        accel_info = HW_PARAMS[accel_type]
        scaler = accel_info["scaler"]
        
        # Format mapping based on bit depth
        if task.bit10:
            hw_fmt = "p010"
            sw_fmt = "yuv420p10le"
        else:
            hw_fmt = "nv12"
            sw_fmt = "yuv420p"
            
        if preset["resolution"]:
            w, h = preset["resolution"]
            if scaler:
                filters.append(f"{scaler}={w}:-2")
                filters.append(f"hwdownload,format={hw_fmt},format={sw_fmt}")
            else:
                filters.append(f"hwdownload,format={hw_fmt},format={sw_fmt}")
                filters.append(f"scale={w}:-2")
        else:
            filters.append(f"hwdownload,format={hw_fmt},format={sw_fmt}")
    else:
        if preset["resolution"]:
            w, h = preset["resolution"]
            if use_cuda_accel:
                filters.append(f"scale_cuda={w}:-2")
            else:
                filters.append(f"scale={w}:-2")
            
    # Optional frame-rate cap (big speed win for high-fps screen recordings).
    # A CUDA scaler runs on GPU frames, so cap on CPU after the download.
    if fps_cap and fps_cap > 0:
        src_fps = meta.get("fps", 0) or 0
        if src_fps == 0 or src_fps > fps_cap + 0.5:
            filters.append(f"fps={fps_cap}")

    # Pass 1 produces no output packets on modern FFmpeg, so its stats line
    # shows time=N/A forever. showinfo logs each frame's pts_time as it enters
    # the encoder - that is the REAL analysis progress the UI parses.
    if pass_num == 1:
        filters.append("showinfo")

    if filters:
        cmd.extend(["-vf", ",".join(filters)])

    # 4. Color / HDR parameters preservation
    meta = task.metadata
    if meta.get("color_primaries"):
        cmd.extend(["-color_primaries", meta["color_primaries"]])
    if meta.get("color_transfer"):
        cmd.extend(["-color_trc", meta["color_transfer"]])
    if meta.get("color_space"):
        cmd.extend(["-colorspace", meta["color_space"]])

    # 5. Apply video codec & args
    if gpu_params:
        cmd.extend(["-c:v", gpu_params["codec"]])
        cmd.extend(gpu_params["args"])
    else:
        codec = preset["codec"]
        if codec:
            cmd.extend(["-c:v", codec])
            args = list(preset["args"])
            
            # CRF Override
            if task.crf_override is not None and "-crf" in args:
                idx = args.index("-crf")
                args[idx + 1] = str(task.crf_override)
                
            # SVT-AV1 preset override & parameter cleaning
            if codec == "libsvtav1":
                # Clean tile-columns & row-mt if present
                for flag in ["-tile-columns", "-row-mt", "-tile_columns", "-tile_rows"]:
                    if flag in args:
                        try:
                            idx = args.index(flag)
                            args.pop(idx + 1)
                            args.pop(idx)
                        except Exception:
                            pass
                if task.av1_preset is not None and "-preset" in args:
                    idx = args.index("-preset")
                    args[idx + 1] = str(task.av1_preset)
                    
            # VP9 specific parameters (lookahead / alt-ref / b:v 0 constant quality)
            if codec == "libvpx-vp9":
                if "-b:v" not in args:
                    args.extend(["-b:v", "0"])
                else:
                    idx = args.index("-b:v")
                    args[idx + 1] = "0"
                # Add lookahead/alt-ref if missing
                for k, v in [("-deadline", "good"), ("-cpu-used", "2"), ("-lag-in-frames", "25"), ("-auto-alt-ref", "1")]:
                    if k in args:
                        idx = args.index(k)
                        args[idx + 1] = v
                    else:
                        args.extend([k, v])
                        
            cmd.extend(args)
            
    # 6. Pixel Format (10-bit color option vs standard yuv420p)
    if task.bit10:
        cmd.extend(["-pix_fmt", "yuv420p10le"])
    else:
        cmd.extend(["-pix_fmt", "yuv420p"])

    # 7. Two-Pass specific parameters
    if pass_num == 1:
        cmd.extend(["-pass", "1", "-passlogfile", passlog_path, "-an", "-f", "null"])
        null_dev = "NUL" if os.name == 'nt' else "/dev/null"
        cmd.append(null_dev)
    elif pass_num == 2:
        cmd.extend(["-pass", "2", "-passlogfile", passlog_path])
        if gpu_params:
            cmd.extend(gpu_params["audio_args"])
        else:
            cmd.extend(preset["audio_args"])
        cmd.append(task.output_path)
    else:
        if gpu_params:
            cmd.extend(gpu_params["audio_args"])
        else:
            cmd.extend(preset["audio_args"])
        cmd.append(task.output_path)
        
    return cmd

def generate_preview(input_path, output_path, preset_name, use_gpu=False, crf_override=None, two_pass=False, bit10=False, av1_preset=None, engine=None, fps_cap=None):
    """
    Extracts a 5-second slice from the exact middle and compresses it using the
    EXACT settings of the final job: profile, codec, CRF, engine (cpu/gpu/
    hybrid/auto), two-pass, 10-bit, AV1 preset and fps cap. Strictly WebM.
    Returns (path, size_bytes, settings_summary_dict).
    """
    if not output_path.lower().endswith(".webm"):
        raise ValueError("Security Exception: Output path must end with .webm")

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file {input_path} does not exist.")

    meta = get_metadata(input_path)
    duration = meta["duration"]
    start_time = max(0.0, (duration / 2.0) - 2.5)

    # Slice temporary file has original container suffix
    temp_slice = os.path.splitext(output_path)[0] + "_temp_slice" + os.path.splitext(input_path)[1]
    ffmpeg_bin = get_ffmpeg_path()

    slice_cmd = [
        ffmpeg_bin, "-y", "-ss", str(start_time), "-t", "5.0",
        "-i", input_path, "-c", "copy", temp_slice
    ]
    flags = CREATE_NO_WINDOW if os.name == 'nt' else 0
    subprocess.run(slice_cmd, check=True, creationflags=flags)

    try:
        preset = PRESETS.get(preset_name)
        if not preset:
            raise ValueError("Invalid preset selection.")

        # Temporary task fed through the same engine resolution and command
        # builder as the real compression job (no simplified preview path)
        temp_task = EncoderTask(0, temp_slice, output_path, preset_name, use_gpu,
                                crf_override, two_pass, bit10, av1_preset,
                                engine=engine, fps_cap=fps_cap)
        gpu_params = resolve_engine(temp_task, preset)

        is_vp9 = (preset["codec"] == "libvpx-vp9")
        run_two_pass = bool(two_pass and is_vp9 and temp_task.resolved_engine != ENGINE_GPU)

        if run_two_pass:
            passlog = os.path.join(tempfile.gettempdir(), f"vp9_preview_passlog_{int(time.time())}")
            cmd1 = build_ffmpeg_command(temp_task, preset, gpu_params, pass_num=1, passlog_path=passlog)
            ok, err = validate_ffmpeg_command(cmd1)
            if not ok:
                raise ValueError(f"Security Blocker: {err}")
            subprocess.run(cmd1, check=True, creationflags=flags)

            cmd2 = build_ffmpeg_command(temp_task, preset, gpu_params, pass_num=2, passlog_path=passlog)
            ok, err = validate_ffmpeg_command(cmd2)
            if not ok:
                raise ValueError(f"Security Blocker: {err}")
            subprocess.run(cmd2, check=True, creationflags=flags)

            for ext in ["-0.log", ".log"]:
                p = passlog + ext
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
        else:
            cmd = build_ffmpeg_command(temp_task, preset, gpu_params)
            ok, err = validate_ffmpeg_command(cmd)
            if not ok:
                raise ValueError(f"Security Blocker: {err}")
            subprocess.run(cmd, check=True, creationflags=flags)

        summary = {
            "profile": preset_name,
            "codec": (gpu_params["codec"] if gpu_params else preset["codec"]) or "audio only",
            "crf": crf_override,
            "engine": temp_task.resolved_engine or ENGINE_CPU,
            "hybrid": bool(temp_task.hybrid_active),
            "hybrid_accel": temp_task.hybrid_accel,
            "two_pass": run_two_pass,
            "bit10": bool(bit10),
            "fps_cap": fps_cap,
            "av1_preset": av1_preset
        }
    finally:
        if os.path.exists(temp_slice):
            try:
                os.remove(temp_slice)
            except Exception:
                pass

    return output_path, os.path.getsize(output_path), summary

class EncoderTask:
    def __init__(self, task_id, input_path, output_path, preset_name, use_gpu=False, crf_override=None, two_pass=False, bit10=False, av1_preset=None, metadata_override=None, engine=None, fps_cap=None):
        self.id = task_id
        self.input_path = input_path
        self.output_path = output_path
        self.preset_name = preset_name
        # Engine: cpu / gpu / hybrid / auto. Legacy use_gpu maps to auto.
        if engine in ENGINES:
            self.engine = engine
        else:
            self.engine = ENGINE_AUTO if use_gpu else ENGINE_CPU
        self.use_gpu = self.engine != ENGINE_CPU
        self.resolved_engine = None   # set by resolve_engine at encode time
        self.crf_override = crf_override
        self.two_pass = two_pass
        self.bit10 = bit10
        self.av1_preset = av1_preset
        self.fps_cap = fps_cap   # None = keep source fps; set to 30 to cap
        self.selected = True   # user can untick a row to exclude it from the run
        self.hybrid_active = False
        self.hybrid_accel = None
        self.status = "Pending"
        self.progress = 0.0
        self.pass_num = 0        # 0 = single pass, 1/2 = two-pass stages
        self.pass_progress = 0.0  # progress of the CURRENT pass, 0-100
        self.speed = "0.0x"
        self.speed_ema = None    # smoothed encode speed (x realtime) for ETA
        self.elapsed = 0
        self.eta = -1            # -1 = unknown / "Estimating..."
        self.paused_seconds = 0.0
        self.pause_started = None
        self.hw_proof = []       # captured FFmpeg log lines proving HW activity
        self.est_size_bytes = 0
        self.error_msg = ""
        # Per-file extension point: future options (LUT, crop, resize,
        # subtitles, metadata, output overrides, audio settings) live here so
        # new features never require a schema change.
        self.extras = {}
        if metadata_override:
            self.metadata = metadata_override
        else:
            self.metadata = get_metadata(input_path)

    def to_dict(self):
        """Serializable snapshot of the task's identity and settings."""
        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "preset_name": self.preset_name,
            "engine": self.engine,
            "crf_override": self.crf_override,
            "two_pass": bool(self.two_pass),
            "bit10": bool(self.bit10),
            "av1_preset": self.av1_preset,
            "fps_cap": self.fps_cap,
            "selected": bool(self.selected),
            "extras": dict(self.extras),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, task_id, data):
        """
        Rebuilds a task from to_dict() output. Status always restarts at
        Pending; saved metadata is reused to avoid re-probing every file.
        """
        task = cls(
            task_id,
            data.get("input_path", ""),
            data.get("output_path", ""),
            data.get("preset_name", ""),
            crf_override=data.get("crf_override"),
            two_pass=data.get("two_pass", False),
            bit10=data.get("bit10", False),
            av1_preset=data.get("av1_preset"),
            metadata_override=data.get("metadata") or None,
            engine=data.get("engine"),
            fps_cap=data.get("fps_cap"),
        )
        task.selected = bool(data.get("selected", True))
        task.extras = dict(data.get("extras", {}))
        return task


def estimate_task_output_bytes(task):
    """
    Rough expected output size in bytes for a task with ITS OWN settings,
    used by the destination free-space preflight. Includes a 15% safety
    margin; audio-only presets are estimated from the Opus bitrate.
    """
    meta = task.metadata
    duration = meta.get("duration", 0.0) or 0.0
    preset = PRESETS.get(task.preset_name)
    if not preset or duration <= 0:
        return 0
    if preset.get("codec") is None:
        bps = 64_000  # Audio Only preset target bitrate
    else:
        bps = estimate_typical_output_bitrate(
            task.preset_name, task.crf_override, meta.get("height", 1080)
        )
        bps += 96_000  # audio track
    return int(duration * bps / 8 * 1.15)

class EncodingQueue:
    def __init__(self, callback_on_update=None, callback_on_finish=None):
        self.tasks = []
        self.queue = queue.Queue()
        self.running = False
        self.paused = False
        self.current_process = None
        self.thread = None
        self.callback_on_update = callback_on_update
        self.callback_on_finish = callback_on_finish
        self.current_task = None
        self.abort_flag = False

    def add_task(self, input_path, output_path, preset_name, use_gpu=False, crf_override=None, two_pass=False, bit10=False, av1_preset=None, metadata_override=None, engine=None, fps_cap=None):
        task_id = len(self.tasks) + 1
        task = EncoderTask(task_id, input_path, output_path, preset_name, use_gpu, crf_override, two_pass, bit10, av1_preset, metadata_override, engine=engine, fps_cap=fps_cap)
        self.tasks.append(task)
        if self.callback_on_update:
            self.callback_on_update()
        return task

    def start(self):
        if self.running:
            return

        self.running = True
        self.paused = False
        self.abort_flag = False

        for task in self.tasks:
            if task.status in ["Pending", "Failed", "Stopped"] and getattr(task, "selected", True):
                task.status = "Queued"
                task.progress = 0.0
                task.pass_progress = 0.0
                task.pass_num = 0
                task.resolved_engine = None
                task.speed = "0.0x"
                task.speed_ema = None
                task.elapsed = 0
                task.eta = -1
                task.paused_seconds = 0.0
                task.pause_started = None
                task.hw_proof = []
                task.est_size_bytes = 0
                self.queue.put(task)

        if self.callback_on_update:
            self.callback_on_update()

        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()

    def _set_process_suspended(self, suspend):
        """
        Truly suspends/resumes the FFmpeg process at OS level. The process keeps
        all file handles; on resume it continues exactly where it stopped, so
        the output cannot be corrupted by pausing. Not a fake UI state.
        """
        p = self.current_process
        if not p or p.poll() is not None:
            return False
        try:
            if os.name == 'nt':
                import ctypes
                fn = ctypes.windll.ntdll.NtSuspendProcess if suspend else ctypes.windll.ntdll.NtResumeProcess
                fn(int(p._handle))
            else:
                import signal
                os.kill(p.pid, signal.SIGSTOP if suspend else signal.SIGCONT)
            return True
        except Exception as e:
            print(f"Process {'suspend' if suspend else 'resume'} failed: {e}")
            return False

    def pause(self):
        """Pause the active compression job (OS-level process suspension)."""
        if self.paused or not self.running:
            return False
        self.paused = True
        task = self.current_task
        if task and task.status == "Encoding":
            if self._set_process_suspended(True):
                task.pause_started = time.time()
                task.status = "Paused"
                task.speed = "-"
        if self.callback_on_update:
            self.callback_on_update()
        return True

    def resume(self):
        """Resume a paused compression job."""
        if not self.paused:
            return False
        task = self.current_task
        if task and task.status == "Paused":
            task.status = "Resuming"
            if self.callback_on_update:
                self.callback_on_update()
            self._set_process_suspended(False)
            if getattr(task, "pause_started", None):
                task.paused_seconds = getattr(task, "paused_seconds", 0.0) + (time.time() - task.pause_started)
                task.pause_started = None
            # First speed sample after resume is stale; re-seed the ETA average
            task.speed_ema = None
            task.eta = -1
            task.status = "Encoding"
        self.paused = False
        if self.callback_on_update:
            self.callback_on_update()
        return True

    def stop(self):
        self.abort_flag = True
        self.running = False
        # A suspended process cannot process terminate(): resume it first
        if self.paused:
            self._set_process_suspended(False)
            self.paused = False
        if self.current_process:
            try:
                self.current_process.terminate()
            except Exception:
                pass

        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except queue.Empty:
                break

        for task in self.tasks:
            if task.status in ["Queued", "Encoding", "Paused", "Resuming"]:
                task.status = "Stopped"
                task.progress = 0.0
                task.pass_progress = 0.0
                task.speed = "-"
                task.eta = -1

        self.current_task = None
        if self.callback_on_update:
            self.callback_on_update()

    def move_task(self, task_id, delta):
        """
        Swap a task with its neighbor (delta < 0 moves up, > 0 moves down) and
        renumber ids to match the new order. The worker consumes tasks in list
        order, so this directly controls encode order. Returns True on success.
        """
        idx = next((i for i, t in enumerate(self.tasks) if t.id == task_id), None)
        if idx is None:
            return False
        j = idx + (1 if delta > 0 else -1)
        if j < 0 or j >= len(self.tasks):
            return False
        self.tasks[idx], self.tasks[j] = self.tasks[j], self.tasks[idx]
        for i, t in enumerate(self.tasks):
            t.id = i + 1
        if self.callback_on_update:
            self.callback_on_update()
        return True

    def remove_task(self, task_id):
        for idx, task in enumerate(self.tasks):
            if task.id == task_id:
                if task.status == "Encoding":
                    self.stop()
                self.tasks.pop(idx)
                break
        
        for idx, task in enumerate(self.tasks):
            task.id = idx + 1
            
        if self.callback_on_update:
            self.callback_on_update()

    def clear(self):
        self.stop()
        self.tasks.clear()
        if self.callback_on_update:
            self.callback_on_update()

    def _worker_loop(self):
        while self.running and not self.queue.empty():
            if self.abort_flag:
                break
                
            task = self.queue.get()
            self.current_task = task
            task.status = "Encoding"
            if self.callback_on_update:
                self.callback_on_update()
                
            self._encode_file(task)
            
            self.queue.task_done()
            
        self.running = False
        self.current_task = None
        if self.callback_on_finish:
            self.callback_on_finish()

    def _encode_file(self, task):
        # 1. Enforce WebM output path suffix
        if not task.output_path.lower().endswith(".webm"):
            task.status = "Failed"
            task.error_msg = f"Security Exception: Output path '{task.output_path}' must end with .webm."
            print(task.error_msg)
            if self.callback_on_update:
                self.callback_on_update()
            return

        # 2. Prevent source file overwrite
        if os.path.abspath(task.input_path) == os.path.abspath(task.output_path):
            task.status = "Failed"
            task.error_msg = "Security Exception: Output file cannot overwrite the original source file."
            print(task.error_msg)
            if self.callback_on_update:
                self.callback_on_update()
            return

        out_dir = os.path.dirname(task.output_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
            
        preset = PRESETS.get(task.preset_name)
        if not preset:
            task.status = "Failed"
            task.error_msg = "Invalid preset selection."
            if self.callback_on_update:
                self.callback_on_update()
            return

        # Resolve the selected engine (cpu/gpu/hybrid/auto) against real hardware
        gpu_params = resolve_engine(task, preset)
        print(f"Engine resolved: {task.engine} -> {task.resolved_engine}")

        force_sw = False
        retry_count = 0

        while retry_count < 2:
            try:
                # Decide if two-pass is applicable. Two-pass works for CPU and
                # HYBRID engines (hybrid only assists decoding); it does not
                # apply to true GPU encoders.
                is_vp9 = (preset["codec"] == "libvpx-vp9")

                if task.two_pass and is_vp9 and task.resolved_engine != ENGINE_GPU:
                    # Run pass 1
                    passlog_base = os.path.join(tempfile.gettempdir(), f"vp9_passlog_{task.id}_{int(time.time())}")
                    cmd1 = build_ffmpeg_command(task, preset, gpu_params, pass_num=1, passlog_path=passlog_base, force_software_decode=force_sw)
                    
                    ok, err = validate_ffmpeg_command(cmd1)
                    if not ok:
                        raise ValueError(f"Security Blocker Pass 1: {err}")
                        
                    print(f"Executing VP9 Pass 1: {' '.join(cmd1)}")
                    task.status = "Encoding"
                    self._run_ffmpeg_process(task, cmd1, is_pass1=True)
                    
                    if self.abort_flag:
                        task.status = "Stopped"
                        return
                        
                    if task.status == "Failed":
                        if task.resolved_engine != ENGINE_CPU:
                            print("Encoding failed in GPU/hybrid mode (Pass 1). Retrying with pure CPU encoding fallback...")
                            task.use_gpu = False
                            task.resolved_engine = ENGINE_CPU
                            task.hybrid_active = False
                            task.hybrid_accel = None
                            gpu_params = None
                            force_sw = True
                            retry_count += 1
                            continue
                        return
                        
                    # Run pass 2
                    cmd2 = build_ffmpeg_command(task, preset, gpu_params, pass_num=2, passlog_path=passlog_base, force_software_decode=force_sw)
                    ok, err = validate_ffmpeg_command(cmd2)
                    if not ok:
                        raise ValueError(f"Security Blocker Pass 2: {err}")
                        
                    print(f"Executing VP9 Pass 2: {' '.join(cmd2)}")
                    self._run_ffmpeg_process(task, cmd2, is_pass1=False)
                    
                    # Cleanup logfiles
                    for ext in ["-0.log", ".log"]:
                        p = passlog_base + ext
                        if os.path.exists(p):
                            try:
                                os.remove(p)
                            except Exception:
                                pass
                else:
                    # Single Pass
                    cmd = build_ffmpeg_command(task, preset, gpu_params, force_software_decode=force_sw)
                    ok, err = validate_ffmpeg_command(cmd)
                    if not ok:
                        raise ValueError(f"Security Blocker: {err}")
                        
                    print(f"Executing Encode: {' '.join(cmd)}")
                    self._run_ffmpeg_process(task, cmd)
                    
                if task.status == "Failed" and task.resolved_engine != ENGINE_CPU:
                    print("Encoding failed in GPU/hybrid mode. Retrying with pure CPU encoding fallback...")
                    task.use_gpu = False
                    task.resolved_engine = ENGINE_CPU
                    task.hybrid_active = False
                    task.hybrid_accel = None
                    gpu_params = None
                    force_sw = True
                    retry_count += 1
                    continue

                break
            except Exception as e:
                if task.resolved_engine != ENGINE_CPU:
                    print(f"Hardware execution exception: {e}. Retrying with pure CPU encoding fallback...")
                    task.use_gpu = False
                    task.resolved_engine = ENGINE_CPU
                    task.hybrid_active = False
                    task.hybrid_accel = None
                    gpu_params = None
                    force_sw = True
                    retry_count += 1
                    continue
                else:
                    task.status = "Failed"
                    task.error_msg = str(e)
                    break
                    
        if self.callback_on_update:
            self.callback_on_update()

    def _run_ffmpeg_process(self, task, cmd, is_pass1=False):
        # Print safety check pre-log
        print("=== JOB START SAFETY CHECK ===")
        print(f"- Input Path: {task.input_path}")
        print(f"- Profile: {task.preset_name}")
        print(f"- Quality CRF: {task.crf_override}")
        print(f"- Engine: {(task.resolved_engine or 'cpu').upper()}" + (" (hybrid decode assist)" if task.hybrid_active else ""))
        print(f"- Format: WebM")
        print("==============================")

        # If the user paused between passes, wait here before launching the next
        while self.paused and not self.abort_flag:
            time.sleep(0.2)
        if self.abort_flag:
            return

        task.start_time = time.time()
        task.paused_seconds = 0.0
        task.pause_started = None
        task.pass_num = (1 if is_pass1 else 2) if task.two_pass else 0
        task.pass_progress = 0.0
        task.speed_ema = None
        task.eta = -1

        try:
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0,
                universal_newlines=True
            )

            duration = task.metadata["duration"]
            time_regex = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")
            speed_regex = re.compile(r"speed=\s*(\d+\.?\d*)x")
            # Pass 1 progress source: showinfo per-frame pts (time= is N/A there)
            pts_regex = re.compile(r"pts_time:\s*([0-9]+\.?[0-9]*)")

            # Real hardware-activity proof captured from FFmpeg's own log
            proof_keys = ("nvdec", "cuvid", "hwaccel", "scale_cuda", "scale_vaapi",
                          "scale_qsv", "pixfmt:cuda", "pix_fmt: cuda")
            pass_wall_start = time.time()
            last_eta_update = 0.0
            last_pts_update = 0.0

            def update_from_position(elapsed_video):
                """Progress/elapsed/ETA/size from the current video position."""
                nonlocal last_eta_update
                pass_pct = min(100.0, (elapsed_video / duration) * 100.0)
                task.pass_progress = pass_pct
                if task.two_pass:
                    if is_pass1:
                        task.progress = min(50.0, pass_pct / 2.0)
                    else:
                        task.progress = min(100.0, 50.0 + pass_pct / 2.0)
                else:
                    task.progress = pass_pct

                now = time.time()
                wall = max(0.001, now - task.start_time - task.paused_seconds)
                task.elapsed = int(wall)

                # Speed for ETA: smoothed FFmpeg speed= when available (output
                # passes); computed average decode speed during pass 1, where
                # FFmpeg reports speed=N/A.
                spd = task.speed_ema
                if is_pass1:
                    spd = elapsed_video / wall
                    task.speed = f"{spd:.1f}x"

                sampled = now - pass_wall_start
                if spd and spd > 0.01 and (pass_pct >= ETA_MIN_PASS_PROGRESS
                                           or sampled >= ETA_MIN_SAMPLE_SECONDS):
                    if now - last_eta_update >= 1.0:
                        task.eta = max(0, int((duration - elapsed_video) / spd))
                        last_eta_update = now
                elif task.eta < 0:
                    task.eta = -1  # UI shows "Estimating..."

                # Size extrapolation from the fraction of OUTPUT written
                # (pass_progress, not combined progress) once stable enough
                if pass_pct > 3.0 and not is_pass1 and os.path.exists(task.output_path):
                    curr_size = os.path.getsize(task.output_path)
                    task.est_size_bytes = int(curr_size / (pass_pct / 100.0))

            while self.current_process.poll() is None:
                line = self.current_process.stdout.readline()
                if not line:
                    continue

                low = line.lower()
                if len(task.hw_proof) < 12 and any(k in low for k in proof_keys):
                    task.hw_proof.append(line.strip())

                if is_pass1 and duration > 0 and "pts_time" in line:
                    # showinfo emits one line per frame; throttle the math
                    now = time.time()
                    if now - last_pts_update >= 0.1:
                        m = pts_regex.search(line)
                        if m:
                            last_pts_update = now
                            update_from_position(float(m.group(1)))
                            if self.callback_on_update:
                                self.callback_on_update()
                    continue

                t_match = time_regex.search(line)
                if t_match and duration > 0:
                    hours = int(t_match.group(1))
                    minutes = int(t_match.group(2))
                    seconds = float(t_match.group(3))
                    update_from_position(hours * 3600 + minutes * 60 + seconds)

                s_match = speed_regex.search(line)
                if s_match:
                    try:
                        v = float(s_match.group(1))
                        task.speed = f"{v}x"
                        if v > 0:
                            if task.speed_ema is None:
                                task.speed_ema = v
                            else:
                                task.speed_ema = ETA_EMA_ALPHA * v + (1 - ETA_EMA_ALPHA) * task.speed_ema
                    except Exception:
                        pass

                if self.callback_on_update:
                    self.callback_on_update()
                    
            ret_code = self.current_process.wait()
            
            if ret_code == 0:
                if not is_pass1:
                    # Post-Encode Verification Checks
                    if not os.path.exists(task.output_path):
                        raise FileNotFoundError("Output file was not created by FFmpeg.")
                        
                    ffprobe_bin = get_ffprobe_path()
                    
                    # Check container format
                    fmt_cmd = [
                        ffprobe_bin, "-v", "error",
                        "-show_entries", "format=format_name",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        task.output_path
                    ]
                    container_fmt = subprocess.check_output(
                        fmt_cmd, 
                        creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0
                    ).decode().strip().lower()
                    
                    # Check codecs
                    codec_cmd = [
                        ffprobe_bin, "-v", "error",
                        "-select_streams", "v:0",
                        "-show_entries", "stream=codec_name",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        task.output_path
                    ]
                    video_codec = subprocess.check_output(
                        codec_cmd, 
                        creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0
                    ).decode().strip().lower()
                    
                    # Audio codec
                    audio_codec = "none"
                    try:
                        audio_cmd = [
                            ffprobe_bin, "-v", "error",
                            "-select_streams", "a:0",
                            "-show_entries", "stream=codec_name",
                            "-of", "default=noprint_wrappers=1:nokey=1",
                            task.output_path
                        ]
                        audio_codec = subprocess.check_output(
                            audio_cmd, 
                            creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0
                        ).decode().strip().lower()
                    except Exception:
                        pass
                    
                    print("=== POST-JOB VERIFICATION ===")
                    print(f"- File exists: True")
                    print(f"- Container: {container_fmt}")
                    print(f"- Video Codec: {video_codec}")
                    print(f"- Audio Codec: {audio_codec}")
                    
                    # Validate container format (webm or matroska,webm)
                    if "webm" not in container_fmt:
                        raise ValueError(f"Post-Verification Failure: Container format '{container_fmt}' is not WebM.")
                        
                    # Validate video codec
                    if video_codec not in ["vp8", "vp9", "av1"]:
                        raise ValueError(f"Post-Verification Failure: Video codec '{video_codec}' is not VP8, VP9, or AV1.")
                        
                    # Validate audio codec
                    if audio_codec not in ["", "none", "opus", "vorbis", "libopus", "libvorbis"]:
                        raise ValueError(f"Post-Verification Failure: Audio codec '{audio_codec}' is not Opus or Vorbis.")
                        
                    print("Verification Passed.")
                    print("=============================")
                    
                    task.status = "Completed"
                    task.progress = 100.0
                    task.pass_progress = 100.0
                    task.eta = 0
                    task.est_size_bytes = os.path.getsize(task.output_path)
                else:
                    # Pass 1 completed successfully
                    task.progress = 50.0
                    task.pass_progress = 100.0
            else:
                if self.abort_flag:
                    task.status = "Stopped"
                    task.progress = 0.0
                    task.eta = -1
                else:
                    task.status = "Failed"
                    task.error_msg = f"FFmpeg failed with exit code {ret_code}."
        except Exception as e:
            if os.path.exists(task.output_path) and not is_pass1:
                try:
                    os.remove(task.output_path)
                except Exception:
                    pass
            task.status = "Failed"
            task.error_msg = str(e)
            print(f"Error: {e}")
            
        self.current_process = None
        if self.callback_on_update:
            self.callback_on_update()
