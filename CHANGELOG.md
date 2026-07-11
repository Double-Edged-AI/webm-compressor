# Changelog

All notable changes to WebM Compressor are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [semantic versioning](https://semver.org/).

## [1.0.0] — 2026-07-11

First public release.

### Added
- WebM (VP9/AV1) compression with Opus audio — one format, always re-verified as valid.
- LMS-focused presets: LMS Upload, High Quality, Balanced, Small Size, Ultra Small (Slow Internet), Experimental AV1, and Audio Only.
- Batch queue with per-video selection and drag-and-drop.
- Automatic GPU detection with CPU fallback; hybrid GPU-decode / CPU-encode mode on older cards.
- Predicted output size, per-file progress bars, ETA, and real Windows taskbar progress.
- 5-second quality preview before committing to a full encode.
- Automatic first-run download of the official LGPL FFmpeg build.
- Post-encode re-verification that every output is a valid WebM container/codec.
- HDR color-tag preservation and safe timestamp handling for variable-framerate recordings.

[1.0.0]: https://github.com/Double-Edged-AI/webm-compressor/releases/tag/v1.0.0
