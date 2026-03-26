#!/usr/bin/env python

from argparse import ArgumentParser
from pathlib import Path
import logging
import shutil
from subprocess import check_call
import sys
from tempfile import mkdtemp
from typing import Optional, List


log = logging.getLogger()


def parser() -> ArgumentParser:
    """Create command-line parser."""
    p = ArgumentParser()
    p.add_argument(
        "--prefix", help="Common file path prefix of input image files", required=True
    )
    p.add_argument(
        "--infix",
        help="Ordered list of infixes of images in temporal sequence",
        nargs="+",
    )
    p.add_argument(
        "--suffix",
        help="Common file path suffix of input image files",
        default=".nii.gz",
    )
    p.add_argument(
        "--mask", help="Foreground mask at which to evaluate image similarity"
    )
    p.add_argument("--parin", help="Pairwise registration parameters", required=True)
    p.add_argument(
        "--dofout",
        help="Output file path template for computed deformations",
        default="{prefix}{infix}.dof.gz",
    )
    p.add_argument("--workdir", help="Temporary working directory", type=Path)
    p.add_argument(
        "--log-level",
        help="Logging level",
        choices=["ERROR", "WARNING", "INFO", "DEBUG"],
        default="INFO",
    )
    return p


def register_pair(
    target: Path,
    source: Path,
    dofout: Path,
    dofin: Optional[Path] = None,
    parin: Optional[Path] = None,
    mask: Optional[Path] = None,
    levels: Optional[int] = None,
):
    """Perform registration between a single pair of images (or pointsets)."""
    command = ["mirtk", "register", str(target), str(source)]
    if parin:
        command.extend(["-parin", str(parin)])
    if levels is not None and levels > 0:
        command.extend(["-levels", str(levels)])
    if mask:
        command.extend(["-mask", str(mask)])
    if dofin:
        command.extend(["-dofin", str(dofin)])
    else:
        command.extend(["-dofin", "Id"])
    command.extend(["-dofout", str(dofout)])
    log.debug(command)
    sys.stdout.write("\n")
    check_call(command)
    sys.stdout.write("\n")


def register_subsequent_pairs(
    workdir: Path,
    prefix: str,
    infix: List[str],
    suffix: str,
    parin: Optional[Path] = None,
    mask: Optional[Path] = None,
):
    """Perform pairwise registrations between subsequent pairs of images (or pointsets)."""
    for i in range(len(infix) - 1):
        j = i + 1
        log.info("Compute deformation from time point %d to %d", i, j)
        register_pair(
            target=Path(prefix + infix[i] + suffix),
            source=Path(prefix + infix[j] + suffix),
            dofout=workdir / "ffd_{}_{}.dof.gz".format(i, j),
            parin=parin,
            mask=mask,
        )


def compose_longitudinal_dofs(workdir: Path, num: int):
    """Compose deformations from first time point to all later time points."""
    for j in range(2, num):
        log.info("Compute deformation from time point %d to %d", 0, j)
        dof_1 = workdir / "ffd_0_{}.dof.gz".format(j - 1)
        dof_2 = workdir / "ffd_{}_{}.dof.gz".format(j - 1, j)
        dof_3 = workdir / "ffd_0_{}.dof.gz".format(j)
        command = ["mirtk", "compose-dofs", dof_1, dof_2, dof_3]
        log.debug(command)
        check_call(command)


def refine_longitudinal_dofs(
    workdir: Path,
    prefix: str,
    infix: List[str],
    suffix: str,
    parin: Optional[Path] = None,
    mask: Optional[Path] = None,
):
    """Refine registration of first time point to later time points."""
    num = len(infix)
    for j in range(2, num):
        log.info("Refine deformation from time point %d to %d", 0, j)
        register_pair(
            target=Path(prefix + infix[0] + suffix),
            source=Path(prefix + infix[j] + suffix),
            parin=parin,
            mask=mask,
            dofin=workdir / "ffd_0_{}.dof.gz".format(j),
            dofout=workdir / "ffd_0_{}.dof.gz".format(j),
            levels=1,
        )


def register_sequence(
    dofout: str,
    prefix: str,
    infix: List[str],
    suffix: str = ".nii.gz",
    parin: Optional[Path] = None,
    mask: Optional[Path] = None,
    workdir: Optional[Path] = None,
):
    """Register all time points of temporal sequence to first time point."""
    if workdir is None:
        tmpdir = Path(mkdtemp())
    else:
        tmpdir = Path(workdir).absolute()
        tmpdir.mkdir(parents=True, exist_ok=False)
    try:
        log.info("Perform step-by-step pairwise registrations")
        register_subsequent_pairs(
            workdir=tmpdir,
            prefix=prefix,
            infix=infix,
            suffix=suffix,
            parin=parin,
            mask=mask,
        )
        log.info("Compose longitudinal deformations")
        compose_longitudinal_dofs(workdir=tmpdir, num=len(infix))
        log.info("Refine longitudinal deformations")
        refine_longitudinal_dofs(
            workdir=tmpdir,
            prefix=prefix,
            infix=infix,
            suffix=suffix,
            parin=parin,
            mask=mask,
        )
        for i in range(1, len(infix)):
            dst = Path(dofout.format(prefix=prefix, infix=infix[i], i=i)).absolute()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(tmpdir / "ffd_0_{}.dof.gz".format(i), dst)
    finally:
        if workdir is None:
            shutil.rmtree(tmpdir)


def main(argv=None) -> int:
    """Main function."""
    args = parser().parse_args(argv)
    logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=args.log_level)
    register_sequence(
        dofout=args.dofout,
        prefix=args.prefix,
        infix=args.infix,
        suffix=args.suffix,
        parin=args.parin,
        mask=args.mask,
        workdir=args.workdir,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write("Execution interrupted by user")
        sys.exit(1)
