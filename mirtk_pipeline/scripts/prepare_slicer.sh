#!/bin/bash
# =============================================================================
# Prepare registration output for 3D Slicer
# =============================================================================
# Copies FFD transforms, time-zero image, and input.txt to a structured folder
# for visualization in 3D Slicer.
# =============================================================================

set -o errexit

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# --- CLI argument parsing ---
opt_template_dir=""
opt_output_dir=""
opt_cpap=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --template-dir) opt_template_dir="$2"; shift 2 ;;
        --output-dir)   opt_output_dir="$2"; shift 2 ;;
        --cpap)         opt_cpap="yes"; shift ;;
        --help)
            echo "Usage: prepare_slicer.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --template-dir DIR   Path to CSA template directory"
            echo "  --output-dir DIR     Base output directory (default: parent dir)"
            echo "  --cpap               Append CPAP to folder name"
            exit 0
            ;;
        *) error "Unknown option: $1" ;;
    esac
done

# --- Detect subject ID from NIfTI files ---
first_nii=$(ls *.nii* 2>/dev/null | head -1)
if [ -z "$first_nii" ]; then
    error "No NIfTI files found in current directory"
fi

sub=$(echo "$first_nii" | cut -d '_' -f 1)
info "Detected subject: $sub"

# --- Determine output folder name ---
mainFolder="${sub}CSA"
if [ -n "$opt_cpap" ]; then
    mainFolder="${mainFolder}_CPAP"
elif [[ "$first_nii" == *"Inspire"* ]]; then
    read -e -p "Is this a CPAP scan? [y/n]: " cpap_ans
    if [[ "$cpap_ans" == y* || "$cpap_ans" == Y* ]]; then
        mainFolder="${mainFolder}_CPAP"
    fi
fi

output_base="${opt_output_dir:-..}"
output_path="$output_base/$mainFolder"

info "Output folder: $output_path"

# --- Copy template if provided ---
if [ -n "$opt_template_dir" ] && [ -d "$opt_template_dir" ]; then
    mkdir -p "$output_path"
    cp -r "$opt_template_dir"/* "$output_path/"
    info "Template copied from $opt_template_dir"
fi

# --- Find and copy FFD data for each registration run ---
for reg_dir in */; do
    reg_dir="${reg_dir%/}"
    if ls "$reg_dir"/ffd_*.dof.gz &>/dev/null; then
        ffd_subdir="$output_path/${reg_dir}/FFD"
        mkdir -p "$ffd_subdir"

        cp "$reg_dir"/ffd_* "$ffd_subdir/"

        # Copy time-zero image
        t0_image=$(ls "$reg_dir"/*_0.nii.gz 2>/dev/null | head -1)
        if [ -n "$t0_image" ]; then
            cp "$t0_image" "$ffd_subdir/"
        fi

        # Copy input.txt if exists
        if [ -f "input.txt" ]; then
            cp input.txt "$ffd_subdir/"
        fi

        info "Copied FFD data from $reg_dir to $ffd_subdir"
    fi
done

info "Slicer preparation complete: $output_path"
