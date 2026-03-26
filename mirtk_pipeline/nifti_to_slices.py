#!/usr/bin/env python

import argparse
import numpy as np
from pathlib import Path
import SimpleITK as sitk
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def nifti_to_png_slices(nifti_path, output_dir, prefix="slice"):
    """Convert a 4D NIfTI image to PNG slices in x/y/z directions.

    Replaces med2image --reslice functionality using SimpleITK + matplotlib.
    """
    img = sitk.ReadImage(str(nifti_path))
    arr = sitk.GetArrayFromImage(img)

    # For 4D: shape is (t, z, y, x)
    # For 3D: shape is (z, y, x) — wrap in extra dim
    if arr.ndim == 3:
        arr = arr[np.newaxis, ...]

    nt, nz, ny, nx = arr.shape

    # Create output directories
    for axis in ("x", "y", "z"):
        Path(output_dir, axis).mkdir(parents=True, exist_ok=True)

    for t in range(nt):
        vol = arr[t]
        # Normalize volume to [0, 1] for consistent PNG output
        vmin, vmax = vol.min(), vol.max()
        if vmax > vmin:
            vol_norm = (vol - vmin) / (vmax - vmin)
        else:
            vol_norm = np.zeros_like(vol, dtype=float)

        # z-slices (axial)
        for s in range(nz):
            out_path = Path(output_dir, "z", "{}_t{:03d}_slice{:03d}.png".format(prefix, t, s))
            plt.imsave(str(out_path), vol_norm[s, :, :], cmap="gray", vmin=0, vmax=1)

        # y-slices (coronal)
        for s in range(ny):
            out_path = Path(output_dir, "y", "{}_t{:03d}_slice{:03d}.png".format(prefix, t, s))
            plt.imsave(str(out_path), vol_norm[:, s, :], cmap="gray", vmin=0, vmax=1)

        # x-slices (sagittal)
        for s in range(nx):
            out_path = Path(output_dir, "x", "{}_t{:03d}_slice{:03d}.png".format(prefix, t, s))
            plt.imsave(str(out_path), vol_norm[:, :, s], cmap="gray", vmin=0, vmax=1)

    print("Generated PNG slices: {}t x ({}z + {}y + {}x) = {} files".format(
        nt, nz, ny, nx, nt * (nz + ny + nx)
    ))


def main():
    parser = argparse.ArgumentParser(
        description="Convert NIfTI to PNG slices in x/y/z directions (replaces med2image --reslice)"
    )
    parser.add_argument("-i", "--input", required=True, help="Input NIfTI file (.nii or .nii.gz)")
    parser.add_argument("-d", "--output-dir", required=True, help="Output directory for PNG slices")
    parser.add_argument("-o", "--prefix", default="slice", help="Filename prefix for slices (default: slice)")
    args = parser.parse_args()

    nifti_to_png_slices(args.input, args.output_dir, args.prefix)


if __name__ == "__main__":
    main()
