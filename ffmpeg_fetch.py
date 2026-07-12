"""
First-run FFmpeg fetcher.

Downloads an LGPL-licensed FFmpeg build (BtbN/FFmpeg-Builds) and places
ffmpeg.exe / ffprobe.exe next to the application so encoder.get_ffmpeg_path()
finds them. The LGPL build is intentional: it contains the WebM toolchain
(libvpx-vp9, SVT-AV1, libopus) without GPL components (x264/x265), which keeps
redistribution obligations minimal for this app.

Windows-only. On other platforms, install FFmpeg via the system package manager.
"""
import os
import sys
import ssl
import zipfile
import tempfile
import urllib.request

# BtbN publishes a stable "latest" asset name for the LGPL master build.
FFMPEG_LGPL_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/"
    "ffmpeg-master-latest-win64-lgpl.zip"
)

WANTED_BINARIES = ("ffmpeg.exe", "ffprobe.exe")


def get_app_dir():
    """Directory where the app executable (or source) lives. Same logic as encoder.py."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def ffmpeg_missing():
    """True when neither a local nor a PATH ffmpeg/ffprobe pair is usable."""
    import shutil
    app_dir = get_app_dir()
    local_ok = all(os.path.exists(os.path.join(app_dir, b)) for b in WANTED_BINARIES)
    path_ok = shutil.which("ffmpeg") and shutil.which("ffprobe")
    return not (local_ok or path_ok)


def download_ffmpeg(progress_cb=None, cancel_flag=None):
    """
    Downloads and extracts ffmpeg.exe + ffprobe.exe into the app directory.

    progress_cb(fraction, message) is called with fraction in [0.0, 1.0].
    cancel_flag: optional callable returning True to abort.
    Returns the app directory on success; raises on failure.
    """
    if sys.platform != "win32":
        raise RuntimeError("Auto-download is Windows-only. Install FFmpeg via your package manager.")

    app_dir = get_app_dir()
    ctx = ssl.create_default_context()

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "ffmpeg-lgpl.zip")

        req = urllib.request.Request(FFMPEG_LGPL_URL, headers={"User-Agent": "WebM-Compressor"})
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp, open(zip_path, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if cancel_flag and cancel_flag():
                    raise RuntimeError("Download cancelled.")
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb(0.9 * done / total, f"Downloading FFmpeg (LGPL)… {done // (1024*1024)} / {total // (1024*1024)} MB")

        if progress_cb:
            progress_cb(0.92, "Extracting…")

        found = {}
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                base = os.path.basename(name).lower()
                if base in WANTED_BINARIES:
                    target = os.path.join(app_dir, base)
                    with zf.open(name) as src, open(target, "wb") as dst:
                        dst.write(src.read())
                    found[base] = target

        missing = [b for b in WANTED_BINARIES if b not in found]
        if missing:
            raise RuntimeError(f"Archive did not contain: {', '.join(missing)}")

    if progress_cb:
        progress_cb(1.0, "FFmpeg ready.")
    return app_dir
