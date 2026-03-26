#!/usr/bin/env python

import pyvista as pv
import argparse
import os


def main():
    parser = argparse.ArgumentParser(
        description="Generate multi-view 3D renderings of an STL mesh sequence."
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
        "--output-prefix",
        help="Output image prefix (default: stl_dir path)",
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

    print("Found {} STL files".format(tf))

    output_prefix = args.output_prefix or args.stl_dir

    pv.set_plot_theme("document")
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

        screenshot_path = "{}_fig_{:04d}.png".format(output_prefix, i)
        plotter.show(screenshot=screenshot_path)
        print("Saved: {}".format(screenshot_path))


if __name__ == "__main__":
    main()
