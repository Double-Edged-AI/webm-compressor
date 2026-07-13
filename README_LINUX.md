# WebM Compressor - Linux Setup Guide

The app is developed and tested on Windows first. It runs on Linux from source,
but treat it as experimental: a few Windows-specific comforts are absent there
(details at the bottom). This guide covers Ubuntu and derivatives; adjust the
package commands for other distributions.

## 1. System packages

Ubuntu does not bundle Tkinter with python3, and on Linux you install FFmpeg
yourself (the automatic FFmpeg download in the app is Windows-only):

```bash
sudo apt update
sudo apt install -y python3-tk ffmpeg
```

`ffprobe` comes inside the `ffmpeg` package; it is not a separate package.
Any FFmpeg 5 or newer from the standard repositories works. Only on very old
Ubuntu releases would you need a newer-FFmpeg PPA.

## 2. Python dependencies

The same `requirements.txt` is used on every platform:

```bash
pip install -r requirements.txt
```

What gets installed where:

| Package | Windows | Linux | Purpose |
|---|---|---|---|
| customtkinter | yes | yes | the UI toolkit |
| pillow | yes | yes | icons and image handling |
| tkinterdnd2 | yes | yes | drag and drop |
| comtypes | yes | skipped automatically | Windows taskbar progress only |

## 3. Run from source

```bash
git clone https://github.com/Double-Edged-AI/webm-compressor
cd webm-compressor
pip install -r requirements.txt
python3 app.py
```

## 4. Optional: portable build with PyInstaller

```bash
pip install pyinstaller
pyinstaller WebM_Compressor.spec --noconfirm
tar -czvf WebM_Compressor_Linux.tar.gz dist/WebM_Compressor/
```

The build uses the system `ffmpeg`/`ffprobe` from your PATH. You can also copy
them next to the executable if you want a self-contained folder. Do not
redistribute FFmpeg builds without checking their license notes (see
THIRD-PARTY-LICENSES.md).

## GPU acceleration on Ubuntu (NVIDIA)

GPU acceleration needs three things; if any one is missing the app quietly
falls back to CPU. The app's ⓘ System Details dialog runs these exact checks
and tells you which step failed.

1. **NVIDIA driver with the video libraries.** The decode library
   `libnvcuvid.so.1` ships in the `libnvidia-decode-*` package (part of the
   standard driver, NOT part of CUDA):

   ```bash
   nvidia-smi                          # driver present?
   ldconfig -p | grep libnvcuvid       # decode runtime present?
   sudo apt install libnvidia-decode-$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | cut -d. -f1)
   ```

2. **An FFmpeg build with NVDEC support.** The apt FFmpeg on Ubuntu 20.04+
   includes it. The snap FFmpeg does NOT. If `ffmpeg -hwaccels` does not list
   `cuda`, install FFmpeg from apt or use a
   [BtbN static build](https://github.com/BtbN/FFmpeg-Builds/releases).

3. **Patience on first run.** The first CUDA initialization after boot can take
   several seconds; the app allows up to 20 seconds for the first GPU probe and
   caches the result.

Note that NVIDIA cards cannot encode VP9 at all, and AV1 encoding needs an
RTX 40-series or newer. On most NVIDIA cards the best real mode is therefore
**Hybrid** (GPU decodes and scales, CPU encodes WebM), which the Auto engine
picks for 1080p+ sources automatically. Intel iGPU/Arc systems can use VAAPI
or Quick Sync the same way. See the main README's
"GPU acceleration & supported hardware" section for the full engine-mode table.

## Known differences on Linux

- No automatic FFmpeg download: install it with your package manager (step 1).
- No taskbar progress: that uses a Windows API and is skipped elsewhere.
- The frameless rounded window relies on Windows-specific behavior; on Linux
  the window may appear with a standard frame or without rounded corners
  depending on your desktop environment.
- Pause/resume works on Linux too (SIGSTOP/SIGCONT instead of the Windows API).
- Output is WebM-only on every platform. That rule does not change.
