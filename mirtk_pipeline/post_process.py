#!/usr/bin/env python

"""Post-processing: generate QC videos from registration output.

Optional step -- requires ffmpeg for video encoding and uses nifti_to_slices.py
(bundled in this pipeline) for PNG slice extraction.

Must be run from inside the results folder.
"""

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Colored logging (matches shell helpers: green INFO, yellow WARN, red ERROR)
# ---------------------------------------------------------------------------
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"

PIPELINE_DIR = Path(__file__).resolve().parent


class _ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: NC,
        logging.INFO: GREEN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: RED,
    }

    def format(self, record):
        color = self.COLORS.get(record.levelno, NC)
        record.msg = "{}[{}]{} {}".format(color, record.levelname, NC, record.msg)
        return super().format(record)


log = logging.getLogger(__name__)


def _setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_ColorFormatter())
    log.addHandler(handler)
    log.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_pngs(directory: Path) -> int:
    """Return the number of .png files in *directory* (non-recursive)."""
    if not directory.is_dir():
        return 0
    return len(sorted(directory.glob("*.png")))


def _seq_formatted(start: int, stop: int, step: int = 1) -> list:
    """Replicate ``seq -f %03g start step stop`` as zero-padded strings."""
    return ["{:03d}".format(i) for i in range(start, stop + 1, step)]


