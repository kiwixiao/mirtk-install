#!/bin/bash
# =============================================================================
# Prepare registration output for CSA pipeline
# =============================================================================
# Creates a subject folder with registration/, surface/, and motion/ subfolders.
# Copies FFD transforms, time-zero image, input.txt, and seg_0.stl.
# Use --legacy for the old LeftNoseDecending/RightNose layout.
# =============================================================================

set -o errexit
set -o pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Dry-run wrappers
do_mkdir() { if [ "$opt_dry_run" = true ]; then info "mkdir -p $1"; else mkdir -p "$1"; fi; }
do_cp()    { if [ "$opt_dry_run" = true ]; then info "cp $*"; else cp "$@"; fi; }

# --- CLI argument parsing ---
opt_output_dir=""
opt_reg_dir=""
opt_legacy=false
opt_dry_run=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --output-dir)   opt_output_dir="$2"; shift 2 ;;
        --reg-dir)      opt_reg_dir="$2"; shift 2 ;;
        --legacy)       opt_legacy=true; shift ;;
        --dry-run)      opt_dry_run=true; shift ;;
        --help)
            echo "Usage: prepare_slicer.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --reg-dir DIR      Path to registration results folder"
            echo "  --output-dir DIR   Where to create the subject folder (default: ../)"
            echo "  --legacy           Use old LeftNoseDecending/RightNose layout"
            echo "  --dry-run          Show what would be done without copying"
            exit 0
            ;;
        *) error "Unknown option: $1" ;;
    esac
done

# --- Find registration results folder ---
if [ -z "$opt_reg_dir" ]; then
    # Auto-detect: look for folders containing ffd_*.dof.gz
    reg_dirs=()
    for d in */; do
        if ls "${d}"ffd_*.dof.gz &>/dev/null; then
            reg_dirs+=("${d%/}")
        fi
    done
    if [ ${#reg_dirs[@]} -eq 0 ]; then
        error "No registration results folder found (no ffd_*.dof.gz files). Use --reg-dir to specify."
    elif [ ${#reg_dirs[@]} -eq 1 ]; then
        opt_reg_dir="${reg_dirs[0]}"
        info "Auto-detected registration folder: $opt_reg_dir"
    else
        echo "Multiple registration folders found:"
        for i in "${!reg_dirs[@]}"; do
            echo "  $((i+1))) ${reg_dirs[$i]}"
        done
        read -e -p "Select [1-${#reg_dirs[@]}]: " reg_choice
        opt_reg_dir="${reg_dirs[$((reg_choice-1))]}"
    fi
fi

[ -d "$opt_reg_dir" ] || error "Registration folder not found: $opt_reg_dir"

# --- Detect subject ID ---
first_nii=$(ls *.nii* 2>/dev/null | head -1)
if [ -z "$first_nii" ]; then
    first_nii=$(ls "$opt_reg_dir"/*_0.nii.gz 2>/dev/null | head -1)
fi
if [ -z "$first_nii" ]; then
    error "No NIfTI files found to detect subject ID"
fi
sub=$(basename "$first_nii" | cut -d '_' -f 1)
info "Detected subject: $sub"

# --- Determine output location ---
if [ -z "$opt_output_dir" ]; then
    read -e -p "Output directory (default: ../): " user_output
    opt_output_dir="${user_output:-..}"
fi

# =============================================================================
# Legacy mode (old LeftNoseDecending/RightNose layout)
# =============================================================================
if [ "$opt_legacy" = true ]; then
    mainFolder="${sub}CSA"
    output_path="$opt_output_dir/$mainFolder"
    do_mkdir "$output_path/LeftNoseDecending/FFD"
    do_mkdir "$output_path/RightNose/FFD"

    for side_path in "$output_path/LeftNoseDecending/FFD" "$output_path/RightNose/FFD"; do
        do_cp "$opt_reg_dir"/ffd_*.dof.gz "$side_path/"
        t0_image=$(ls "$opt_reg_dir"/*_0.nii.gz 2>/dev/null | head -1)
        [ -n "$t0_image" ] && do_cp "$t0_image" "$side_path/"
        [ -f "input.txt" ] && do_cp input.txt "$side_path/"
    done

    info "Legacy layout created: $output_path"
    exit 0
fi

# =============================================================================
# New standard layout
# =============================================================================
output_path="$opt_output_dir/$sub"
do_mkdir "$output_path/registration"
do_mkdir "$output_path/surface"
do_mkdir "$output_path/motion/stl"
do_mkdir "$output_path/motion/centerlines"

# --- registration/ ---
do_cp "$opt_reg_dir"/ffd_*.dof.gz "$output_path/registration/"
info "Copied FFD files"

if [ -f "$opt_reg_dir/ffds.csv" ]; then
    do_cp "$opt_reg_dir/ffds.csv" "$output_path/registration/"
    info "Copied ffds.csv"
elif [ -f "ffds.csv" ]; then
    do_cp ffds.csv "$output_path/registration/"
    info "Copied ffds.csv from current dir"
fi

t0_image=$(ls "$opt_reg_dir"/*_0.nii.gz 2>/dev/null | head -1)
if [ -n "$t0_image" ]; then
    do_cp "$t0_image" "$output_path/registration/"
    info "Copied time-zero image: $(basename "$t0_image")"
fi

if [ -f "input.txt" ]; then
    do_cp input.txt "$output_path/registration/"
    info "Copied input.txt"
fi

# --- surface/ ---
if [ -f "$opt_reg_dir/seg_0.stl" ]; then
    do_cp "$opt_reg_dir/seg_0.stl" "$output_path/surface/"
    info "Copied seg_0.stl"
elif [ -f "seg_0.stl" ]; then
    do_cp seg_0.stl "$output_path/surface/"
    info "Copied seg_0.stl from current dir"
else
    warn "seg_0.stl not found — surface/ folder is empty"
fi

info "Subject folder ready: $output_path"
echo ""
echo "  $output_path/"
echo "  ├── registration/   (FFDs, ffds.csv, img_0, input.txt)"
echo "  ├── surface/        (seg_0.stl)"
echo "  └── motion/"
echo "      ├── stl/        (empty — populated by interpolation)"
echo "      └── centerlines/ (empty — populated by CSA pipeline)"
