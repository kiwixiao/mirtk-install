#!/usr/bin/env python

import trimesh
import argparse
import os


def main():
    parser = argparse.ArgumentParser(
        description="Scale STL mesh coordinates by a given factor."
    )
    parser.add_argument("input_file", help="Path to the input STL file")
    parser.add_argument(
        "--scale-factor",
        type=float,
        default=1000.0,
        help="Uniform scale factor to apply (default: 1000)",
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: input_Scaled.stl)",
    )
    args = parser.parse_args()

    mesh = trimesh.load_mesh(args.input_file)
    mesh_scaled = mesh.apply_scale(args.scale_factor)

    if args.output:
        output_file = args.output
    else:
        base = os.path.splitext(os.path.basename(args.input_file))[0]
        output_file = base + "_Scaled.stl"

    mesh_scaled.export(output_file)
    print("Saved scaled mesh to: {}".format(output_file))


if __name__ == "__main__":
    main()
