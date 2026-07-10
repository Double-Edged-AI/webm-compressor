# Double-Edged AI Video Compressor - Linux Ubuntu Setup Guide

This guide describes how to run and package the compressor application on Linux Ubuntu.

---

## 1. Prerequisites

Unlike Windows, Ubuntu does not bundle the Tkinter graphical library with python3. You must install it manually along with FFmpeg.

Open a terminal and run:

```bash
sudo apt update
sudo apt install -y python3-tk ffmpeg ffprobe
```

---

## 2. Running From Source

1. Clone or copy the application folder to your Ubuntu machine.
2. Open a terminal in the folder directory.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Launch the application:
   ```bash
   python3 app.py
   ```

---

## 3. Creating a Portable Executable Build

To package the application into a standalone folder that you can run on any Ubuntu machine (with the system packages installed), use **PyInstaller**:

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Build the app bundle:
   ```bash
   pyinstaller --noconfirm --onedir --windowed --name="WebM_Compressor" --add-data "$(python3 -c 'import customtkinter; print(customtkinter.__path__[0])'):customtkinter/" app.py
   ```
3. Copy the compiled binaries to the build directory (optional, or let the app fallback to the system-installed `/usr/bin/ffmpeg` and `/usr/bin/ffprobe`):
   ```bash
   cp /usr/bin/ffmpeg /usr/bin/ffprobe dist/WebM_Compressor/
   ```
4. Compress and distribute the build:
   ```bash
   tar -czvf WebM_Compressor_Linux.tar.gz dist/WebM_Compressor/
   ```

To run the built app, double-click `dist/WebM_Compressor/WebM_Compressor` or launch it via the terminal:
```bash
./dist/WebM_Compressor/WebM_Compressor
```
