# MIRTK Installer

Pre-built conda packages for [MIRTK](https://github.com/BioMedIA/MIRTK) (Medical Image Registration ToolKit).

## Quick Install

```bash
git clone https://github.com/kiwixiao/mirtk-install.git
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

| Platform | Status | Package |
|----------|--------|---------|
| macOS Apple Silicon (M1/M2/M3/M4) | Available | `packages/osx-arm64/` |
| Linux x86_64 (Ubuntu, CentOS, etc.) | Coming soon | `packages/linux-64/` |

## Requirements

- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or [Anaconda](https://www.anaconda.com/download)

## Building from Source

If your platform is not listed above, you can build from source using the
[MIRTK source repo](https://github.com/kiwixiao/MIRTK):

```bash
git clone --recursive https://github.com/kiwixiao/MIRTK.git
cd MIRTK
conda install conda-build -y
conda build conda-recipe/mirtk --output-folder ~/conda-channel
```

## What is MIRTK?

MIRTK is a C++ toolkit for medical image registration supporting rigid, affine,
and non-rigid registration. It includes ~80 command-line tools for image processing,
surface mesh operations, and transformation utilities.
