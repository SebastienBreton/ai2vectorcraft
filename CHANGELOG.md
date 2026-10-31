# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-31

### Added

- Convert `.ai` files to `.vectorcraft` by driving VectorCraft's control port.
- Read Illustrator's `AIPrivateData` (Zstandard and zlib).
- Fix the positions of linked images that Illustrator writes wrongly in the PDF part, artboard by artboard.
- `--outdir`, `--port` and `--keep-pdf` options, and the `VECTORCRAFT_BIN` environment variable.
