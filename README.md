# WebM Compressor

> **Free for non-commercial use.** A Windows desktop app that compresses video to **WebM (VP9 / AV1)** with a single-pass, GPU-assisted FFmpeg pipeline. Source-available under [PolyForm Noncommercial 1.0.0](LICENSE) — see [License](#license).

<!-- Add a screenshot or GIF here — it's the single biggest driver of stars/downloads. -->
<!-- ![screenshot](docs/screenshot.png) -->

## Why this exists

There are plenty of FFmpeg front-ends and online converters. This one focuses on **WebM done well** — here's what it does that the others don't:

> *The only WebM compressor that uses your GPU even when your GPU "can't" — private, local, and impossible to get a broken file out of.*

### 🆚 vs. HandBrake / Shutter Encoder / VidCoder

- 🎯 **Does one thing perfectly** — WebM only. No confusing wall of 50 formats and codecs, and you can't produce a broken or wrong-format file: every output is re-verified as valid WebM/VP9/AV1/Opus after encoding.
- ⚡ **Hybrid GPU pipeline (the killer feature)** — on GPUs that *can't* hardware-encode AV1/VP9 (that's most GPUs, including NVIDIA RTX 30-series and older), other tools silently fall back to 100% CPU. This app still uses the GPU for **decode + scaling** (NVDEC / CUDA / QSV / D3D11VA) and only runs the encode on the CPU — with automatic pure-CPU retry if anything fails.
- 🖥️ **Smart hardware detection** — it *probes* your GPU with a real test encode instead of trusting a device list. RTX 40+ / Intel Arc / RX 7000+ get true hardware AV1; older cards get hybrid; no-GPU machines get CPU. Zero settings to understand.
- 🎨 **Correctness that free tools get wrong** — forced `yuv420p` (no unplayable files from 4:2:2 camera footage), HDR color-tag preservation (no washed-out output), VFR-safe timestamps (no audio desync from phone recordings), safe stream mapping (iPhone/GoPro files with data tracks don't crash the encode).

### 🌐 vs. online converters (CloudConvert, FreeConvert, …)

- 🔒 **100% local & private** — your video never leaves your PC. No uploading personal or client footage to someone else's server.
- 💸 **No file-size limits, no queues, no subscription** — online tools cap free files and throttle you.
- 🚀 **Faster for real files** — no upload/download time; a 4 GB video starts compressing instantly.

### ⌨️ vs. raw FFmpeg on the command line

- 🧠 **Expert-tuned commands built in** — `-b:v 0` true constant quality, lag-in-frames/alt-ref lookahead, two-pass VP9, SVT-AV1 speed presets, and automatic quality compensation when hardware encoders are used. Getting all of that right by hand takes days of reading docs.
- 📊 **Live progress, ETA, predicted file size, batch queue**, and a 5-second preview before you commit to an hour-long encode.

### 📜 The legal angle

- 🆓 **Fully royalty-free stack** — VP9, AV1, and Opus only. No H.264/HEVC patent baggage, and the auto-downloaded FFmpeg build is LGPL, keeping distribution clean.

## Features

- Single-pass constant-quality (CRF) encoding to `.webm`, with optional **two-pass VP9**
- Codecs: **VP9** (`libvpx-vp9`) and **AV1** (`libsvtav1`, speed preset exposed), audio via **Opus**
- True hardware encoding when available (NVENC AV1 on RTX 40+, Intel QSV AV1/VP9, AMD AMF AV1, Apple VideoToolbox) with automatic quality compensation
- Batch queue with progress, speed, ETA, and estimated output size
- 5-second middle-of-file quality preview before committing to a full encode
- Resolution scaling presets (1080p / 720p) and audio-only Opus WebM

## Requirements

- Windows 10/11 (primary target; a Linux note is in [README_LINUX.md](README_LINUX.md))
- Python 3.10+ if running from source
- A GPU is optional — the app runs CPU-only when no acceleration is available

**FFmpeg is downloaded automatically on first run** (the official **LGPL** build from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), ~100 MB, one time). You can also place your own `ffmpeg.exe`/`ffprobe.exe` next to the app, or have FFmpeg on PATH. See [THIRD-PARTY-LICENSES](THIRD-PARTY-LICENSES.md).

## Install (users)

Download the latest release from the [Releases](https://github.com/dimanthasehan80-blip/webm-compressor/releases) page, unzip, and run `WebM_Compressor.exe`. On first run, accept the FFmpeg download prompt.

## Run / build from source (developers)

```bash
git clone https://github.com/dimanthasehan80-blip/webm-compressor
cd webm-compressor
pip install -r requirements.txt
python app.py                # run the app

# Build a distributable with PyInstaller:
pip install pyinstaller
pyinstaller WebM_Compressor.spec
```

> Do **not** commit `ffmpeg.exe`/`ffprobe.exe` to the repository — they are large, separately licensed, and fetched at first run.

## How it works

Input is demuxed and decoded (on GPU when possible), optionally scaled, then encoded to VP9/AV1 and muxed to `.webm` in a single pass (or two-pass for VP9). When the GPU can't hardware-encode AV1/VP9 (most GPUs — hardware AV1 encode needs RTX 40-series / Intel Arc / RX 7000+), the app runs a **hybrid** path: GPU decode + scale for sources ≥1080p, CPU encode, with pure-CPU retry on any hardware failure.

## License

**PolyForm Noncommercial 1.0.0** — you may use, modify, and share this software for **any non-commercial purpose**. Commercial use requires a separate license from the author. See [LICENSE](LICENSE).

This is **source-available**, not OSI "open source": commercial use is restricted. FFmpeg and the codecs it uses are separately licensed — see [THIRD-PARTY-LICENSES](THIRD-PARTY-LICENSES.md).

Copyright (c) 2026 [dimanthasehan80-blip](https://github.com/dimanthasehan80-blip)
