#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
"""
MIRTK Registration Pipeline - Dual Mode (Interactive / CLI)

All processing runs INSIDE the results folder. Subject folder stays clean.
Supports both interactive prompts (no args) and CLI arguments (for scripting).
"""

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# =============================================================================
# Paths
# =============================================================================
PIPELINE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = PIPELINE_DIR / "config" / "register.cfg"
WORK_DIR = Path.cwd()


# =============================================================================
# Colored logging formatter
# =============================================================================
class ColorFormatter(logging.Formatter):
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    NC = "\033[0m"

    LEVEL_COLORS = {
        logging.INFO: GREEN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, self.NC)
        tag = {
            logging.INFO: "INFO",
            logging.WARNING: "WARN",
            logging.ERROR: "ERROR",
        }.get(record.levelno, record.levelname)
        record.msg = f"{color}[{tag}]{self.NC} {record.msg}"
        return super().format(record)


log = logging.getLogger("mirtk_pipeline")
log.setLevel(logging.DEBUG)

# Console handler (always present)
_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.DEBUG)
_console.setFormatter(ColorFormatter("%(message)s"))
log.addHandler(_console)


def add_file_handler(log_path: Path):
    """Add a file handler that strips ANSI codes."""

    class StripAnsiFormatter(logging.Formatter):
        _ansi_re = re.compile(r"\033\[[0-9;]*m")

        def format(self, record):
            msg = super().format(record)
            return self._ansi_re.sub("", msg)

    fh = logging.FileHandler(str(log_path), mode="a")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(StripAnsiFormatter("%(message)s"))
    log.addHandler(fh)

    global _log_file_handle
    _log_file_handle = open(str(log_path), "a")


def error(msg):
    log.error(msg)
    sys.exit(1)


# =============================================================================
# Dual-mode parameter getter
# =============================================================================
def get_param(prompt: str, cli_value: str = "") -> str:
    """If cli_value is provided (non-empty), use it; otherwise prompt the user."""
    if cli_value:
        return cli_value
    return input(prompt)


# =============================================================================
# Helper: resolve path to absolute
# =============================================================================
def resolve_path(p: str) -> Path:
    """Resolve a path: if already absolute use as-is, otherwise relative to WORK_DIR."""
    if not p:
        return Path("")
    path = Path(p)
    if path.is_absolute():
        return path.resolve()
    return (WORK_DIR / path).resolve()


# =============================================================================
# Natural sort key (no external dependency)
# =============================================================================
def natural_sort_key(p: Path):
    return [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", p.name)]


# =============================================================================
# Subprocess runner: tee output to log file like shell's exec > >(tee ...)
# =============================================================================
_log_file_handle = None

def run(cmd, **kwargs):
    """Run a subprocess, tee stdout/stderr to log file if logging is active."""
    kwargs.setdefault("check", True)
    if _log_file_handle is not None:
        # Capture output and tee to both terminal and log.
        # check=True makes subprocess.run raise before we get a chance to tee,
        # so catch it, flush the captured output (which holds the traceback,
        # since stderr is folded into stdout), then re-raise.
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, **kwargs)
        except subprocess.CalledProcessError as exc:
            output = exc.output or ""
            sys.stdout.write(output)
            _log_file_handle.write(output)
            _log_file_handle.write(
                "\n[ERROR] Command failed (exit {}): {}\n".format(
                    exc.returncode, " ".join(str(c) for c in cmd)))
            _log_file_handle.flush()
            raise
        sys.stdout.write(result.stdout)
        _log_file_handle.write(result.stdout)
        _log_file_handle.flush()
        return result
    return subprocess.run(cmd, **kwargs)


# =============================================================================
# Shared functions
# =============================================================================

def parse_input_txt(input_file: Path) -> dict:
    if not input_file.is_file():
        error(f"input.txt not found at: {input_file}")
    log.info(f"Reading timing parameters from {input_file}")
    lines = input_file.read_text().splitlines()
    # Line indices: 0-based in Python, shell used sed -n 2p (1-based)
    begin_point = int(lines[1].split(",")[-1].strip())
    time_points = int(lines[2].split(",")[-1].strip())
    bre_time = int(lines[3].split(",")[-1].strip())
    dt = bre_time // (time_points - 1)
    time_end = dt * (time_points - 1)
    num_infix = list(range(time_points))
    log.info(f"beginPoint={begin_point} timePoints={time_points} breTime={bre_time} dt={dt}")
    return {
        "begin_point": begin_point,
        "time_points": time_points,
        "bre_time": bre_time,
        "dt": dt,
        "time_end": time_end,
        "num_infix": num_infix,
    }


