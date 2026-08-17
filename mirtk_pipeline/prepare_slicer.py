#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
"""Prepare registration output for CSA pipeline.

Creates a subject folder with registration/, surface/, and motion/ subfolders.
Copies FFD transforms, time-zero image, input.txt, and seg_0.stl.
Use --legacy for the old LeftNoseDecending/RightNose layout.
"""

import argparse
from argparse import ArgumentParser
from pathlib import Path
import logging
import shutil
import sys


# ---------------------------------------------------------------------------
# Colored logging formatter (matches run_pipeline.sh color scheme)
# ---------------------------------------------------------------------------
class ColoredFormatter(logging.Formatter):
    """Logging formatter that adds ANSI color codes to level names."""

    COLORS = {
        logging.DEBUG: "\033[0;37m",    # white
        logging.INFO: "\033[0;32m",     # green
        logging.WARNING: "\033[1;33m",  # yellow
        logging.ERROR: "\033[0;31m",    # red
        logging.CRITICAL: "\033[1;31m", # bold red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, self.RESET)
        record.levelname = f"{color}[{record.levelname}]{self.RESET}"
        return super().format(record)


def setup_logging() -> logging.Logger:
    """Configure root logger with colored output."""
    logger = logging.getLogger("prepare_slicer")
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(ColoredFormatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


log = setup_logging()


# ---------------------------------------------------------------------------
# Dry-run aware helpers
# ---------------------------------------------------------------------------
def do_mkdir(path: Path, dry_run: bool) -> None:
    """Create directory (or log what would be created in dry-run mode)."""
    if dry_run:
        log.info("mkdir -p %s", path)
    else:
        path.mkdir(parents=True, exist_ok=True)


def do_copy(src: Path, dst: Path, dry_run: bool) -> None:
    """Copy a single file (or log what would be copied in dry-run mode)."""
    if dry_run:
        log.info("cp %s %s", src, dst)
    else:
        shutil.copy2(str(src), str(dst))


def do_copy_glob(pattern_dir: Path, pattern: str, dst_dir: Path, dry_run: bool) -> int:
    """Copy all files matching a glob pattern into *dst_dir*.

    Returns the number of files copied.
    """
    count = 0
    for src in sorted(pattern_dir.glob(pattern)):
        do_copy(src, dst_dir / src.name, dry_run)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Auto-detection helpers
# ---------------------------------------------------------------------------
def find_registration_dirs(search_dir: Path) -> list[Path]:
    """Return subdirectories of *search_dir* that contain ffd_*.dof.gz files."""
    reg_dirs: list[Path] = []
    for child in sorted(search_dir.iterdir()):
        if child.is_dir() and list(child.glob("ffd_*.dof.gz")):
            reg_dirs.append(child)
    return reg_dirs


def detect_subject_id(reg_dir: Path, cwd: Path) -> str:
    """Detect the subject ID from the first NIfTI filename found.

    Searches the current working directory first, then falls back to
    *_0.nii.gz inside the registration directory.
    """
    # Try current directory first
    niftis = sorted(cwd.glob("*.nii*"))
    if not niftis:
        niftis = sorted(reg_dir.glob("*_0.nii.gz"))
    if not niftis:
        log.error("No NIfTI files found to detect subject ID")
        sys.exit(1)
    # Subject ID is the first underscore-delimited token of the filename
    subject = niftis[0].name.split("_")[0]
    return subject


def find_t0_image(reg_dir: Path) -> Path | None:
    """Return the first *_0.nii.gz image in the registration directory."""
    matches = sorted(reg_dir.glob("*_0.nii.gz"))
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Layout builders
# ---------------------------------------------------------------------------
def build_legacy_layout(
    reg_dir: Path,
    output_dir: Path,
    subject: str,
    dry_run: bool,
    cwd: Path,
) -> None:
    """Create the old LeftNoseDecending / RightNose folder structure."""
    main_folder = output_dir / f"{subject}CSA"

    for side in ("LeftNoseDecending", "RightNose"):
        side_path = main_folder / side / "FFD"
        do_mkdir(side_path, dry_run)

        count = do_copy_glob(reg_dir, "ffd_*.dof.gz", side_path, dry_run)
        if count == 0:
            log.warning("No FFD files found in %s", reg_dir)

        t0 = find_t0_image(reg_dir)
        if t0 is not None:
            do_copy(t0, side_path / t0.name, dry_run)

        input_txt = cwd / "input.txt"
        if input_txt.is_file():
            do_copy(input_txt, side_path / "input.txt", dry_run)

    log.info("Legacy layout created: %s", main_folder)


def build_standard_layout(
    reg_dir: Path,
    output_dir: Path,
    subject: str,
    dry_run: bool,
    cwd: Path,
) -> None:
    """Create the new standard folder structure."""
    output_path = output_dir / subject

    # Create directories
    for subdir in ("registration", "surface", "motion/stl", "motion/centerlines"):
        do_mkdir(output_path / subdir, dry_run)

    # --- registration/ ---
    count = do_copy_glob(reg_dir, "ffd_*.dof.gz", output_path / "registration", dry_run)
    if count == 0:
        log.error("No FFD files found in %s — aborting", reg_dir)
        return 1
    log.info("Copied %d FFD files", count)

    ffds_csv = reg_dir / "ffds.csv"
    if ffds_csv.is_file():
        do_copy(ffds_csv, output_path / "registration" / "ffds.csv", dry_run)
        log.info("Copied ffds.csv")
    elif (cwd / "ffds.csv").is_file():
        do_copy(cwd / "ffds.csv", output_path / "registration" / "ffds.csv", dry_run)
        log.info("Copied ffds.csv from current dir")

    t0 = find_t0_image(reg_dir)
    if t0 is not None:
        do_copy(t0, output_path / "registration" / t0.name, dry_run)
        log.info("Copied time-zero image: %s", t0.name)

    input_txt = cwd / "input.txt"
    if input_txt.is_file():
        do_copy(input_txt, output_path / "registration" / "input.txt", dry_run)
        log.info("Copied input.txt")

    # --- surface/ ---
    seg_stl = reg_dir / "seg_0.stl"
    if seg_stl.is_file():
        do_copy(seg_stl, output_path / "surface" / "seg_0.stl", dry_run)
        log.info("Copied seg_0.stl")
    elif (cwd / "seg_0.stl").is_file():
        do_copy(cwd / "seg_0.stl", output_path / "surface" / "seg_0.stl", dry_run)
        log.info("Copied seg_0.stl from current dir")
    else:
        log.warning("seg_0.stl not found — surface/ folder is empty")

    # --- Summary ---
    log.info("Subject folder ready: %s", output_path)
    print()
    print(f"  {output_path}/")
    print("  \u251c\u2500\u2500 registration/   (FFDs, ffds.csv, img_0, input.txt)")
    print("  \u251c\u2500\u2500 surface/        (seg_0.stl)")
    print("  \u2514\u2500\u2500 motion/")
    print("      \u251c\u2500\u2500 stl/        (empty \u2014 populated by interpolation)")
    print("      \u2514\u2500\u2500 centerlines/ (empty \u2014 populated by CSA pipeline)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Build the argument parser."""
    p = ArgumentParser(
        description="Prepare registration output for CSA pipeline",
    )
    p.add_argument(
        "--reg-dir",
        type=Path,
        default=None,
        help="Path to registration results folder (auto-detected if omitted)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to create the subject folder (default: ../)",
    )
    p.add_argument(
        "--subject",
        type=str,
        default="",
        help="Subject ID for the output folder (skips filename-based detection)",
    )
    p.add_argument(
        "--legacy",
        action="store_true",
        help="Use old LeftNoseDecending/RightNose layout",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without copying",
    )
    try:
        import argcomplete
        argcomplete.autocomplete(p)
    except ImportError:
        pass
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    # Enable Tab completion of file/dir paths at interactive input() prompts.
    from mirtk_pipeline._completion import enable_path_completion
    enable_path_completion()

    args = parse_args(argv)
    cwd = Path.cwd()

    # --- Find registration results folder ---
    reg_dir: Path
    if args.reg_dir is not None:
        reg_dir = args.reg_dir.resolve()
    else:
        candidates = find_registration_dirs(cwd)
        if len(candidates) == 0:
            log.error(
                "No registration results folder found (no ffd_*.dof.gz files). "
                "Use --reg-dir to specify."
            )
            return 1
        elif len(candidates) == 1:
            reg_dir = candidates[0]
            log.info("Auto-detected registration folder: %s", reg_dir)
        else:
            print("Multiple registration folders found:")
            for i, d in enumerate(candidates, 1):
                print(f"  {i}) {d}")
            choice = input(f"Select [1-{len(candidates)}]: ")
            try:
                idx = int(choice) - 1
                if idx < 0 or idx >= len(candidates):
                    raise ValueError
            except ValueError:
                log.error("Invalid selection: %s", choice)
                return 1
            reg_dir = candidates[idx]

    if not reg_dir.is_dir():
        log.error("Registration folder not found: %s", reg_dir)
        return 1

    # --- Subject ID: explicit flag wins, filename detection as fallback ---
    if args.subject:
        subject = args.subject
        log.info("Subject (from --subject): %s", subject)
    else:
        subject = detect_subject_id(reg_dir, cwd)
        log.info("Detected subject: %s", subject)

    # --- Determine output location ---
    if args.output_dir is not None:
        output_dir = args.output_dir.resolve()
    else:
        user_input = input("Output directory (default: ../): ").strip()
        output_dir = Path(user_input).resolve() if user_input else (cwd / "..").resolve()

    # --- Build layout ---
    if args.legacy:
        build_legacy_layout(reg_dir, output_dir, subject, args.dry_run, cwd)
    else:
        build_standard_layout(reg_dir, output_dir, subject, args.dry_run, cwd)

    return 0


if __name__ == "__main__":
    sys.exit(main())
