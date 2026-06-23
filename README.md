# MIRTK Installer

Self-contained installer for [MIRTK](https://github.com/BioMedIA/MIRTK) (Medical
Image Registration ToolKit) plus the `mirtk-pipeline` registration/analysis
tools. Ships a pre-built conda package, so no compilation is needed on supported
platforms.

> ✅ **Viewer included.** The bundled Linux (`linux-64`) binary is built **with
> the FLTK/OpenGL viewer**, so `mirtk view` works out of the box (it links
> `libfltk`, `libGL`, and `libX11`). The ~11 MB package is committed to this
> repo, so a fresh `git clone` of `main` pulls the complete viewer-enabled
> binary — no separate download or build step. A graphical display is required
> to use the viewer (local desktop, `ssh -X`, or VNC).

> **Linux users: install from `main`.** The `main` branch is the current,
> full-featured build — it includes the viewer-enabled MIRTK binary **and** the
> `mirtk-pipeline` / `csa-slicer` tools and tab completion. (The older
> `viewer-for-linux` / `viewer-for-mac` branches contain only the bare MIRTK
> binary and are kept for reference.)

## Supported Platforms

| Platform | Pre-built package on `main` | Notes |
|----------|:--------------------------:|-------|
| Linux x86_64 (Ubuntu, CentOS, etc.) | ✅ `linux-64` | Recommended. Viewer + FLTK included. |
| macOS Apple Silicon (M1–M4) | ✅ `osx-arm64` | Works, but for the FLTK viewer use the [`viewer-for-mac`](https://github.com/kiwixiao/mirtk-install/tree/viewer-for-mac) branch. |
| Other (Intel Mac, Windows, …) | ❌ | Build from source — see [Building from Source](#building-from-source). |

## Quick Install (Linux x86_64)

**Requirements:** [Miniconda or Anaconda](https://docs.conda.io/en/latest/miniconda.html),
`git`, and network access during install (the `csa-slicer` package is pulled
from GitHub).

```bash
# 1. Clone the main branch (default)
git clone https://github.com/kiwixiao/mirtk-install.git
cd mirtk-install

# 2. Run the installer
bash install.sh

# 3. Activate and use
conda activate mirtk
mirtk help
mirtk-pipeline --help
```

`install.sh` will:

1. Check that conda is installed and detect your platform.
2. Create a dedicated `mirtk` conda environment from the bundled pre-built package.
3. Verify the MIRTK binary (`mirtk help`).
4. Install the `mirtk-pipeline` Python package (`mirtk-pipeline`, `mirtk-register-seq`, etc.).
5. Install the `csa-slicer` package (`csa-legacy`, `csa-bifurcation`, `csa-aortic`).

## Usage

```bash
conda activate mirtk

# MIRTK toolkit
mirtk help
mirtk register --help
mirtk transform-image --help
mirtk view image.nii.gz          # FLTK viewer (Linux/main build)

# Pipeline tools
mirtk-pipeline --help            # registration pipeline (interactive or CLI)
mirtk-prepare-slicer --help
```

## Tab completion (optional)

Argument completion for the `mirtk-*` commands is available via `argcomplete`
but must be registered in your shell once. Add this to `~/.bashrc`:

```bash
for c in mirtk-pipeline mirtk-prepare-slicer mirtk-postprocess mirtk-register-seq \
         mirtk-interpolate mirtk-decimate mirtk-scale-stl mirtk-preprocess \
         mirtk-visualize mirtk-nifti-slices; do
    eval "$(register-python-argcomplete "$c" 2>/dev/null)"
done
```

Then `conda activate mirtk` and open a new shell. Completion fires only while the
`mirtk` env is active. (File-path completion at the pipeline's *interactive*
prompts works automatically — no setup needed.)

## Troubleshooting

**`Could not solve for environment specs` / `mirtk requires fltk >=1.3.10 ...`**

The bundled local channel ships only the `mirtk` package — its dependencies
(`fltk`, `vtk`, `mesalib`, `tbb`, xorg libs, …) come from **conda-forge**. This
happens when conda-forge isn't used for the solve. `install.sh` handles it
automatically, but if you installed manually or have an older clone, create the
env with conda-forge forced:

```bash
conda create -n mirtk --override-channels -c conda-forge -c "file://$(pwd)/packages" mirtk -y
conda activate mirtk
pip install .
pip install "csa-slicer @ git+https://github.com/kiwixiao/csa.git#subdirectory=python_slicer"
```

## Building from Source

If your platform has no pre-built package, build the conda package from source
using the recipe in this repo:

```bash
conda install conda-build -y
conda build conda-recipe/mirtk --output-folder ~/conda-channel
conda create -n mirtk -c ~/conda-channel mirtk -y
conda activate mirtk
pip install .                    # install the mirtk-pipeline package
```

See [`conda-recipe/mirtk/HOW_TO_BUILD.md`](conda-recipe/mirtk/HOW_TO_BUILD.md)
for details. The MIRTK C++ sources are vendored under [`mirtk-source/`](mirtk-source/).

## What is MIRTK?

MIRTK is a C++ toolkit for medical image registration supporting rigid, affine,
and non-rigid registration. It includes ~80 command-line tools for image processing,
surface mesh operations, and transformation utilities.

## Credits

MIRTK was originally developed by [Andreas Schuh](https://github.com/schuhschuh)
at Imperial College London. The original source code is available at
[BioMedIA/MIRTK](https://github.com/BioMedIA/MIRTK).

This repository provides conda packaging with patches for modern toolchain
compatibility (CMake 4.x, Eigen 3.4+, VTK 9.x, TBB 2022+).

## License

MIRTK is licensed under the [Apache License 2.0](https://github.com/BioMedIA/MIRTK/blob/master/LICENSE.txt).
