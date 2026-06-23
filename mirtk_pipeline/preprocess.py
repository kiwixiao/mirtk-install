#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import argparse

import SimpleITK as sitk


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--timestep", type=float, default=0.025)
    parser.add_argument("--conductance", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=15)

    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass
    argv = parser.parse_args()

    img = sitk.ReadImage(argv.input)
    out = sitk.CurvatureAnisotropicDiffusion(
        img,
        timeStep=argv.timestep,
        conductanceParameter=argv.conductance,
        conductanceScalingUpdateInterval=1,
        numberOfIterations=argv.iterations,
    )
    out = sitk.RescaleIntensity(out, 0, 1000)
    sitk.WriteImage(out, argv.output)


if __name__ == "__main__":
    main()
