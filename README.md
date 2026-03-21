# MIRTK Installer

Pre-built conda packages for [MIRTK](https://github.com/BioMedIA/MIRTK) (Medical Image Registration ToolKit).

## Quick Install

```bash
git clone https://github.com/xiaz9n/mirtk-install.git
cd mirtk-install
bash install.sh
```

This will:
1. Check that conda is installed
2. Check your platform has a pre-built package
3. Create a dedicated `mirtk` conda environment
4. Install MIRTK and all dependencies

## Usage

```bash
conda activate mirtk
mirtk help
mirtk register --help
mirtk transform-image --help
```

## Supported Platforms

- macOS Apple Silicon (M1/M2/M3/M4) — `osx-arm64`
- Linux x86_64 — `linux-64` (coming soon)

## Requirements

- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or [Anaconda](https://www.anaconda.com/download)

## Building from Source

If your platform is not listed above, you can build from source:

```bash
git clone --recursive https://github.com/xiaz9n/MIRTK.git
cd MIRTK
conda install conda-build -y
conda build conda-recipe/mirtk --output-folder ~/conda-channel
```

See `HOW_TO_BUILD.md` for details.

## What is MIRTK?

MIRTK is a C++ toolkit for medical image registration supporting rigid, affine,
and non-rigid registration. It includes ~80 command-line tools for image processing,
surface mesh operations, and transformation utilities.
