# Changelog

All notable changes to WebM Compressor are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [semantic versioning](https://semver.org/).

## [1.2.0] - 2026-07-14

### Added
- Per-file compression settings: every queued video keeps its own profile, quality, engine, two-pass, 10-bit, fps-cap and AV1 settings. Click a row to edit that file's settings in the sidebar; press Escape or "done" to return to editing the defaults applied to newly added files.
- "Apply These Settings to All Files" button for one-click batch stamping.
- Per-row settings chip showing each file's plan at a glance (profile, CRF, passes, engine).
- Per-file preview: the 5-second sample uses that file's own settings and now also reports an estimated encode time measured from the sample.
- Destination preflight before compression: free-space check against the estimated output of all selected files (with a friendly choose-another-folder / continue / cancel dialog), write-permission probe, and long-path warning.
- Queue persistence: the queue and every file's individual settings are restored (on request) when the app reopens.

### Changed
- Start-time warnings (10-bit on 8-bit sources, two-pass on large files, already-compressed inputs, GPU honesty) are now evaluated per file against that file's own settings.
- Queue rows can be reordered with per-row up/down arrows or Ctrl+Up/Down on the selected row; encode order follows queue order.
- System Details diagnostics now explain WHY GPU WebM encoding is or is not available and recommend the best engine for the detected hardware.

### Fixed
- GPU AV1 encoder detection: the capability probe encoded a 64x64 test frame, below NVENC's minimum supported frame size, so real hardware AV1 encoders (RTX 40-series, Intel Arc, AMD RX 7000) were never detected. The probe now uses a 256x256 frame.

## [1.1.0] - 2026-07-14

### Added
- Four engine modes: CPU, GPU, Hybrid (GPU decode + CPU encode) and Auto. The selected engine changes the real FFmpeg command; queue rows show which mode Auto resolved to.
- True pause/resume for running compressions (OS-level process suspension - no CPU/GPU use while paused, output cannot be corrupted).
- Two-pass analysis pass now has its own full progress bar, elapsed time and ETA, plus an explanation that encoding starts in pass 2.
- GPU compatibility popup with a clickable link to the README hardware guide when selecting GPU or Hybrid.
- Staged GPU diagnostics in the System Details dialog (driver, decode runtime, FFmpeg hwaccels, working WebM encoders, hybrid readiness) with Ubuntu fix hints.
- Pipeline dialog shows hardware-activity proof captured from the last job's FFmpeg log.
- Startup splash screen: appears the instant the exe launches and closes when the dashboard is ready.

### Changed
- ETA is now computed from FFmpeg's real encode speed with rolling-average smoothing, shown per pass, and displays "Estimating..." until it is reliable instead of a wrong number.
- Quality preview now uses the exact final job settings, including two-pass, engine mode and the 30fps cap, and labels its size estimate as approximate.
- Elapsed time is shown for every running and finished job.
- Minimize and restore now use the native Windows animations (the window is managed by Windows with only the title bar stripped).
- Faster startup: FFmpeg checks and GPU detection run in the background after the window opens.

### Fixed
- Ubuntu GPU detection: first-run hardware probes now allow up to 20 seconds for cold CUDA/driver initialization (previously 2-4s, causing false CPU fallbacks) and results are cached.
- Two-pass ETA no longer assumes both passes run at the same speed.
- Estimated output size during two-pass encoding no longer doubles the real value.
- Sidebar no longer reports "GPU: Unsupported (CPU Fallback)" on systems where hybrid GPU decoding is active.
- App icon is no longer clipped at the bottom in the taskbar, window title bar and File Explorer; the icon now ships in all standard sizes (16 to 256 px).

## [1.0.1] - 2026-07-11

### Changed
- Up to 1.6x faster VP9 encoding on multi-core CPUs (same quality and output size).
- Smoother interface while a compression is running.
- More reliable handling of very large files.

## [1.0.0] - 2026-07-11

First public release.

### Added
- WebM (VP9/AV1) compression with Opus audio: one format, always re-verified as valid.
- LMS-focused presets: LMS Upload, High Quality, Balanced, Small Size, Ultra Small (Slow Internet), Experimental AV1, and Audio Only.
- Batch queue with per-video selection and drag-and-drop.
- Automatic GPU detection with CPU fallback; hybrid GPU-decode / CPU-encode mode on older cards.
- Predicted output size, per-file progress bars, ETA, and real Windows taskbar progress.
- 5-second quality preview before committing to a full encode.
- Automatic first-run download of the official LGPL FFmpeg build.
- Post-encode re-verification that every output is a valid WebM container/codec.
- HDR color-tag preservation and safe timestamp handling for variable-framerate recordings.

[1.2.0]: https://github.com/Double-Edged-AI/webm-compressor/releases/tag/v1.2.0
[1.1.0]: https://github.com/Double-Edged-AI/webm-compressor/releases/tag/v1.1.0
[1.0.1]: https://github.com/Double-Edged-AI/webm-compressor/releases/tag/v1.0.1
[1.0.0]: https://github.com/Double-Edged-AI/webm-compressor/releases/tag/v1.0.0
