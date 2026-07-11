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

## Known differences on Linux

- No automatic FFmpeg download: install it with your package manager (step 1).
- No taskbar progress: that uses a Windows API and is skipped elsewhere.
- The frameless rounded window relies on Windows-specific behavior; on Linux
  the window may appear with a standard frame or without rounded corners
  depending on your desktop environment.
- GPU acceleration depends on your distribution's FFmpeg build having the
  relevant hardware encoders/decoders compiled in (VAAPI on most systems).
  The app falls back to CPU encoding automatically either way.
- Output is WebM-only on every platform. That rule does not change.