def extract_4d_frames(image4d: Path, time_points: int, begin_point: int):
    # input.txt uses 1-based frame numbering (beginPoint=1 => first frame), but
    # `mirtk extract-image-volume -t` is a 0-based volume index. Convert here so the
    # 1-based input.txt convention is preserved. Keep run_pipeline.sh in sync.
    if begin_point < 1:
        error(f"beginPoint in input.txt must be 1-based (>= 1), got {begin_point}")
    start_index = begin_point - 1
    log.info(f"Extracting {time_points} frames from 4D image starting at frame "
             f"{begin_point} (1-based, = volume index {start_index})")
    run(
        ["mirtk", "extract-image-volume", str(image4d),
         "-t", str(start_index), "-n", str(time_points),
         "extracted_static.nii.gz"],
        check=True,
    )
    # Rename extracted files (tighten glob to .nii.gz only)
    extracted = sorted(Path(".").glob("extracted_static*.nii.gz"), key=natural_sort_key)
    for i, x in enumerate(extracted):
        x.rename(f"staticFrom4D_t{begin_point}_n{time_points}_{i}.nii.gz")


def copy_3d_frames(frames_dir: Path, time_points: int, begin_point: int):
    if not frames_dir.is_dir():
        error(f"Frames directory not found: {frames_dir}")
    # Collect .nii and .nii.gz files, natural sorted
    nii_files = sorted(
        [f for f in frames_dir.iterdir() if f.name.endswith((".nii", ".nii.gz"))],
        key=natural_sort_key,
    )
    if not nii_files:
        error(f"No .nii/.nii.gz files found in {frames_dir}")
    if len(nii_files) != time_points:
        error(
            f"Frame count mismatch: found {len(nii_files)} image(s) in {frames_dir} "
            f"but input.txt timePoints={time_points}. These must match "
            f"(one 3D image per time point, in natural-sort order)."
        )
    for i, x in enumerate(nii_files):
        shutil.copy2(str(x), f"staticImage_t{begin_point}_n{time_points}_{i}.nii.gz")
    log.info(f"Copied {len(nii_files)} 3D frames from {frames_dir}")


def create_symlinks(prefix: str, time_points: int, begin_point: int):
    if not Path("img_0.nii.gz").exists():
        for i in range(time_points):
            src = f"{prefix}_t{begin_point}_n{time_points}_{i}.nii.gz"
            dst = f"img_{i}.nii.gz"
            os.symlink(src, dst)
        log.info("Symlinks created")
    else:
        log.warning("Symlinks already exist, skipping")


def extract_stl_from_mask(segmask: Path, output_stl: str):
    log.info("Extracting STL surface from segmentation mask")
    run(
        ["mirtk", "extract-surface", str(segmask), output_stl,
         "-blur", "0.8", "-isovalue", "0.4"],
        check=True,
    )


def perform_alignment(static_image: str, first_image: str, man_seg_stl: str,
                       aligned_stl: str, aligned_mask: str, alignment_dof: str,
                       initial: str, align_mode: str, align_config: str,
                       ds: str, levels: str, align_be: str,
                       force: bool = False):
    # force=True re-runs every step even if the outputs already exist. Required for the
    # --reuse-reg path, which runs INSIDE a prior results dir that already contains
    # alignment.dof.gz / seg_0.stl / seg_0.nii.gz from the earlier run -- without force
    # the existence checks below would silently skip the requested alignment and leave
    # the stale (possibly unaligned) seg_0.stl in place while labeling the run "aligned".
    # Register static image to first time point
    if force or not Path(alignment_dof).exists():
        log.info("Registering static image to time-zero frame")
        if align_mode == "config":
            run(
                ["mirtk", "register", static_image, first_image,
                 "-model", "Rigid+Affine+FFD",
                 "-dofin", initial, "-dofout", alignment_dof,
                 "-parin", align_config],
                check=True,
            )
        else:
            run(
                ["mirtk", "register", static_image, first_image,
                 "-model", "Rigid+Affine+FFD",
                 "-dofin", initial, "-dofout", alignment_dof,
                 "-ds", ds, "-levels", levels, "-be", align_be, "-sim", "NMI"],
                check=True,
            )
    else:
        log.warning("Alignment DOF already exists, skipping")

    # Transform manual segmentation STL to time-zero
    if force or not Path(aligned_stl).exists():
        log.info("Transforming STL to time-zero using alignment")
        run(["mirtk", "transform-points", man_seg_stl, aligned_stl,
             "-dofin", alignment_dof])
    else:
        log.warning("Aligned STL already exists, skipping")

    # Generate binary mask from aligned STL
    if force or not Path(aligned_mask).exists():
        log.info("Generating binary mask from aligned STL")
        run(["mirtk", "extract-pointset-surface",
             "-input", aligned_stl, "-mask", aligned_mask,
             "-reference", first_image])
    else:
        log.warning("Aligned mask already exists, skipping")


