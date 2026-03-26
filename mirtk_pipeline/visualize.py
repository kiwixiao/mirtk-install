#!/usr/bin/env python

import pyvista as pv
import argparse
import os
import subprocess


def main():
    parser = argparse.ArgumentParser(
        description="Generate multi-view 3D renderings of an STL mesh sequence and create MP4 video."
    )
    parser.add_argument("stl_dir", help="Directory containing STL output files")
    parser.add_argument(
        "--interval",
        type=int,
        default=1,
        help="Render every Nth STL file (default: 1)",
    )
    parser.add_argument(
        "--pattern",
        default="out",
        help="Filename substring to match STL files (default: 'out')",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for frames and video (default: stl_dir/video_frames)",
    )
    parser.add_argument(
        "--framerate",
        type=int,
        default=10,
        help="Video framerate (default: 10)",
    )
    parser.add_argument(
        "--no-video",
        action="store_true",
        help="Skip MP4 video generation (PNGs only)",
    )
    args = parser.parse_args()

    file_list = []
    for filename in os.listdir(args.stl_dir):
        if args.pattern in filename and filename.endswith(".stl"):
            file_list.append(os.path.join(args.stl_dir, filename))

    file_list.sort()
    tf = len(file_list)

    if tf == 0:
        print("No STL files found matching pattern '{}' in {}".format(
            args.pattern, args.stl_dir
        ))
        return

    print("Found {} STL files, rendering every {}th = {} frames".format(
        tf, args.interval, len(range(0, tf, args.interval))
    ))

    # Create output directory
    output_dir = args.output_dir or os.path.join(args.stl_dir, "video_frames")
    os.makedirs(output_dir, exist_ok=True)

    pv.set_plot_theme("document")
    frame_count = 0
    for i in range(0, tf, args.interval):
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

    print("Generated {} PNG frames in: {}".format(frame_count, output_dir))

    # Generate MP4 video
    if not args.no_video:
        video_path = os.path.join(output_dir, "stl_motion.mp4")
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-framerate", str(args.framerate),
            "-i", os.path.join(output_dir, "frame_%04d.png"),
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


if __name__ == "__main__":
    main()
