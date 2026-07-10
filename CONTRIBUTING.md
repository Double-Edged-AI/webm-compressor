# Contributing to WebM Compressor

Thanks for your interest in contributing!

## License of contributions (please read)

This project is **source-available** under the [PolyForm Noncommercial 1.0.0](LICENSE)
license, and the author retains the right to offer commercial licenses.

To keep that possible, **by submitting a pull request you agree that:**

1. You are the original author of your contribution (or have the right to submit it), and
2. You grant the project author (**dimanthasehan80-blip**) a perpetual, worldwide,
   irrevocable license to use, modify, sublicense, and **relicense** your contribution,
   including under commercial terms.

This lightweight Contributor License Agreement (CLA) lets the author dual-license or
commercialize the project in the future without needing to track down every contributor.
If you are not comfortable with this, please open an issue to discuss before submitting
code.

## How to contribute

1. Open an issue describing the bug or feature first, so we can agree on the approach.
2. Fork the repo and create a branch: `git checkout -b fix/short-description`
3. `pip install -r requirements.txt`, make your change, and test with `python app.py`.
4. Keep PRs focused and small; match the existing code style.
5. Reference the issue in your PR description.

## Good first areas

- Additional GPU vendor coverage (AMD hybrid decode, VideoToolbox refinements)
- Chunked/scene-split parallel encoding for higher CPU throughput
- Size-target mode ("fit under N MB") using two-pass ABR
- UX: drag-and-drop, watch folders, more presets

## Reporting bugs

Include: OS version, GPU model, the input file's codec/resolution, the exact settings used,
and the FFmpeg command the app printed to the console (and its error output, if any).