def skip_alignment(man_seg_stl: str, segmask: str, aligned_stl: str, aligned_mask: str):
    log.info("No alignment requested. Copying manual segmentation as time-zero reference.")
    shutil.copy2(man_seg_stl, aligned_stl)
    shutil.copy2(segmask, aligned_mask)


def run_registration(nose_rigid: str, nose_mask: str, config_file: str,
                     num_infix: list):
    log.info("Starting temporal registration")
    cmd = [
        "python", str(PIPELINE_DIR / "register.py"),
        "--prefix", "img_",
        "--infix",
    ] + [str(i) for i in num_infix] + [
        "--suffix", ".nii.gz",
        "--parin", config_file,
        "--dofout", "ffd_{i}.dof.gz",
    ]
    if nose_rigid.lower().startswith("y"):
        cmd += ["--mask", nose_mask]
    run(cmd)


def apply_transforms(aligned_mask: str, time_points: int):
    log.info("Applying transforms to generate STLs...")
    for i in range(1, time_points):
        run(["mirtk", "transform-points", "seg_0.stl", f"seg_{i}.stl",
             "-dofin", f"ffd_{i}.dof.gz"])
    log.info("All STL transforms complete")

    log.info("Generating binary masks...")
    for i in range(1, time_points):
        run(["mirtk", "extract-pointset-surface",
             "-input", f"seg_{i}.stl", "-mask", f"seg_{i}.nii.gz",
             "-reference", aligned_mask])
    log.info("All masks generated")


def generate_ffds_csv(time_points: int, dt: int):
    if not Path("ffds.csv").exists():
        log.info("Generating ffds.csv for interpolation")
        lines = ["dof,t", "identity,0"]
        for i in range(1, time_points):
            t = i * dt
            lines.append(f"ffd_{i}.dof.gz,{t}")
        Path("ffds.csv").write_text("\n".join(lines) + "\n")
    else:
        log.warning("ffds.csv already exists, skipping")


def run_interpolation(first_image: str, aligned_stl: str, table_name: str,
                      interp_step: str, align_or_not: str, be_str: str,
                      time_end: int, downsample: str):
    log.info("Running cubic spline interpolation")
    Path("interpolated_stls").mkdir(exist_ok=True)

    cmd = [
        "python", str(PIPELINE_DIR / "interpolate.py"),
        "--target", first_image,
        "--dofs", "ffds.csv",
        "--mesh", aligned_stl,
        "--start", "0",
        "--stop", str(time_end),
        "--step", interp_step,
        "--output-mesh", f"./interpolated_stls/out_{{t:08.3f}}_{align_or_not}_{be_str}.stl",
        "--output-table", f"./{table_name}",
    ]
    try:
        ds_val = int(downsample)
        if ds_val > 0:
            cmd += ["--downsample", downsample]
    except (ValueError, TypeError):
        pass

    run(cmd)


# =============================================================================
# Interactive STL selection menu (used in both reuse-reg and full pipeline)
# =============================================================================
def interactive_stl_selection(seg_mask: str, man_seg_stl: str):
    """Interactive menu for choosing how to get the STL. Returns nothing; writes man_seg_stl."""
    has_existing = (WORK_DIR / "manual_seg.stl").is_file()
    if has_existing:
        log.info("Found existing manual_seg.stl in subject folder")

    print("")
    print("How do you want to get the STL for propagation?")
    print("  1) Auto-generate from segmentation mask")
    print("  2) Provide path to an existing STL file")
    if has_existing:
        print("  3) Use detected manual_seg.stl from subject folder")
    stl_choice = input("Choose [1/2/3]: ").strip()

    if stl_choice == "2":
        custom_stl_path = input("Path to STL file: ").strip()
        custom_stl_path = str(resolve_path(custom_stl_path))
        if not Path(custom_stl_path).is_file():
            error(f"STL file not found: {custom_stl_path}")
        log.info(f"Using: {custom_stl_path}")
        shutil.copy2(custom_stl_path, man_seg_stl)
    elif stl_choice == "3":
        if has_existing:
            log.info("Using existing manual_seg.stl")
            shutil.copy2(str(WORK_DIR / "manual_seg.stl"), man_seg_stl)
        else:
            error("No manual_seg.stl found in subject folder")
    else:
        extract_stl_from_mask(seg_mask, man_seg_stl)


