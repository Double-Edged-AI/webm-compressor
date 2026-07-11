# Roadmap

Planned and considered improvements. These are directions, not commitments, and the
order may change. Suggestions are welcome via
[issues](https://github.com/Double-Edged-AI/webm-compressor/issues) and
[discussions](https://github.com/Double-Edged-AI/webm-compressor/discussions).

### Planned
- **Watch-folder automation** — drop a file into a folder and get a WebM out automatically.
- **Size-target mode** — set a target size in MB and let the app choose settings to hit it.
- **Shareable quality report** — export the VMAF/SSIM numbers per encode.

### Considering
- Portable / no-install build.
- macOS and Linux builds (Linux run notes already exist in `README_LINUX.md`).
- Additional interface languages.

### Not planned (by design)
- **MP4 / H.264 / H.265 export** — WebM-only is the entire point; use HandBrake for those.
- **A built-in video editor** — that is Shutter Encoder's domain, not this app's.
- **Any cloud upload or telemetry** — the app stays fully local, always.
