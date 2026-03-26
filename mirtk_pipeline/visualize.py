#!/usr/bin/env python

import pyvista as pv
import argparse
import numpy as np
import os
import pandas as pd
import subprocess


def make_video(frames_dir, video_path, frame_count, duration):
    """Generate MP4 from numbered PNG frames."""
    framerate = max(1, frame_count // duration)
    print("Video: {} frames / {}s = {} fps".format(frame_count, duration, framerate))
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-framerate", str(framerate),
        "-i", os.path.join(frames_dir, "frame_%04d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        video_path,
    ]
    try:
        subprocess.check_call(ffmpeg_cmd)
        print("Video saved: {}".format(video_path))
    except FileNotFoundError:
        print("[WARN] ffmpeg not found. PNGs saved but video not generated.")
    except subprocess.CalledProcessError as e:
        print("[WARN] ffmpeg failed: {}. PNGs saved.".format(e))


def render_stl_video(stl_dir, output_dir, results_root, interval, duration, pattern, no_video):
    """Render multi-view STL mesh sequence as PNGs + MP4."""
    file_list = []
    for filename in os.listdir(stl_dir):
        if pattern in filename and filename.endswith(".stl"):
            file_list.append(os.path.join(stl_dir, filename))

    file_list.sort()
    tf = len(file_list)

    if tf == 0:
        print("No STL files found matching pattern '{}' in {}".format(pattern, stl_dir))
        return

    print("Found {} STL files, rendering every {}th = {} frames".format(
        tf, interval, len(range(0, tf, interval))
    ))

    os.makedirs(output_dir, exist_ok=True)

    pv.set_plot_theme("document")
    frame_count = 0
    for i in range(0, tf, interval):
        mymesh = pv.read(file_list[i])
        plotter = pv.Plotter(shape=(2, 2), off_screen=True)

        plotter.subplot(0, 0)
        plotter.add_mesh(mymesh)

        plotter.subplot(0, 1)
        plotter.add_mesh(mymesh)
        plotter.view_xy()

        plotter.subplot(1, 0)
        plotter.add_mesh(mymesh)
        plotter.view_xz()

        plotter.subplot(1, 1)
        plotter.add_mesh(mymesh)
        plotter.view_yz()

        screenshot_path = os.path.join(output_dir, "frame_{:04d}.png".format(frame_count))
        plotter.show(screenshot=screenshot_path)
        print("Saved: {}".format(screenshot_path))
        frame_count += 1

    print("Generated {} STL PNG frames in: {}".format(frame_count, output_dir))

    if not no_video:
        video_path = os.path.join(results_root, "stl_motion.mp4")
        make_video(output_dir, video_path, frame_count, duration)


def render_pointcloud_video(csv_path, results_root, interval, duration, no_video):
    """Render point cloud animation from star table CSV as PNGs + MP4."""
    if not os.path.isfile(csv_path):
        print("[WARN] Star table not found: {}. Skipping point cloud video.".format(csv_path))
        return

    print("Reading star table: {}".format(csv_path))
    df = pd.read_csv(csv_path)

    n_cols = len(df.columns)
    n_timesteps = n_cols // 3

    if n_timesteps == 0:
        print("[WARN] No time steps found in star table. Skipping point cloud video.")
        return

    frames_dir = os.path.join(results_root, "pointcloud_frames")
    os.makedirs(frames_dir, exist_ok=True)

    print("Rendering {} time steps as point cloud (every {}th)...".format(
        n_timesteps, interval
    ))

    pv.set_plot_theme("document")
    frame_count = 0
    for t in range(0, n_timesteps, interval):
        x = df.iloc[:, t * 3].values
        y = df.iloc[:, t * 3 + 1].values
        z = df.iloc[:, t * 3 + 2].values
        points = np.column_stack([x, y, z])

        cloud = pv.PolyData(points)
        plotter = pv.Plotter(shape=(2, 2), off_screen=True)

        plotter.subplot(0, 0)
        plotter.add_mesh(cloud, point_size=3, color="blue", render_points_as_spheres=True)

        plotter.subplot(0, 1)
        plotter.add_mesh(cloud, point_size=3, color="blue", render_points_as_spheres=True)
        plotter.view_xy()

        plotter.subplot(1, 0)
        plotter.add_mesh(cloud, point_size=3, color="blue", render_points_as_spheres=True)
        plotter.view_xz()

        plotter.subplot(1, 1)
        plotter.add_mesh(cloud, point_size=3, color="blue", render_points_as_spheres=True)
        plotter.view_yz()

        screenshot_path = os.path.join(frames_dir, "frame_{:04d}.png".format(frame_count))
        plotter.show(screenshot=screenshot_path)
        frame_count += 1

    print("Generated {} point cloud PNG frames in: {}".format(frame_count, frames_dir))

    if not no_video:
        video_path = os.path.join(results_root, "pointcloud_motion.mp4")
        make_video(frames_dir, video_path, frame_count, duration)


def main():
    parser = argparse.ArgumentParser(
        description="Generate multi-view 3D renderings of STL meshes and point clouds."
    )
    parser.add_argument("stl_dir", help="Directory containing STL output files")
    parser.add_argument(
        "--interval",
        type=int,
        default=1,
        help="Render every Nth frame (default: 1)",
    )
    parser.add_argument(
        "--pattern",
        default="out",
        help="Filename substring to match STL files (default: 'out')",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for STL frames (default: results_root/video_frames)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=10,
        help="Target video duration in seconds (default: 10)",
    )
    parser.add_argument(
        "--csv",
        help="Path to star table CSV for point cloud video",
    )
    parser.add_argument(
        "--no-video",
        action="store_true",
        help="Skip MP4 video generation (PNGs only)",
    )
    args = parser.parse_args()

    results_root = os.path.dirname(args.stl_dir) or "."
    output_dir = args.output_dir or os.path.join(results_root, "video_frames")

    # STL mesh video
    render_stl_video(
        args.stl_dir, output_dir, results_root,
        args.interval, args.duration, args.pattern, args.no_video
    )

    # Point cloud video from star table
    if args.csv:
        render_pointcloud_video(
            args.csv, results_root, args.interval, args.duration, args.no_video
        )


if __name__ == "__main__":
    main()
