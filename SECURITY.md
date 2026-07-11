# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |

Only the latest release is supported with security fixes.

## Reporting a Vulnerability

If you find a security issue in WebM Compressor, please report it privately
rather than opening a public issue:

- Use GitHub's private vulnerability reporting on this repository
  (Security tab, then "Report a vulnerability"), or
- Email dimanthasehan80@gmail.com with the details.

Please include what you found, steps to reproduce it, and the app version.
You can expect an acknowledgement within a few days. Please give us a
reasonable amount of time to fix the issue before disclosing it publicly.

## Scope notes

- The app runs entirely offline. Its only network activity is the optional
  one-time FFmpeg download from the official BtbN/FFmpeg-Builds GitHub
  releases on first run.
- The app never uploads your videos or any telemetry.
- FFmpeg itself is a third-party project; vulnerabilities in FFmpeg should be
  reported upstream at https://ffmpeg.org/security.html. We will still ship
  updated builds when relevant fixes are released.
