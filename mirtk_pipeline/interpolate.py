#!/usr/bin/env python

import argparse
import csv
import numpy as np
import os
from pathlib import Path
import pandas as pd
import scipy.ndimage
import scipy.interpolate
import SimpleITK as sitk
from concurrent.futures import ThreadPoolExecutor, as_completed
from subprocess import check_call
from tempfile import mkstemp
from typing import Optional
from vtk import vtkSTLReader, vtkSTLWriter, vtkPoints, vtkPolyData
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy
import warnings


warnings.simplefilter(action="ignore", category=FutureWarning)


# deform_mesh function may not give correct result, use
# "mirtk transform-points" instead by setting this to True
use_mirtk_transform_points = True


def farthest_point_sample(points, n_samples):
    """Select n_samples points maximally spread across the surface via FPS.

    Guarantees spatially-uniform coverage of the mesh surface.
    Used for downsampling the star table while preserving shape representation.
    """
    n = points.shape[0]
    if n_samples >= n:
        return np.arange(n)
    selected = np.zeros(n_samples, dtype=int)
    distances = np.full(n, np.inf)
    selected[0] = 0
    for i in range(1, n_samples):
        dist = np.linalg.norm(points - points[selected[i - 1]], axis=1)
        distances = np.minimum(distances, dist)
        selected[i] = np.argmax(distances)
        if (i + 1) % 1000 == 0:
            print("  FPS: {}/{} points selected".format(i + 1, n_samples))
    return np.sort(selected)


def rotation_matrix(target: sitk.Image) -> np.ndarray:
    """Image rotation matrix."""
    return np.array(target.GetDirection()).reshape(3, 3)


def inverse_rotation_matrix(target: sitk.Image) -> np.ndarray:
    """Image rotation matrix."""
    return rotation_matrix(target).T


def scaling_matrix(target: sitk.Image) -> np.ndarray:
    """Image scaling matrix."""
    return np.diag(target.GetSpacing())


def inverse_scaling_matrix(target: sitk.Image) -> np.ndarray:
    """Image scaling matrix."""
    return np.diag([1 / s for s in target.GetSpacing()])


def image_translation(target: sitk.Image) -> np.ndarray:
    """Image translation vector."""
    return np.array(target.GetOrigin())


def transform(
    points: np.ndarray,
    matrix: Optional[np.ndarray] = None,
    translation: Optional[np.ndarray] = None,
):
    """Apply affine transformation to list of points."""
    assert points.ndim == 2
    assert points.shape[1] == 3
    if matrix is not None:
        y = np.matmul(points, matrix.T)
    else:
        y = points.copy()
    if translation is not None:
        y += np.expand_dims(translation, axis=0)
    assert y.ndim == 2
    assert y.shape == points.shape
    return y


def voxel_to_world(target: sitk.Image, points: np.ndarray) -> np.ndarray:
    """Map coordinates from image space to world space."""
    return transform(
        points=points,
        matrix=rotation_matrix(target) @ scaling_matrix(target),
        translation=image_translation(target),
    )


def world_to_voxel(target: sitk.Image, points: np.ndarray) -> np.ndarray:
    """Map coordinates from work space to image space."""
    m = inverse_scaling_matrix(target) @ inverse_rotation_matrix(target)
    x = points - np.expand_dims(image_translation(target), axis=0)
    y = transform(points=x, matrix=m)
    return y


def numpy_to_sitk(
    data: np.ndarray, reference: Optional[sitk.Image] = None
) -> sitk.Image:
    """Create SimpleITK image from NumPy array using image grid of reference."""
    img = sitk.GetImageFromArray(data)
    if reference:
        img.CopyInformation(reference)
    return img


def replace_mesh_points(mesh: vtkPolyData, points: np.ndarray) -> vtkPolyData:
    """Create new vtkPolyData mesh with same topology as input mesh but replace point coordinates."""
    assert points.ndim == 2, "points.shape={}".format(points.shape)
    assert points.shape[0] == mesh.GetNumberOfPoints(), "points.shape={}".format(
        points.shape
    )
    assert points.shape[1] == 3, "points.shape={}".format(points.shape)
    new_points = vtkPoints()
    new_points.SetData(numpy_to_vtk(points))
    new_mesh = vtkPolyData()
    new_mesh.ShallowCopy(mesh)
    new_mesh.SetPoints(new_points)
    assert new_mesh.GetNumberOfCells() == mesh.GetNumberOfCells()
    assert new_mesh.GetNumberOfPoints() == mesh.GetNumberOfPoints()
    return new_mesh


def deform_mesh(mesh: vtkPolyData, disp_field: sitk.Image) -> vtkPolyData:
    """Apply dense displacement field to vtkPolyData mesh points."""
    points = vtk_to_numpy(mesh.GetPoints().GetData())
    assert points.ndim == 2, "points.ndim={}".format(points.ndim)
    assert points.shape[0] == mesh.GetNumberOfPoints(), "points.shape={}".format(
        points.shape
    )
    assert points.shape[1] == 3, "points.shape={}".format(points.shape)
    voxels = world_to_voxel(disp_field, points)
    assert voxels.shape == points.shape
    indices = np.flip(np.moveaxis(voxels, -1, 0), axis=0)
    disps = sitk.GetArrayViewFromImage(disp_field)
    assert disps.ndim == 4, "disps.ndim={}".format(disps.ndim)
    assert disps.shape[-1] == 3, "disps.shape={}".format(disps.shape)
    new_points = points + np.stack(
        [
            scipy.ndimage.map_coordinates(disps[..., c], indices, cval=0, order=1)
            for c in range(3)
        ],
        axis=-1,
    )
    new_mesh = replace_mesh_points(mesh, new_points)
    assert new_mesh.GetNumberOfCells() == mesh.GetNumberOfCells()
    assert new_mesh.GetNumberOfPoints() == mesh.GetNumberOfPoints()
    return new_mesh