# =============================================================================
# CLI argument parsing
# =============================================================================
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="MIRTK Registration Pipeline - Dual Mode (Interactive / CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="All options are optional. If omitted, interactive prompts are shown.",
    )
    p.add_argument("--align", dest="align", default="", help="Alignment mode (yes|no)")
    p.add_argument("--dim", dest="dim", default="", help="Image dimension (4D|3D)")
    p.add_argument("--nose-rigid", dest="nose_rigid", default="", help="Nose rigid-only mode (yes|no)")
    p.add_argument("--nose-mask", dest="nose_mask", default="", help="Nose rigid mask file")
    p.add_argument("--image4d", dest="image4d", default="", help="4D image file")
    p.add_argument("--static-image", dest="static_image", default="", help="Static/reference image")
    p.add_argument("--segmask", dest="segmask", default="", help="Segmentation mask")
    p.add_argument("--manual-stl", dest="manual_stl", default="", help="Pre-existing manual STL (skip auto-generation)")
    p.add_argument("--frames-dir", dest="frames_dir", default="", help="Folder containing 3D frame images (for 3D mode)")
    p.add_argument("--subject", dest="subject", default="", help="Subject/project name")
    p.add_argument("--ds", dest="ds", default="", help="Alignment downsampling (1-10)")
    p.add_argument("--levels", dest="levels", default="", help="Alignment levels (2 or 4)")
    p.add_argument("--align-be", dest="align_be", default="", help="Alignment bending energy")
    p.add_argument("--align-mode", dest="align_mode", default="", help="Alignment mode (config|manual)")
    p.add_argument("--initial", dest="initial", default="", help="Initial alignment (Id, guess, or dof.gz)")
    p.add_argument("--motion-be", dest="motion_be", default="", help="Motion registration bending energy")
    p.add_argument("--interp-step", dest="interp_step", default="", help="Interpolation step (ms)")
    p.add_argument("--downsample", dest="downsample", default="", help="Star table row downsampling factor")
    p.add_argument("--input-txt", dest="input_txt", default="./input.txt", help="Path to input.txt (default: ./input.txt)")
    p.add_argument("--config", dest="config", default=str(DEFAULT_CONFIG), help="Path to custom register.cfg")
    p.add_argument("--config-ct", dest="config_ct", action="store_true", help="Use CT registration config")
    p.add_argument("--config-mri-large", dest="config_mri_large", action="store_true", help="Use MRI config for large images")
    p.add_argument("--output-dir", dest="output_dir", default="", help="Output directory (overrides auto naming)")
    p.add_argument("--reg-only", dest="reg_only", action="store_true", help="Registration only (no segmask needed, stops after FFDs)")
    p.add_argument("--reuse-reg", dest="reuse_reg", default="", help="Reuse existing registration from DIR")
    p.add_argument("--skip-video", dest="skip_video", action="store_true", help="Skip post-processing video generation")
    return p


