# WebM Compressor

> **Free for non-commercial use.** A Windows desktop app that compresses video to **WebM (VP9 / AV1)** with a single-pass, GPU-assisted FFmpeg pipeline. Source-available under [PolyForm Noncommercial 1.0.0](LICENSE) — see [License](#license).

<!-- Add a screenshot or GIF here — it's the single biggest driver of stars/downloads. -->
<!-- ![screenshot](docs/screenshot.png) -->

## Why this exists

There are plenty of FFmpeg front-ends. This one focuses on **WebM done well**:

- **Hybrid GPU acceleration** — even on GPUs that *can't* hardware-encode AV1 (e.g. NVIDIA RTX 30-series and older), it still uses the GPU for **decode + scaling** (NVDEC / CUDA / QSV / D3D11VA) and only runs the AV1/VP9 encode on the CPU. You get GPU speedups where your hardware allows them, and correct output where it doesn't — with automatic pure-CPU fallback if anything fails.
- **Royalty-free stack** — VP9, AV1, and Opus only. No H.264/HEVC patent baggage.
- **Correct output by default** — forced `yuv420p` (10-bit opt-in), HDR color-tag preservation, VFR-safe timestamps, WebM-only container enforcement with post-encode verification.

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