def read_mesh(path: str):
    reader = vtkSTLReader()
    reader.SetFileName(path)
    reader.Update()
    mesh = vtkPolyData()
    mesh.DeepCopy(reader.GetOutput())
    return mesh


def write_mesh(mesh: vtkPolyData, path: str):
    writer = vtkSTLWriter()
    writer.SetFileName(path)
    writer.SetInputData(mesh)
    writer.SetFileTypeToBinary()
    writer.Update()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target", help="Target image, i.e., first time point", required=True
    )
    parser.add_argument(
        "--dofs",
        help="CSV file with transformation file paths and time",
        type=Path,
        required=True,
    )
    parser.add_argument("--mesh", help="Input mesh at first time point", required=True)
    parser.add_argument("--step", help="Time step", type=float, required=True)
    parser.add_argument(
        "--start", help="Initial time point of output mesh", type=float, required=True
    )
    parser.add_argument(
        "--stop", help="Last time point of output mesh", type=float, required=True
    )
    parser.add_argument(
        "--output-mesh",
        help="File path template for output meshes, e.g., 'output_{i:05d}.stl' or 'output_{t:08.3f}.stl",
    )
    parser.add_argument("--output-table", help="File path of output STAR table")
    parser.add_argument(
        "--downsample",
        help="Number of spatially-uniform points to keep via FPS (0 = keep all, default: 5000)",
        type=int,
        default=5000,
    )

    args = parser.parse_args()

    initial_mesh = read_mesh(args.mesh)

    dofs = []
    dofs_csv_path = Path(args.dofs)
    with dofs_csv_path.open() as dofs_csv_file:
        dofs_csv_reader = csv.DictReader(dofs_csv_file)
        for row in dofs_csv_reader:
            dofs.append((str(Path(row["dof"])), float(row["t"])))
    dofs = sorted(dofs, key=lambda item: item[1])

    # --- Parallel DOF loading ---
    def load_dof_points(dof):
        """Load mesh points for a single DOF (thread-safe)."""
        t_val = float(dof[1])
        if dof[0] in ("id", "Id", "identity"):
            return t_val, vtk_to_numpy(initial_mesh.GetPoints().GetData())
        fp, tmp_path = mkstemp(suffix=".stl")
        os.close(fp)
        try:
            check_call(
                ["mirtk", "transform-points", args.mesh, tmp_path, "-dofin", dof[0]]
            )
            mesh = read_mesh(tmp_path)
            points = vtk_to_numpy(mesh.GetPoints().GetData())
            assert points.ndim == 2 and points.shape[1] == 3
            return t_val, points
        finally:
            os.remove(tmp_path)

    n_workers = min(len(dofs), os.cpu_count() or 1)
    print("Loading {} DOFs in parallel ({} workers)...".format(len(dofs), n_workers))
    results = []
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(load_dof_points, d): d for d in dofs}
        for f in as_completed(futures):
            t_val, pts = f.result()
            results.append((t_val, pts))
            print("  Loaded t={}".format(t_val))

    # Sort by time after parallel collection
    results.sort(key=lambda x: x[0])
    time_points = [r[0] for r in results]
    mesh_points = np.stack([r[1] for r in results], axis=0)

    # --- Vectorized interpolation ---
    mesh_points_interpolator = scipy.interpolate.interp1d(
        time_points, mesh_points, axis=0, bounds_error=True,
        assume_sorted=True, kind='cubic'
    )
    ts = np.arange(args.start, args.stop + args.step, args.step)

    # Evaluate all time points at once (vectorized)
    print("Interpolating {} time steps...".format(len(ts)))
    all_points = mesh_points_interpolator(ts)  # shape: (len(ts), N_vertices, 3)

    # Write star table (vectorized, no pd.concat)
    if args.output_table:
        columns = {}
        for i, t in enumerate(ts):
            columns["X[t={}ms] (mm)".format(t)] = all_points[i, :, 0]
            columns["Y[t={}ms] (mm)".format(t)] = all_points[i, :, 1]
            columns["Z[t={}ms] (mm)".format(t)] = all_points[i, :, 2]
        table = pd.DataFrame(columns)
        if args.downsample > 0 and args.downsample < table.shape[0]:
            print("FPS spatial downsampling: {} → {} points...".format(table.shape[0], args.downsample))
            indices = farthest_point_sample(all_points[0], args.downsample)
            table = table.iloc[indices]
        print("Write STAR table with shape", table.shape)
        table.to_csv(args.output_table, index=False, quoting=csv.QUOTE_NONNUMERIC)

    # Write interpolated STL meshes
    if args.output_mesh:
        print("Writing {} STL meshes...".format(len(ts)))
        for i, t in enumerate(ts):
            mesh = replace_mesh_points(initial_mesh, all_points[i])
            write_mesh(mesh, args.output_mesh.format(i=i, t=t))
