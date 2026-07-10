# Third-Party Licenses & Attribution

WebM Compressor uses third-party software. This file documents that software and its licenses.

## FFmpeg

This application uses **FFmpeg** (<https://ffmpeg.org>) to decode, scale, encode, and mux
media. FFmpeg is **not** distributed as part of this repository. On first run, the
application downloads the prebuilt **LGPL-licensed** FFmpeg build published by
[BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds)
(`ffmpeg-master-latest-win64-lgpl.zip`) into the application directory, and invokes it as
a **separate process** (it is not statically or dynamically linked into the application).

- The build used is licensed under the **GNU Lesser General Public License (LGPL) v2.1 or
  later**. Some FFmpeg builds are GPL; this application intentionally fetches an **LGPL**
  build so no GPL obligations attach to the application.
- FFmpeg source code and license details: <https://ffmpeg.org/legal.html> and the
  corresponding source published alongside each BtbN build.
- The LGPL grants you the right to obtain the FFmpeg source and to replace the FFmpeg
  binary this application uses with your own compatible build (place your own
  `ffmpeg.exe`/`ffprobe.exe` next to the app, or put them on PATH).

> **If you redistribute a bundle that includes `ffmpeg.exe`:** include the FFmpeg LGPL
> license text alongside the binary and a link to its corresponding source. Do not bundle
> a GPL ("full") FFmpeg build with this application.

## Codecs & libraries (within the FFmpeg build)

| Component | Purpose | License |
|-----------|---------|---------|
| libvpx (VP9) | VP9 video encoding | BSD-3-Clause |
| SVT-AV1 (libsvtav1) | AV1 video encoding | BSD-3-Clause-Clear / AOM patent grant |
| libopus | Opus audio encoding | BSD-3-Clause |
| NVIDIA NVDEC/NVENC (ffnvcodec headers) | GPU decode/encode | MIT (headers); runtime requires NVIDIA drivers |
| Intel libvpl (QSV) | GPU decode/encode | MIT |

VP9, AV1, and Opus are **royalty-free**. This application does not use H.264 or H.265/HEVC,
which carry patent-licensing obligations.

## Python dependencies

| Package | Purpose | License |
|---------|---------|---------|
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | GUI toolkit | MIT |
| [Pillow](https://python-pillow.org/) | Image handling | MIT-CMU (HPND) |

Distributable builds are produced with [PyInstaller](https://pyinstaller.org) (GPL 2.0 with
a bootloader exception that explicitly permits distributing packaged applications under
any license).

---

*If you redistribute this application, keep this file intact and ensure the FFmpeg LGPL
notice reaches end users.*
