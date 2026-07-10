# 🎬 WebM Compressor

**Compress any video to WebM (VP9 / AV1) locally — with GPU acceleration even on GPUs that "can't" hardware-encode WebM.**

Private, offline, and impossible to get a broken file out of. Free for non-commercial use.

![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Codecs](https://img.shields.io/badge/codecs-VP9%20%7C%20AV1%20%7C%20Opus-4285F4)
![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue)
![FFmpeg](https://img.shields.io/badge/FFmpeg-LGPL%20build-007808?logo=ffmpeg&logoColor=white)

<!-- Add a screenshot or GIF here — it's the single biggest driver of stars/downloads. -->
<!-- ![screenshot](docs/screenshot.png) -->

---

## ✨ Why WebM Compressor?

Great tools like HandBrake and Shutter Encoder cover every format under the sun. This app deliberately does the opposite: **one format, done exceptionally well.** Here's how it compares for the WebM job specifically:

| | 🎬 **WebM Compressor** | 🖥️ Desktop GUIs (HandBrake, …) | 🌐 Online converters |
|---|:---:|:---:|:---:|
| ⚡ GPU used on RTX 30/20, GTX, older cards | ✅ Hybrid: GPU decode + scale | ❌ Falls back to 100% CPU | ❌ Cloud queue |
| 🚀 True hardware AV1 (RTX 40+ / Arc / RX 7000+) | ✅ Auto-detected by real probe | ⚠️ Manual setup | ❌ |
| 🔒 Video stays on your PC | ✅ 100% offline | ✅ | ❌ Uploaded to a server |
| 📦 File-size limits / subscription | ✅ None, free | ✅ None | ❌ Caps & paywalls |
| 🛡️ Output verified after encode | ✅ Container + codecs re-checked | ❌ | ❌ |
| 🎨 HDR tags, VFR sync, iPhone/GoPro quirks | ✅ Handled automatically | ⚠️ Manual flags | ❌ |
| 🆓 Royalty-free codec stack (no H.264/HEVC patents) | ✅ VP9/AV1/Opus only | ⚠️ Mixed | ⚠️ Mixed |

> 💡 **Fair note:** if you need MP4/H.264 for maximum device compatibility, HandBrake is excellent — that's just not this tool's job. This is for **WebM**: the web-native, royalty-free format for embeds, Discord, and modern browsers.

## 🧠 What makes it different under the hood

- ⚡ **Hybrid GPU pipeline** — most GPUs (including NVIDIA RTX 30-series and older) can't hardware-encode VP9/AV1 at all. Instead of dropping to pure CPU like other tools, this app keeps the GPU working on **decode + scaling** (NVDEC / CUDA / QSV / D3D11VA) and runs only the encode on CPU — with automatic pure-CPU retry if any hardware step fails.
- 🖥️ **Probe, don't assume** — hardware support is detected with a real 1-frame test encode, not a device list. RTX 40+ / Intel Arc / RX 7000+ get true hardware AV1; older cards get hybrid; no-GPU machines get CPU. Zero settings to understand.
- 🛡️ **Impossible to ship a broken file** — forced `yuv420p` (no unplayable files from 4:2:2 camera footage), HDR color-tag preservation (no washed-out output), VFR-safe timestamps (no audio desync from phone recordings), safe stream mapping (iPhone/GoPro data tracks can't crash the encode), and every output is re-verified as valid WebM/VP9/AV1/Opus.
- 🧪 **Expert-tuned FFmpeg, built in** — `-b:v 0` true constant quality, alt-ref lookahead, optional two-pass VP9, SVT-AV1 speed presets, and automatic quality compensation when hardware encoders are used. Getting all of that right by hand takes days of reading encoder docs.

## 🚀 Features

- 🎯 Single-pass constant-quality (CRF) encoding to `.webm`, with optional **two-pass VP9**
- 🎞️ **VP9** (`libvpx-vp9`) and **AV1** (`libsvtav1`, speed preset exposed), audio via **Opus**
- ⚡ True hardware encoding when available (NVENC AV1, Intel QSV AV1/VP9, AMD AMF AV1, Apple VideoToolbox)
- 📊 Batch queue with live progress, speed, ETA, and **predicted output size**
- 👀 5-second middle-of-file **quality preview** before committing to an hour-long encode
- 📐 Resolution presets (1080p / 720p) and audio-only Opus WebM
- 📥 **FFmpeg auto-download on first run** — the official LGPL build, no manual setup

## 📋 Requirements

- 🪟 Windows 10/11 (primary target; Linux notes in [README_LINUX.md](README_LINUX.md))
- 🐍 Python 3.10+ only if running from source
- 🎮 GPU optional — everything works CPU-only too

FFmpeg is fetched automatically on first run (official **LGPL** build from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), ~100 MB, one time). You can also drop your own `ffmpeg.exe`/`ffprobe.exe` next to the app or use PATH. See [THIRD-PARTY-LICENSES](THIRD-PARTY-LICENSES.md).

## 📦 Install (users)

1. Grab the latest zip from [Releases](https://github.com/dimanthasehan80-blip/webm-compressor/releases)
2. Unzip and run `WebM_Compressor.exe`
3. Accept the one-time FFmpeg download prompt — done ✅

## 🛠️ Run / build from source (developers)

```bash
git clone https://github.com/dimanthasehan80-blip/webm-compressor
cd webm-compressor
pip install -r requirements.txt
python app.py                # run the app

# Build a distributable with PyInstaller:
pip install pyinstaller
pyinstaller WebM_Compressor.spec
```

> ⚠️ Do **not** commit `ffmpeg.exe`/`ffprobe.exe` — they are large, separately licensed, and fetched at first run.

## ⚙️ How it works

Input is demuxed and decoded (on GPU when possible), optionally scaled, then encoded to VP9/AV1 and muxed to `.webm` in a single pass (or two-pass for VP9). When the GPU can't hardware-encode AV1/VP9 (most GPUs — hardware AV1 encode needs RTX 40-series / Intel Arc / RX 7000+), the app runs a **hybrid** path: GPU decode + scale for sources ≥1080p, CPU encode, with pure-CPU retry on any hardware failure.

## 🤝 Contributing

Issues and pull requests are warmly welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the quick guidelines (please read the CLA note there).

## 📜 License

**PolyForm Noncommercial 1.0.0** — use, modify, and share freely for **any non-commercial purpose**. Commercial use requires a separate license from the author. See [LICENSE](LICENSE).

This is **source-available**, not OSI "open source": commercial use is restricted. FFmpeg and the codecs it uses are separately licensed — see [THIRD-PARTY-LICENSES](THIRD-PARTY-LICENSES.md).

Copyright © 2026 [dimanthasehan80-blip](https://github.com/dimanthasehan80-blip)