# =============================================================================
# Main
# =============================================================================
def main():
    # Detect CLI mode: any args beyond the script name
    cli_mode = len(sys.argv) > 1

    # Enable Tab completion of file/dir paths at interactive input() prompts.
    from mirtk_pipeline._completion import enable_path_completion
    enable_path_completion()

    parser = build_parser()
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass
    args = parser.parse_args()

    # Handle config shortcut flags
    if args.config_ct:
        args.config = str(PIPELINE_DIR / "config" / "register_ct.cfg")
    elif args.config_mri_large:
        args.config = str(PIPELINE_DIR / "config" / "register_mri_large.cfg")

    # =========================================================================
    # Pre-flight checks
    # =========================================================================
    if not shutil.which("mirtk"):
        error("mirtk not found on PATH. Run: conda activate mirtk")
    if not shutil.which("python"):
        error("python not found on PATH. Run: conda activate mirtk")

    log.info("MIRTK Registration Pipeline")
    log.info(f"Using mirtk: {shutil.which('mirtk')}")
    log.info(f"Using python: {shutil.which('python')}")
    log.info(f"Working directory: {WORK_DIR}")
    print("")

    # --- Validate mutually exclusive flags ---
    if args.reg_only and args.reuse_reg:
        error("--reg-only and --reuse-reg cannot be used together")

    if args.reg_only:
        log.info("MODE: Registration only (will stop after FFDs, no segmask needed)")
    elif args.reuse_reg:
        log.info("MODE: Reuse existing registration (propagation only)")
    else:
        log.info("MODE: Full pipeline")
    print("")

    # --- Ask about CSA prepare-slicer at the end ---
    opt_prepare_slicer = False
    if shutil.which("mirtk-prepare-slicer"):
        run_prepare = input(
            f"\033[0;32m[INFO]\033[0m Run prepare-slicer for CSA pipeline after completion? [y/N]: "
        ).strip()
        if run_prepare.lower() == "y":
            opt_prepare_slicer = True
            log.info("Will run prepare-slicer after pipeline completes.")
        print("")

    # =========================================================================
    # --reuse-reg: Skip to propagation using existing results
    # =========================================================================
    if args.reuse_reg:
        reuse_dir = resolve_path(args.reuse_reg)
        if not reuse_dir.is_dir():
            error(f"Reuse directory not found: {reuse_dir}")

        # Verify FFDs exist
        if not list(reuse_dir.glob("ffd_*.dof.gz")):
            error(f"No ffd_*.dof.gz found in {reuse_dir}")
        if not (reuse_dir / "ffds.csv").is_file():
            error(f"ffds.csv not found in {reuse_dir}")
        if not (reuse_dir / "img_0.nii.gz").is_file():
            error(f"img_0.nii.gz not found in {reuse_dir}")

        # Read timing from input.txt (check reuse dir first, then WORK_DIR)
        input_txt_path = args.input_txt
        if (reuse_dir / "input.txt").is_file():
            input_txt_path = str(reuse_dir / "input.txt")
        input_txt_path = resolve_path(input_txt_path)
        timing = parse_input_txt(input_txt_path)

        # Collect propagation parameters
        seg_mask = get_param("What is the manual segmentation mask name?: ", args.segmask)
        agn = get_param("Do you need align the highRes to timeFrame 0? [y,n]: ", args.align)

        static_image = ""
        ds = ""
        lev = ""
        a_be = ""
        initial = ""
        align_mode = "manual"

        if agn.lower().startswith("y"):
            static_image = get_param("What is the StaticImage name?: ", args.static_image)
            ds = get_param("Please say the alignment ds in range 1 to 10: ", args.ds)
            lev = get_param("Please say the alignment levels choose 2 or 4: ", args.levels)
            a_be = get_param("Please say the alignment bending energy (default 0.001): ", args.align_be)
            initial = get_param("Please say the initial alignment (Id, guess, or dof.gz): ", args.initial)
            align_or_not = "aligned"
        else:
            align_or_not = "noalign"

        inte_step = get_param("Please tell the interpolation step (ms): ", args.interp_step)
        downsample = args.downsample if args.downsample else "5000"

        # Resolve paths
        seg_mask_path = resolve_path(seg_mask)
        if not seg_mask_path.is_file():
            error(f"Segmentation mask not found: {seg_mask_path}")

        if agn.lower().startswith("y"):
            static_image_path = resolve_path(static_image)
            if not static_image_path.is_file():
                error(f"Static image not found: {static_image_path}")
            static_image = str(static_image_path)

        if args.manual_stl:
            manual_stl_path = resolve_path(args.manual_stl)
            if not manual_stl_path.is_file():
                error(f"Manual STL not found: {manual_stl_path}")
            args.manual_stl = str(manual_stl_path)

        # cd into existing results dir
        os.chdir(str(reuse_dir))
        results_dir = Path.cwd()
        log.info(f"Reusing registration from: {results_dir}")

        # Start logging
        add_file_handler(results_dir / "pipeline.log")
        log.info(f"Logging to: {results_dir / 'pipeline.log'}")

        # Set variables
        aligned_stl = "seg_0.stl"
        aligned_mask = "seg_0.nii.gz"
        man_seg_stl = "manual_seg.stl"
        first_image_link = "img_0.nii.gz"
        be = "reused"
        be_str = "reused"
        table_name = f"{args.output_dir if args.output_dir else 'propagation'}_{align_or_not}.csv"

        # --- Stage 2: STL extraction / manual STL + alignment ---
        if args.manual_stl:
            log.info(f"Using provided manual STL: {args.manual_stl}")
            shutil.copy2(args.manual_stl, man_seg_stl)
        else:
            interactive_stl_selection(str(seg_mask_path), man_seg_stl)

        if agn.lower().startswith("y"):
            # Reusing a prior results dir: force a real re-alignment. The dir already
            # holds seg_0.stl / seg_0.nii.gz / alignment.dof.gz from the earlier run,
            # so without force=True perform_alignment would silently skip and reuse them.
            perform_alignment(
                static_image, first_image_link, man_seg_stl,
                aligned_stl, aligned_mask, "alignment.dof.gz",
                initial, align_mode, "./register_work.cfg", ds, lev, a_be,
                force=True,
            )
        else:
            skip_alignment(man_seg_stl, str(seg_mask_path), aligned_stl, aligned_mask)

        # --- Stage 4: Apply transforms ---
        apply_transforms(aligned_mask, timing["time_points"])

        # --- Stage 8: Interpolation ---
        run_interpolation(
            first_image_link, aligned_stl, table_name,
            inte_step, align_or_not, be_str,
            timing["time_end"], downsample,
        )

        # --- Stage 9: STL video generation ---
        if not args.skip_video:
            log.info("Generating STL motion video...")
            try:
                run(
                    ["python", str(PIPELINE_DIR / "visualize.py"),
                     str(results_dir / "interpolated_stls"),
                     "--duration", "10",
                     "--csv", str(results_dir / table_name)],
                    check=True,
                )
            except subprocess.CalledProcessError:
                log.warning("Video generation failed (missing ffmpeg or pyvista?). Skipping.")

        print("")
        log.info("Propagation complete!")
        log.info(f"Results folder: {results_dir}")
        log.info(f"Star table:     {results_dir / table_name}")
        log.info(f"Pipeline log:   {results_dir / 'pipeline.log'}")
        sys.exit(0)

    # =========================================================================
    # Normal flow: Collect parameters (interactive or CLI)
    # =========================================================================
    agn = get_param("Do you need align the highRes to timeFrame 0? [y,n]: ", args.align)
    dim = get_param("Do you use 4D image as input or multiple 3D images? [4D,3D]: ", args.dim)

    # Validate dim
    if dim not in ("4D", "3D"):
        error(f"Dimension must be '4D' or '3D', got: '{dim}'")

    nro = get_param("Do you want to make the nose rigid motion only? [y,n]: ", args.nose_rigid)

    nose_rigid_only = ""
    if nro.lower().startswith("y"):
        nose_rigid_only = get_param("What is the image mask for Nose Rigid only?: ", args.nose_mask)

    # Dimension-specific inputs
    image_4d = ""
    frames_dir = ""
    if dim == "4D":
        image_4d = get_param("What is the 4D image name?: ", args.image4d)
    elif dim == "3D":
        frames_dir = get_param("Path to folder containing 3D frame images: ", args.frames_dir)

    static_image = ""
    if agn.lower().startswith("y"):
        static_image = get_param("What is the StaticImage name?: ", args.static_image)

    # Skip segmask in --reg-only mode
    seg_mask = ""
    if not args.reg_only:
        seg_mask = get_param("What is the manual segmentation mask name?: ", args.segmask)

    # Read timing parameters
    input_txt_path = resolve_path(args.input_txt)
    timing = parse_input_txt(input_txt_path)

    subject = get_param("What is the project and subject name: ", args.subject)

    # Alignment parameters
    ds = "1"
    lev = ""
    a_be = ""
    initial = ""
    align_mode = "manual"

    if agn.lower().startswith("y"):
        initial = get_param("Please say the initial alignment (Id, guess, or dof.gz): ", args.initial)
        if args.align_mode:
            align_mode = args.align_mode
            if align_mode == "manual":
                ds = get_param("Please say the alignment ds in range 1 to 10: ", args.ds)
                lev = get_param("Please say the alignment levels choose 2 or 4: ", args.levels)
                a_be = get_param("Please say the alignment bending energy (default 0.001): ", args.align_be)
        else:
            print("")
            print("Alignment registration parameters:")
            print("  1) Use same config as pairwise registration")
            print("  2) Manual input (ds, levels, bending energy)")
            align_choice = input("Select [1/2]: ").strip()
            if align_choice == "1":
                align_mode = "config"
            else:
                align_mode = "manual"
                ds = get_param("Please say the alignment ds in range 1 to 10: ", args.ds)
                lev = get_param("Please say the alignment levels choose 2 or 4: ", args.levels)
                a_be = get_param("Please say the alignment bending energy (default 0.001): ", args.align_be)

    be = get_param("What is the bending energy for Motion Registration (default 0.001): ", args.motion_be)

    # Only ask interpolation params if not reg-only
    inte_step = ""
    if not args.reg_only:
        inte_step = get_param("Please tell the interpolation step (ms): ", args.interp_step)

    # Downsample parameter
    downsample = args.downsample if args.downsample else "5000"

    # Interactive config template selection (only if --config/--config-ct not given)
    opt_config = args.config
    if opt_config == str(DEFAULT_CONFIG) and not cli_mode:
        print("")
        print("Select registration config template:")
        print("  1) MRI        (cine MRI, small images, X-axis frozen, full resolution)")
        print("  2) MRI-large  (large images, X-axis frozen, 4 levels, downsampled)")
        print("  3) CT         (isotropic CT, all axes active, memory-efficient)")
        print("  4) Custom config file")
        config_choice = input("Choose [1/2/3/4]: ").strip()
        if config_choice == "2":
            opt_config = str(PIPELINE_DIR / "config" / "register_mri_large.cfg")
        elif config_choice == "3":
            opt_config = str(PIPELINE_DIR / "config" / "register_ct.cfg")
        elif config_choice == "4":
            opt_config = input("Path to config file: ").strip()
        else:
            opt_config = str(DEFAULT_CONFIG)

    # =========================================================================
    # Resolve all input paths to absolute
    # =========================================================================
    if dim == "4D":
        image_4d_path = resolve_path(image_4d)
        if not image_4d_path.is_file():
            error(f"4D image not found: {image_4d_path}")
        image_4d = str(image_4d_path)
    elif dim == "3D":
        frames_dir_path = resolve_path(frames_dir)
        if not frames_dir_path.is_dir():
            error(f"Frames directory not found: {frames_dir_path}")
        frames_dir = str(frames_dir_path)

    if agn.lower().startswith("y"):
        static_image_path = resolve_path(static_image)
        if not static_image_path.is_file():
            error(f"Static image not found: {static_image_path}")
        static_image = str(static_image_path)

    if not args.reg_only:
        seg_mask_path = resolve_path(seg_mask)
        if not seg_mask_path.is_file():
            error(f"Segmentation mask not found: {seg_mask_path}")
        seg_mask = str(seg_mask_path)

    if nose_rigid_only:
        nose_rigid_only_path = resolve_path(nose_rigid_only)
        if not nose_rigid_only_path.is_file():
            error(f"Nose rigid mask not found: {nose_rigid_only_path}")
        nose_rigid_only = str(nose_rigid_only_path)

    if args.manual_stl:
        manual_stl_path = resolve_path(args.manual_stl)
        if not manual_stl_path.is_file():
            error(f"Manual STL not found: {manual_stl_path}")
        args.manual_stl = str(manual_stl_path)

    opt_config_path = resolve_path(opt_config)
    if not opt_config_path.is_file():
        error(f"Config file not found: {opt_config_path}")
    opt_config = str(opt_config_path)

    # =========================================================================
    # Subject-first output folder naming
    # =========================================================================
    if agn.lower().startswith("y"):
        align_or_not = "aligned"
        if align_mode == "config":
            # Extract config name from filename (e.g. register_mri_large.cfg -> mri_large)
            config_basename = Path(opt_config).stem  # register_mri_large
            align_config_name = re.sub(r"^register_", "", config_basename)
            align_tag = f"cfg_{align_config_name}"
        else:
            align_tag = f"ds{ds}_l{lev}_aBE{a_be}"
        auto_output_dir = f"{subject}_aligned_{align_tag}_be{be}"
    else:
        align_tag = ""
        auto_output_dir = f"{subject}_noalign_be{be}"
        align_or_not = "noalign"

    output_dir = args.output_dir if args.output_dir else auto_output_dir
    table_name = f"{output_dir}.csv"

    be_str = f"{align_tag}_be{be}" if align_tag else f"be{be}"

    aligned_stl = "seg_0.stl"
    aligned_mask = "seg_0.nii.gz"
    man_seg_stl = "manual_seg.stl"
    first_image_link = "img_0.nii.gz"

    # =========================================================================
    # Create output dir FIRST, put config inside, cd into it
    # =========================================================================
    output_path = WORK_DIR / output_dir

    if output_path.is_dir():
        if cli_mode:
            log.warning(f"Output dir '{output_dir}' exists. Overwriting (CLI mode).")
            shutil.rmtree(str(output_path))
        else:
            log.warning(f"Output dir '{output_dir}' already exists.")
            overwrite = input("Overwrite? [y,n]: ").strip()
            if overwrite.lower().startswith("y"):
                shutil.rmtree(str(output_path))
            else:
                error("Aborted. Choose a different --output-dir or remove the existing folder.")

    output_path.mkdir()

    # Create working config INSIDE results folder (kept permanently for reproducibility)
    config_text = Path(opt_config).read_text()
    # B5 fix: replace bending energy line
    config_text = re.sub(r"\+ (.*) BE", f"+ {be} BE", config_text)
    (output_path / "register_work.cfg").write_text(config_text)
    log.info(f"register_work.cfg saved in results folder (bending energy = {be})")

    # cd into results folder -- everything runs here from now on
    os.chdir(str(output_path))
    results_dir = Path.cwd()
    log.info(f"All processing will run inside: {results_dir}")

    # Start logging (duplicate all output to pipeline.log)
    add_file_handler(results_dir / "pipeline.log")
    log.info(f"Logging to: {results_dir / 'pipeline.log'}")

    # =========================================================================
    # Stage 1: Image extraction and setup
    # =========================================================================
    if dim == "4D":
        extract_4d_frames(Path(image_4d), timing["time_points"], timing["begin_point"])
        create_symlinks("staticFrom4D", timing["time_points"], timing["begin_point"])
    elif dim == "3D":
        copy_3d_frames(Path(frames_dir), timing["time_points"], timing["begin_point"])
        create_symlinks("staticImage", timing["time_points"], timing["begin_point"])

    # =========================================================================
    # --reg-only: generate ffds.csv and stop here
    # =========================================================================
    if args.reg_only:
        # Stage 3: Registration
        run_registration(nro, nose_rigid_only, "./register_work.cfg", timing["num_infix"])

        # Stage 7: Generate ffds.csv
        generate_ffds_csv(timing["time_points"], timing["dt"])

        # Copy input.txt into results folder for later --reuse-reg
        try:
            shutil.copy2(str(input_txt_path), str(results_dir / "input.txt"))
        except Exception:
            pass

        print("")
        log.info("Registration-only mode complete!")
        log.info(f"FFD transforms saved in: {results_dir}")
        log.info("To propagate STL motion later, run:")
        log.info(f"  mirtk-pipeline --reuse-reg {results_dir} --segmask <mask.nii.gz> --manual-stl <stl> --interp-step <step_ms>")
        log.info(f"Pipeline log:   {results_dir / 'pipeline.log'}")
        sys.exit(0)

    # =========================================================================
    # Stage 2: STL extraction / manual STL + alignment
    # =========================================================================
    if args.manual_stl:
        log.info(f"Using provided manual STL: {args.manual_stl}")
        shutil.copy2(args.manual_stl, man_seg_stl)
    else:
        interactive_stl_selection(seg_mask, man_seg_stl)

    if agn.lower().startswith("y"):
        perform_alignment(
            static_image, first_image_link, man_seg_stl,
            aligned_stl, aligned_mask, "alignment.dof.gz",
            initial, align_mode, "./register_work.cfg", ds, lev, a_be,
        )
    else:
        skip_alignment(man_seg_stl, seg_mask, aligned_stl, aligned_mask)

    # =========================================================================
    # Stage 3: Temporal registration
    # =========================================================================
    run_registration(nro, nose_rigid_only, "./register_work.cfg", timing["num_infix"])

    # =========================================================================
    # Stage 4: Apply transforms to all time points
    # =========================================================================
    apply_transforms(aligned_mask, timing["time_points"])

    # =========================================================================
    # Stage 5: Generate ffds.csv and run interpolation
    # =========================================================================
    generate_ffds_csv(timing["time_points"], timing["dt"])

    run_interpolation(
        first_image_link, aligned_stl, table_name,
        inte_step, align_or_not, be_str,
        timing["time_end"], downsample,
    )

    # =========================================================================
    # Stage 6: STL motion video generation
    # =========================================================================
    if not args.skip_video:
        log.info("Generating STL motion video...")
        try:
            run(
                ["python", str(PIPELINE_DIR / "visualize.py"),
                 str(results_dir / "interpolated_stls"),
                 "--duration", "10",
                 "--csv", str(results_dir / table_name)],
                check=True,
            )
        except subprocess.CalledProcessError:
            log.warning("Video generation failed (missing ffmpeg or pyvista?). Skipping.")
    else:
        log.info("Video generation skipped (--skip-video)")

    # =========================================================================
    # Done
    # =========================================================================
    print("")
    log.info("Pipeline complete!")
    log.info(f"Results folder: {results_dir}")
    log.info(f"Star table:     {results_dir / table_name}")
    log.info(f"Config used:    {results_dir / 'register_work.cfg'}")
    log.info(f"Pipeline log:   {results_dir / 'pipeline.log'}")

    # =========================================================================
    # Stage 7: Prepare for CSA slicer (if opted in)
    # =========================================================================
    if opt_prepare_slicer:
        print("")
        log.info("Running prepare-slicer...")
        # Pass the subject the user already provided so the CSA folder gets the
        # right name (otherwise prepare-slicer falls back to filename detection,
        # which inside the results dir would pick up e.g. img_0.nii.gz -> "img").
        prep_cmd = ["mirtk-prepare-slicer", "--reg-dir", str(results_dir)]
        if subject:
            prep_cmd += ["--subject", subject]
        run(prep_cmd)
    else:
        if shutil.which("mirtk-prepare-slicer"):
            log.info(f"To prepare for CSA: mirtk-prepare-slicer --reg-dir {results_dir}")


if __name__ == "__main__":
    main()
