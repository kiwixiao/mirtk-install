#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import pyvista as pv
import argparse
import numpy as np
import os
import pandas as pd
import re
import subprocess


# Target spacing between rendered video frames, in milliseconds. The video is
# sampled in TIME, not by index stride, so the motion plays back at the same
# temporal resolution whether the interpolation ran at 1 ms or 25 ms.
FRAME_DT_DEFAULT = 25.0


def parse_times_from_names(paths):
    """Extract the time (ms) encoded in out_<t>_*.stl names.

    Returns None if any name does not carry a parseable time, so the caller can
    fall back to index-stride sampling.
    """
    times = []
    for p in paths:
        m = re.match(r"^out_(\d+(?:\.\d+)?)_", os.path.basename(p))
        if m is None:
            return None
        times.append(float(m.group(1)))
    return times


def select_frame_indices(times, frame_dt, label="frames"):
    """Pick indices spaced ~frame_dt ms apart, always including the last one.

    *times* must be sorted. Returns every index when the source is already
    coarser than frame_dt (we cannot invent resolution we do not have).
    """
    n = len(times)
    if n < 2 or not frame_dt or frame_dt <= 0:
        return list(range(n))

    steps = np.diff(times)
    source_dt = float(np.median(steps))
    if source_dt <= 0:
        return list(range(n))

    stride = int(round(frame_dt / source_dt))
    if stride < 1:
        print("[WARN] {} are {:.3f} ms apart, coarser than the {:.3f} ms target; "
              "rendering every frame.".format(label, source_dt, frame_dt))
        stride = 1

    idx = list(range(0, n, stride))
    # Always close the cycle -- the last mesh is rarely a multiple of the stride.
    if idx[-1] != n - 1:
        idx.append(n - 1)

    print("{}: {} available at {:.3f} ms -> rendering {} at ~{:.3f} ms "
          "(stride {})".format(label, n, source_dt, len(idx),
                               source_dt * stride, stride))
    return idx


def make_video(frames_dir, video_path, frame_count, duration):
    """Generate MP4 from numbered PNG frames, always spanning *duration* seconds.

    The framerate is passed to ffmpeg as an exact rational (frames/duration) so
    the clip length is fixed regardless of frame count. Integer floor division
    was used here previously, which silently stretched the clip whenever the
    frame count was not a multiple of the duration (e.g. 18 frames over 10 s
    truncated to 1 fps and produced an 18 s video).
    """
    if frame_count <= 0:
        print("[WARN] No frames to encode; skipping video.")
        return
    if duration <= 0:
        print("[WARN] Invalid duration {}s; skipping video.".format(duration))
        return
    framerate = "{}/{}".format(frame_count, duration)
    print("Video: {} frames / {}s = {:.3f} fps".format(
        frame_count, duration, frame_count / float(duration)))
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-framerate", framerate,
        "-i", os.path.join(frames_dir, "frame_%04d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-r", framerate,
        video_path,
    ]
    try:
        subprocess.check_call(ffmpeg_cmd)
        print("Video saved: {}".format(video_path))
    except FileNotFoundError:
        print("[WARN] ffmpeg not found. PNGs saved but video not generated.")
    except subprocess.CalledProcessError as e:
        print("[WARN] ffmpeg failed: {}. PNGs saved.".format(e))


def render_stl_video(stl_dir, output_dir, results_root, interval, duration, pattern,
                     no_video, frame_dt=FRAME_DT_DEFAULT):
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

    # Prefer sampling by time so the playback resolution is independent of the
    # interpolation step; fall back to the index stride if --interval was given
    # explicitly or the filenames carry no time.
    times = None if interval is not None else parse_times_from_names(file_list)
    if times is not None:
        indices = select_frame_indices(times, frame_dt, label="STL meshes")
    else:
        stride = interval if interval else 1
        indices = list(range(0, tf, stride))
        print("Found {} STL files, rendering every {}th = {} frames".format(
            tf, stride, len(indices)))

    os.makedirs(output_dir, exist_ok=True)

    pv.set_plot_theme("document")
    frame_count = 0
    for i in indices:
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


def render_pointcloud_video(csv_path, results_root, interval, duration, no_video,
                            frame_dt=FRAME_DT_DEFAULT):
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

    # Column headers carry the time, e.g. "X[t=25.0ms] (mm)".
    times = None
    if interval is None:
        parsed = []
        for c in df.columns[::3]:
            m = re.search(r"t=([0-9.eE+-]+)ms", str(c))
            if m is None:
                parsed = None
                break
            parsed.append(float(m.group(1)))
        times = parsed

    if times:
        indices = select_frame_indices(times, frame_dt, label="star-table steps")
    else:
        stride = interval if interval else 1
        indices = list(range(0, n_timesteps, stride))
        print("Rendering {} time steps as point cloud (every {}th)...".format(
            n_timesteps, stride))

    pv.set_plot_theme("document")
    frame_count = 0
    for t in indices:
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
        "--frame-dt",
        dest="frame_dt",
        type=float,
        default=FRAME_DT_DEFAULT,
        help="Target spacing between video frames in ms (default: {:g}). "
             "Sampling is done in time, so playback resolution is the same "
             "whether the interpolation ran at 1 ms or 25 ms.".format(FRAME_DT_DEFAULT),
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Legacy index stride: render every Nth frame. Overrides --frame-dt.",
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
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass
    args = parser.parse_args()

    results_root = os.path.dirname(args.stl_dir) or "."
    output_dir = args.output_dir or os.path.join(results_root, "video_frames")

    # STL mesh video
    render_stl_video(
        args.stl_dir, output_dir, results_root,
        args.interval, args.duration, args.pattern, args.no_video, args.frame_dt
    )

    # Point cloud video from star table
    if args.csv:
        render_pointcloud_video(
            args.csv, results_root, args.interval, args.duration, args.no_video,
            args.frame_dt
        )


if __name__ == "__main__":
    main()
