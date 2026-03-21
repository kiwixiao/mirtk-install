# How to Build the MIRTK Conda Package

## What is this?

A conda recipe that builds MIRTK (Medical Image Registration ToolKit) from source.
MIRTK is a C++ toolkit for medical image registration (rigid, affine, non-rigid).
The upstream repo (github.com/BioMedIA/MIRTK) is unmaintained since 2019 and fails
with modern CMake, Eigen, VTK, and TBB. This recipe includes 4 patches that fix those
issues.

## What the recipe does

1. Clones MIRTK from GitHub (with submodules)
2. Applies 4 patches for modern toolchain compatibility
3. Builds with CMake + make
4. Installs the `mirtk` CLI, ~80 tool executables, 7 shared libraries, and a Python module

## Prerequisites

Install conda-build:
```bash
conda install conda-build
```

## Build (one command)

```bash
conda build conda-recipe/mirtk --output-folder ~/conda-channel
```

This works on any platform:
- Apple Silicon Mac (osx-arm64)
- x86_64 Linux (linux-64)
- ARM64 Linux (linux-aarch64)

conda-build auto-detects the platform and uses the correct compilers.
The build takes a while (~10-20 min) because it compiles VTK-linked C++ code.

## After building

Index the channel so conda can find the package:
```bash
conda index ~/conda-channel
```

## Install the package

```bash
conda install -c file://$HOME/conda-channel mirtk
```

## Verify

```bash
mirtk help
mirtk info
mirtk register --help
```

## Multi-platform channel

If you build on multiple machines (e.g., Mac + Linux), copy the platform
subdirectories into one channel directory:

```
~/conda-channel/
  linux-64/
    mirtk-*.tar.bz2
  osx-arm64/
    mirtk-*.tar.bz2
```

Then run `conda index ~/conda-channel` once and both platforms can install from it.

## What the 4 patches fix

1. **cmake-minimum-version-3.5** — Bumps cmake_minimum_required from 2.8.12/3.4 to 3.5
   across 7 files. Required because CMake 3.27+ deprecated old policy versions.

2. **cxx14-standard** — Changes C++ standard from C++11 to C++14 in BasisProject.cmake.
   Required for Eigen 3.4+.

3. **eigen3-version-fallback** — Adds Eigen 5.x version detection to FindEigen3.cmake.
   Eigen 5.x moved version defines to a different header file.

4. **tbb-stub-targets** — Creates stub TBB::tbbmalloc targets in FindTBB.cmake.
   Prevents target conflict when VTK 9.x ships its own TBBConfig.cmake.