def _run_ffmpeg_encode(pattern_glob: str, output: Path):
    """Encode a glob of PNGs into an MP4 (libx264, crf 15, yuv420p)."""
    cmd = [
        "ffmpeg", "-y",
        "-framerate", "5",
        "-pattern_type", "glob",
        "-i", pattern_glob,
        "-c:v", "libx264",
        "-crf", "15",
        "-pix_fmt", "yuv420p",
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        str(output),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def _run_ffmpeg_overlay(seg_video: Path, img_video: Path, output: Path):
    """Overlay segmentation on image video (50 % opacity, 3x upscale)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(seg_video),
        "-i", str(img_video),
        "-filter_complex",
        "[1:v]format=rgba,colorchannelmixer=aa=0.5[fg];[0][fg]overlay,scale=iw*3:-1",
        str(output),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


# ---------------------------------------------------------------------------
# Per-direction video generation
# ---------------------------------------------------------------------------

def _generate_direction_videos(
    axis: str,
    seg_prefix: str,
    img_prefix: str,
    ovl_prefix: str,
    png_mask_dir: Path,
    png_image_dir: Path,
    video_dir: Path,
    timepoints: int,
    is_x: bool = False,
    png_image_axis_dir: Path = None,
):
    """Generate seg / image / overlay videos for one axis direction.

    For the x-direction the shell script uses a stride (``instep``) between
    the mask resolution and the image resolution.  For y and z every slice
    index is used for both mask and image.
    """
    mask_axis_dir = png_mask_dir / axis
    image_axis_dir = png_image_axis_dir if png_image_axis_dir else (png_image_dir / axis)

    mask_png_count = _count_pngs(mask_axis_dir)
    image_png_count = _count_pngs(image_axis_dir)

    if mask_png_count == 0:
        log.warning("No PNG slices in %s. Skipping %s-direction.", mask_axis_dir, axis)
        return

    mask_slices = mask_png_count // timepoints
    image_slices = image_png_count // timepoints

    if is_x:
        # x-direction: seg uses strided indices starting at 0,
        # image uses seq 1..N (bash ``seq N`` starts at 1)
        if image_slices == 0:
            log.warning("No image PNG slices for x-direction. Skipping.")
            return
        instep = mask_slices // image_slices if image_slices > 0 else 1
        seg_indices = _seq_formatted(0, mask_slices - 1, instep)
        img_indices = _seq_formatted(1, image_slices - 1)
    else:
        # y / z: bash ``seq N`` produces 1..N, so indices are 1..(slices-1)
        seg_indices = _seq_formatted(1, mask_slices - 1)
        img_indices = seg_indices

    # Segmentation videos
    for idx in seg_indices:
        pattern = str(mask_axis_dir / "{}*slice{}.png".format(seg_prefix, idx))
        out = video_dir / "{}{}_{}.mp4".format(seg_prefix, idx, axis)
        try:
            _run_ffmpeg_encode(pattern, out)
        except subprocess.CalledProcessError:
            log.warning("ffmpeg failed for seg slice %s %s-direction.", idx, axis)

    # Image videos
    for idx in img_indices:
        pattern = str(image_axis_dir / "{}*slice{}.png".format(img_prefix, idx))
        out = video_dir / "{}{}_{}.mp4".format(img_prefix, idx, axis)
        try:
            _run_ffmpeg_encode(pattern, out)
        except subprocess.CalledProcessError:
            log.warning("ffmpeg failed for image slice %s %s-direction.", idx, axis)

    # Overlay videos (only where both exist)
    overlay_indices = img_indices if is_x else seg_indices
    for idx in overlay_indices:
        seg_mp4 = video_dir / "{}{}_{}.mp4".format(seg_prefix, idx, axis)
        img_mp4 = video_dir / "{}{}_{}.mp4".format(img_prefix, idx, axis)
        ovl_mp4 = video_dir / "{}{}_{}.mp4".format(ovl_prefix, idx, axis)
        if seg_mp4.is_file() and img_mp4.is_file():
            try:
                _run_ffmpeg_overlay(seg_mp4, img_mp4, ovl_mp4)
            except subprocess.CalledProcessError:
                log.warning("ffmpeg overlay failed for slice %s %s-direction.", idx, axis)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    _setup_logging()

    parser = argparse.ArgumentParser(
        description="Post-processing: generate QC videos from registration output."
    )
    parser.add_argument(
        "video_subdir",
        nargs="?",
        default="video",
        help="Name of the video output subdirectory (default: video)",
    )
    args = parser.parse_args()

    # Shell script treats "." same as default
    if args.video_subdir == ".":
        args.video_subdir = "video"

    # ------------------------------------------------------------------
    # Dependency checks
    # ------------------------------------------------------------------
    if shutil.which("ffmpeg") is None:
        log.warning("ffmpeg not found. Cannot generate videos.")
        return

    if shutil.which("python") is None:
        log.warning("python not found. Cannot generate PNG slices.")
        return

    # ------------------------------------------------------------------
    # Locate seg_*.nii.gz in current directory
    # ------------------------------------------------------------------
    seg_files = sorted(Path(".").glob("seg_*.nii.gz"))
    timepoints = len(seg_files)
    if timepoints == 0:
        log.warning("No seg_*.nii.gz files found. Skipping video.")
        return

    # ------------------------------------------------------------------
    # Naming conventions (match shell script)
    # ------------------------------------------------------------------
    seg_prefix = "4Dseg"
    img_prefix = "4Dimage"
    ovl_prefix = "segVSimage"

    video_dir = Path(args.video_subdir)

    # Recreate video directory
    if video_dir.is_dir():
        shutil.rmtree(video_dir)
    video_dir.mkdir(parents=True)

    # ------------------------------------------------------------------
    # Combine time-series images into 4-D NIfTI
    # ------------------------------------------------------------------
    log.info("Combining segmentation masks into 4D...")
    seg_4d = Path("{}.nii.gz".format(seg_prefix))
    try:
        subprocess.run(
            ["mirtk", "combine-images"]
            + [str(f) for f in seg_files]
            + ["-output", str(seg_4d)],
            check=True,
        )
    except subprocess.CalledProcessError:
        log.error("Failed to combine segmentation masks into 4D")
        return

    log.info("Combining static images into 4D...")
    static_files = sorted(Path(".").glob("static*.nii.gz"))
    if not static_files:
        log.warning("No static*.nii.gz files found. Skipping image 4D combine.")
        return
    img_4d = Path("{}.nii.gz".format(img_prefix))
    try:
        subprocess.run(
            ["mirtk", "combine-images"]
            + [str(f) for f in static_files]
            + ["-output", str(img_4d)],
            check=True,
        )
    except subprocess.CalledProcessError:
        log.error("Failed to combine static images into 4D")
        return

    # ------------------------------------------------------------------
    # Convert to PNG slices using nifti_to_slices.py
    # ------------------------------------------------------------------
    nifti_to_slices = str(PIPELINE_DIR / "nifti_to_slices.py")
    png_mask_dir = Path("pngMask")
    png_image_dir = Path("pngImage")

    log.info("Generating PNG slices from segmentation 4D...")
    try:
        subprocess.run(
            ["python", nifti_to_slices, "-i", str(seg_4d), "-d", str(png_mask_dir), "-o", seg_prefix],
            check=True,
        )
    except subprocess.CalledProcessError:
        log.error("Failed to generate segmentation PNG slices")
        return

    log.info("Generating PNG slices from image 4D...")
    try:
        subprocess.run(
            ["python", nifti_to_slices, "-i", str(img_4d), "-d", str(png_image_dir), "-o", img_prefix],
            check=True,
        )
    except subprocess.CalledProcessError:
        log.error("Failed to generate image PNG slices")
        return

    # ------------------------------------------------------------------
    # Verify slices were generated
    # ------------------------------------------------------------------
    x_image_count = _count_pngs(png_image_dir / "x")
    if x_image_count == 0:
        log.warning("No PNG slices found. Skipping video generation.")
        return

    # ------------------------------------------------------------------
    # Generate videos for each direction
    # ------------------------------------------------------------------
    log.info("Generating x-direction videos...")
    _generate_direction_videos(
        axis="x",
        seg_prefix=seg_prefix,
        img_prefix=img_prefix,
        ovl_prefix=ovl_prefix,
        png_mask_dir=png_mask_dir,
        png_image_dir=png_image_dir,
        video_dir=video_dir,
        timepoints=timepoints,
        is_x=True,
        png_image_axis_dir=png_image_dir / "x",
    )

    log.info("Generating y-direction videos...")
    _generate_direction_videos(
        axis="y",
        seg_prefix=seg_prefix,
        img_prefix=img_prefix,
        ovl_prefix=ovl_prefix,
        png_mask_dir=png_mask_dir,
        png_image_dir=png_image_dir,
        video_dir=video_dir,
        timepoints=timepoints,
    )

    log.info("Generating z-direction videos...")
    _generate_direction_videos(
        axis="z",
        seg_prefix=seg_prefix,
        img_prefix=img_prefix,
        ovl_prefix=ovl_prefix,
        png_mask_dir=png_mask_dir,
        png_image_dir=png_image_dir,
        video_dir=video_dir,
        timepoints=timepoints,
    )

    log.info("Video generation complete. Output in: %s", video_dir)


if __name__ == "__main__":
    main()
