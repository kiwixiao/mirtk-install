#!/usr/bin/env python

import argparse
import pyvista as pv


def main():
    parser = argparse.ArgumentParser(
        description="Decimate (simplify) an STL mesh by reducing triangle count."
    )
    parser.add_argument("input_file", help="Path to the input STL file")
    parser.add_argument(
        "--target-reduction",
        type=float,
        default=0.95,
        help="Fraction of triangles to remove (0.0-1.0, default: 0.95 = keep 5%%)",
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: input_decimated.stl)",
    )
    args = parser.parse_args()

    mesh = pv.read(args.input_file)
    decimated_mesh = mesh.decimate(target_reduction=args.target_reduction)

    if args.output:
        output_file = args.output
    else:
        output_file = args.input_file[:-4] + "_decimated.stl"

    decimated_mesh.save(output_file)
    print("Saved decimated mesh to: {}".format(output_file))
    print("  Original triangles: {}".format(mesh.n_cells))
    print("  Decimated triangles: {}".format(decimated_mesh.n_cells))


if __name__ == "__main__":
    main()
