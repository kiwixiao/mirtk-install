#!/bin/bash
set -o errexit
set -o pipefail

# =============================================================================
# MIRTK Registration Pipeline - Dual Mode (Interactive / CLI)
# =============================================================================
# All processing runs INSIDE the results folder. Subject folder stays clean.
# Supports both interactive prompts (no args) and CLI arguments (for scripting).
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEFAULT_CONFIG="$PIPELINE_DIR/config/register.cfg"
WORK_DIR="$(pwd)"

# --- Color output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# =============================================================================
# Pre-flight checks
# =============================================================================
if ! command -v mirtk &> /dev/null; then
    error "mirtk not found on PATH. Run: conda activate mirtk"
fi

if ! command -v python &> /dev/null; then
    error "python not found on PATH. Run: conda activate mirtk"
fi

# =============================================================================
# CLI argument parsing (all optional - falls back to interactive)
# =============================================================================
opt_align=""
opt_dim=""
opt_nose_rigid=""
opt_nose_mask=""
opt_image4d=""
opt_static_image=""
opt_segmask=""
opt_subject=""
opt_ds=""
opt_levels=""
opt_align_be=""
opt_initial=""
opt_motion_be=""
opt_interp_step=""
opt_downsample=""
opt_input_txt="./input.txt"
opt_config="$DEFAULT_CONFIG"
opt_output_dir=""
opt_manual_stl=""
opt_frames_dir=""
opt_reg_only=false
opt_reuse_reg=""
opt_skip_video=false
# Track if ANY CLI arg was provided (for detecting CLI vs interactive mode)
cli_mode=false

while [[ $# -gt 0 ]]; do
    cli_mode=true
    case $1 in
        --align)        opt_align="$2"; shift 2 ;;
        --dim)          opt_dim="$2"; shift 2 ;;
        --nose-rigid)   opt_nose_rigid="$2"; shift 2 ;;
        --nose-mask)    opt_nose_mask="$2"; shift 2 ;;
        --image4d)      opt_image4d="$2"; shift 2 ;;
        --static-image) opt_static_image="$2"; shift 2 ;;
        --segmask)      opt_segmask="$2"; shift 2 ;;
        --subject)      opt_subject="$2"; shift 2 ;;
        --ds)           opt_ds="$2"; shift 2 ;;
        --levels)       opt_levels="$2"; shift 2 ;;
        --align-be)     opt_align_be="$2"; shift 2 ;;
        --initial)      opt_initial="$2"; shift 2 ;;
        --motion-be)    opt_motion_be="$2"; shift 2 ;;
        --interp-step)  opt_interp_step="$2"; shift 2 ;;
        --downsample)   opt_downsample="$2"; shift 2 ;;
        --input-txt)    opt_input_txt="$2"; shift 2 ;;
        --config)       opt_config="$2"; shift 2 ;;
        --config-ct)    opt_config="$PIPELINE_DIR/config/register_ct.cfg"; shift ;;
        --output-dir)   opt_output_dir="$2"; shift 2 ;;
        --manual-stl)   opt_manual_stl="$2"; shift 2 ;;
        --frames-dir)   opt_frames_dir="$2"; shift 2 ;;
        --reg-only)     opt_reg_only=true; shift ;;
        --reuse-reg)    opt_reuse_reg="$2"; shift 2 ;;
        --skip-video)   opt_skip_video=true; shift ;;
        --help)
            echo "Usage: run_pipeline.sh [OPTIONS]"
            echo ""
            echo "All options are optional. If omitted, interactive prompts are shown."
            echo ""
            echo "Options:"
            echo "  --align yes|no         Alignment mode"
            echo "  --dim 4D|3D            Image dimension"
            echo "  --nose-rigid yes|no    Nose rigid-only mode"
            echo "  --nose-mask FILE       Nose rigid mask"
            echo "  --image4d FILE         4D image file"
            echo "  --static-image FILE    Static/reference image"
            echo "  --segmask FILE         Segmentation mask"
            echo "  --manual-stl FILE      Pre-existing manual STL (skip auto-generation)"
            echo "  --frames-dir DIR       Folder containing 3D frame images (for 3D mode)"
            echo "  --subject NAME         Subject/project name"
            echo "  --ds INT               Alignment downsampling (1-10)"
            echo "  --levels INT           Alignment levels (2 or 4)"
            echo "  --align-be FLOAT       Alignment bending energy"
            echo "  --initial ID|FILE      Initial alignment (Id, guess, or dof.gz)"
            echo "  --motion-be FLOAT      Motion registration bending energy"
            echo "  --interp-step FLOAT    Interpolation step (ms)"
            echo "  --downsample INT       Star table row downsampling factor"
            echo "  --input-txt FILE       Path to input.txt (default: ./input.txt)"
            echo "  --config FILE          Path to custom register.cfg"
            echo "  --config-ct            Use CT registration config (isotropic, all axes active)"
            echo "  --output-dir DIR       Output directory (overrides auto naming)"
            echo "  --reg-only             Registration only (no segmask needed, stops after FFDs)"
            echo "  --reuse-reg DIR        Reuse existing registration from DIR, propagate STL only"
            echo "  --skip-video           Skip post-processing video generation"
            exit 0
            ;;
        *) error "Unknown option: $1. Use --help for usage." ;;
    esac
done

# =============================================================================
# Dual-mode parameter getter (B1 fix: printf -v instead of eval)
# =============================================================================
get_param() {
    local var_name="$1"
    local prompt="$2"
    local cli_value="$3"
    if [ -n "$cli_value" ]; then
        printf -v "$var_name" '%s' "$cli_value"
    else
        read -e -p "$prompt" "$var_name"
    fi
}

# =============================================================================
# Helper: resolve path to absolute
# =============================================================================
resolve_path() {
    local path="$1"
    if [ -z "$path" ]; then
        echo ""
        return
    fi
    # If already absolute, use as-is; otherwise prepend WORK_DIR
    if [[ "$path" == /* ]]; then
        echo "$path"
    else
        echo "$WORK_DIR/$path"
    fi
}

# =============================================================================
# Shared functions
# =============================================================================

parse_input_txt() {
    local input_file="$1"
    if [ ! -f "$input_file" ]; then
        error "input.txt not found at: $input_file"
    fi
    info "Reading timing parameters from $input_file"
    beginPoint=$(sed -n 2p "$input_file" | sed 's/.*,//')
    timePoints=$(sed -n 3p "$input_file" | sed 's/.*,//')
    breTime=$(sed -n 4p "$input_file" | sed 's/.*,//')
    dt=$(($breTime/$(($timePoints-1))))
    timeEnd=$(($dt*$(($timePoints-1))))
    numInfix=$(seq -s " " 0 $(($timePoints-1)))
    info "beginPoint=$beginPoint timePoints=$timePoints breTime=$breTime dt=$dt"
}

extract_4d_frames() {
    local image4d="$1"
    info "Extracting $timePoints frames from 4D image starting at frame $beginPoint"
    mirtk extract-image-volume "$image4d" -t "$beginPoint" -n "$timePoints" extracted_static.nii.gz
    local i=0
    # B2 fix: tighten glob to .nii.gz only
    for x in extracted_static*.nii.gz; do
        mv "$x" "staticFrom4D_t${beginPoint}_n${timePoints}_${i}.nii.gz"
        i=$((i+1))
    done
}

copy_3d_frames() {
    local frames_dir="$1"
    if [ ! -d "$frames_dir" ]; then
        error "Frames directory not found: $frames_dir"
    fi
    local i=0
    local count=0
    # ls -1v for natural/version sort order (frame2 before frame10)
    # pipe to while read for safe whitespace handling
    while IFS= read -r x; do
        cp "$x" "staticImage_t${beginPoint}_n${timePoints}_${i}.nii.gz"
        i=$((i+1))
        count=$((count+1))
    done < <(ls -1v "$frames_dir"/*.nii* 2>/dev/null)
    if [ "$count" -eq 0 ]; then
        error "No .nii/.nii.gz files found in $frames_dir"
    fi
    info "Copied $count 3D frames from $frames_dir"
}

create_symlinks() {
    local prefix="$1"  # "staticFrom4D" or "staticImage"
    if [ ! -f "img_0.nii.gz" ]; then
        for i in $(seq 0 $(($timePoints-1))); do
            ln -s "${prefix}_t${beginPoint}_n${timePoints}_${i}.nii.gz" "img_${i}.nii.gz"
        done
        info "Symlinks created"
    else
        warn "Symlinks already exist, skipping"
    fi
}

extract_stl_from_mask() {
    local segmask="$1"
    local output_stl="$2"
    info "Extracting STL surface from segmentation mask"
    mirtk extract-surface "$segmask" "$output_stl" -blur 0.8 -isovalue 0.4
}

perform_alignment() {
    local static_image="$1"
    local first_image="$2"
    local man_seg_stl="$3"
    local aligned_stl="$4"
    local aligned_mask="$5"
    local alignment_dof="$6"
    local initial="$7"
    local ds="$8"
    local levels="$9"
    local align_be="${10}"

    # Register static image to first time point
    if [ ! -f "$alignment_dof" ]; then
        info "Registering static image to time-zero frame"
        mirtk register "$static_image" "$first_image" -model Rigid+Affine+FFD \
            -dofin "$initial" -dofout "$alignment_dof" \
            -ds "$ds" -levels "$levels" -be "$align_be" -sim NMI
    else
        warn "Alignment DOF already exists, skipping"
    fi

    # Transform manual segmentation STL to time-zero
    if [ ! -f "$aligned_stl" ]; then
        info "Transforming STL to time-zero using alignment"
        mirtk transform-points "$man_seg_stl" "$aligned_stl" -dofin "$alignment_dof"
    else
        warn "Aligned STL already exists, skipping"
    fi

    # Generate binary mask from aligned STL
    if [ ! -f "$aligned_mask" ]; then
        info "Generating binary mask from aligned STL"
        mirtk extract-pointset-surface -input "$aligned_stl" -mask "$aligned_mask" -reference "$first_image"
    else
        warn "Aligned mask already exists, skipping"
    fi
}

skip_alignment() {
    local man_seg_stl="$1"
    local segmask="$2"
    local aligned_stl="$3"
    local aligned_mask="$4"
    info "No alignment requested. Copying manual segmentation as time-zero reference."
    cp "$man_seg_stl" "$aligned_stl"
    cp "$segmask" "$aligned_mask"
}

run_registration() {
    local nose_rigid="$1"
    local nose_mask="$2"
    local config_file="$3"

    info "Starting temporal registration"
    if [[ "$nose_rigid" == y* || "$nose_rigid" == Y* ]]; then
        python "$PIPELINE_DIR/register.py" \
            --prefix "img_" \
            --infix $numInfix \
            --suffix ".nii.gz" \
            --parin "$config_file" \
            --dofout "ffd_{i}.dof.gz" \
            --mask "$nose_mask"
    else
        python "$PIPELINE_DIR/register.py" \
            --prefix "img_" \
            --infix $numInfix \
            --suffix ".nii.gz" \
            --parin "$config_file" \
            --dofout "ffd_{i}.dof.gz"
    fi
}

apply_transforms() {
    local aligned_mask="$1"

    info "Applying transforms to generate STLs..."
    for i in $(seq 1 $(($timePoints-1))); do
        mirtk transform-points "seg_0.stl" "seg_${i}.stl" -dofin "ffd_${i}.dof.gz"
    done
    info "All STL transforms complete"

    info "Generating binary masks..."
    for i in $(seq 1 $(($timePoints-1))); do
        mirtk extract-pointset-surface -input "seg_${i}.stl" -mask "seg_${i}.nii.gz" -reference "$aligned_mask"
    done
    info "All masks generated"
}

generate_ffds_csv() {
    if [ ! -f "ffds.csv" ]; then
        info "Generating ffds.csv for interpolation"
        echo "dof,t
identity,0" > ffds.csv
        for i in $(seq 1 $(($timePoints-1))); do
            local t=$(($i*$dt))
            echo "ffd_${i}.dof.gz,${t}" >> ffds.csv
        done
        echo "identity,$(($timeEnd+$dt))" >> ffds.csv
    else
        warn "ffds.csv already exists, skipping"
    fi
}

run_interpolation() {
    local first_image="$1"
    local aligned_stl="$2"
    local table_name="$3"
    local interp_step="$4"
    local align_or_not="$5"
    local be_str="$6"
    local downsample="$7"

    info "Running cubic spline interpolation"
    local downsample_arg=""
    if [ -n "$downsample" ] && [ "$downsample" -gt 1 ] 2>/dev/null; then
        downsample_arg="--downsample $downsample"
    fi

    python "$PIPELINE_DIR/interpolate.py" \
        --target "$first_image" \
        --dofs ffds.csv \
        --mesh "$aligned_stl" \
        --start 0 \
        --stop "$timeEnd" \
        --step "$interp_step" \
        --output-mesh "./out_{t:08.3f}_${align_or_not}_${be_str}.stl" \
        --output-table "./${table_name}" \
        $downsample_arg
}

# =============================================================================
# Main pipeline execution
# =============================================================================

info "MIRTK Registration Pipeline"
info "Using mirtk: $(which mirtk)"
info "Using python: $(which python)"
info "Working directory: $WORK_DIR"
echo ""

# --- Validate mutually exclusive flags ---
if [ "$opt_reg_only" = true ] && [ -n "$opt_reuse_reg" ]; then
    error "--reg-only and --reuse-reg cannot be used together"
fi

if [ "$opt_reg_only" = true ]; then
    info "MODE: Registration only (will stop after FFDs, no segmask needed)"
elif [ -n "$opt_reuse_reg" ]; then
    info "MODE: Reuse existing registration (propagation only)"
else
    info "MODE: Full pipeline"
fi
echo ""

# =============================================================================
# --reuse-reg: Skip to propagation using existing results
# =============================================================================
if [ -n "$opt_reuse_reg" ]; then
    reuse_dir="$(resolve_path "$opt_reuse_reg")"
    [ -d "$reuse_dir" ] || error "Reuse directory not found: $reuse_dir"

    # Verify FFDs exist
    ls "$reuse_dir"/ffd_*.dof.gz &>/dev/null || error "No ffd_*.dof.gz found in $reuse_dir"
    [ -f "$reuse_dir/ffds.csv" ] || error "ffds.csv not found in $reuse_dir"
    [ -f "$reuse_dir/img_0.nii.gz" ] || error "img_0.nii.gz not found in $reuse_dir"

    # Read timing from input.txt (check reuse dir first, then WORK_DIR)
    if [ -f "$reuse_dir/input.txt" ]; then
        opt_input_txt="$reuse_dir/input.txt"
    fi
    opt_input_txt="$(resolve_path "$opt_input_txt")"
    parse_input_txt "$opt_input_txt"

    # Collect propagation parameters
    get_param "SegMask" "What is the manual segmentation mask name?: " "$opt_segmask"
    get_param "agn" "Do you need align the highRes to timeFrame 0? [y,n]: " "$opt_align"

    if [[ "$agn" == y* || "$agn" == Y* ]]; then
        get_param "StaticImage" "What is the StaticImage name?: " "$opt_static_image"
        get_param "DS" "Please say the alignment ds in range 1 to 10: " "$opt_ds"
        get_param "L" "Please say the alignment levels choose 2 or 4: " "$opt_levels"
        get_param "aBE" "Please say the alignment bending energy (default 0.001): " "$opt_align_be"
        get_param "initial" "Please say the initial alignment (Id, guess, or dof.gz): " "$opt_initial"
        alignOrnot="aligned"
    else
        alignOrnot="noalign"
    fi

    get_param "inteStep" "Please tell the interpolation step (ms): " "$opt_interp_step"
    downsample="${opt_downsample:-1}"

    # Resolve paths
    SegMask="$(resolve_path "$SegMask")"
    [ -f "$SegMask" ] || error "Segmentation mask not found: $SegMask"

    if [[ "$agn" == y* || "$agn" == Y* ]]; then
        StaticImage="$(resolve_path "$StaticImage")"
        [ -f "$StaticImage" ] || error "Static image not found: $StaticImage"
    fi

    if [ -n "$opt_manual_stl" ]; then
        opt_manual_stl="$(resolve_path "$opt_manual_stl")"
        [ -f "$opt_manual_stl" ] || error "Manual STL not found: $opt_manual_stl"
    fi

    # cd into existing results dir
    cd "$reuse_dir"
    RESULTS_DIR="$(pwd)"
    info "Reusing registration from: $RESULTS_DIR"

    # Start logging
    exec > >(tee -a "$RESULTS_DIR/pipeline.log") 2>&1
    info "Logging to: $RESULTS_DIR/pipeline.log"

    # Set variables
    alignedSTL="seg_0.stl"
    alignedMask="seg_0.nii.gz"
    man_segSTL="manual_seg.stl"
    firstImageLink="img_0.nii.gz"
    be="reused"
    BE_str="reused"
    tableName="${opt_output_dir:-propagation}_${alignOrnot}.csv"

    # Jump directly to STL extraction + propagation (Stages 2, 4, 5, 8)
    # --- Stage 2: STL extraction / manual STL + alignment ---
    if [ -n "$opt_manual_stl" ]; then
        info "Using provided manual STL: $opt_manual_stl"
        cp "$opt_manual_stl" "$man_segSTL"
    else
        # Interactive mode: let the user choose
        if [ -f "$WORK_DIR/manual_seg.stl" ]; then
            info "Found existing manual_seg.stl in subject folder"
        fi
        echo ""
        echo "How do you want to get the STL for propagation?"
        echo "  1) Auto-generate from segmentation mask"
        echo "  2) Provide path to an existing STL file"
        if [ -f "$WORK_DIR/manual_seg.stl" ]; then
            echo "  3) Use detected manual_seg.stl from subject folder"
        fi
        read -e -p "Choose [1/2/3]: " stl_choice
        case "$stl_choice" in
            2)
                # cd to WORK_DIR so tab-completion finds STL files in subject folder
                pushd "$WORK_DIR" > /dev/null
                read -e -p "Path to STL file: " custom_stl_path
                popd > /dev/null
                custom_stl_path="$(cd "$WORK_DIR" && resolve_path "$custom_stl_path")"
                [ -f "$custom_stl_path" ] || error "STL file not found: $custom_stl_path"
                info "Using: $custom_stl_path"
                cp "$custom_stl_path" "$man_segSTL"
                ;;
            3)
                if [ -f "$WORK_DIR/manual_seg.stl" ]; then
                    info "Using existing manual_seg.stl"
                    cp "$WORK_DIR/manual_seg.stl" "$man_segSTL"
                else
                    error "No manual_seg.stl found in subject folder"
                fi
                ;;
            *)
                extract_stl_from_mask "$SegMask" "$man_segSTL"
                ;;
        esac
    fi

    if [[ "$agn" == y* || "$agn" == Y* ]]; then
        perform_alignment "$StaticImage" "$firstImageLink" "$man_segSTL" \
            "$alignedSTL" "$alignedMask" "alignment.dof.gz" \
            "$initial" "$DS" "$L" "$aBE"
    else
        skip_alignment "$man_segSTL" "$SegMask" "$alignedSTL" "$alignedMask"
    fi

    # --- Stage 4: Apply transforms ---
    apply_transforms "$alignedMask"

    # --- Stage 8: Interpolation ---
    run_interpolation "$firstImageLink" "$alignedSTL" \
        "$tableName" "$inteStep" "$alignOrnot" "$BE_str" "$downsample"

    echo ""
    info "Propagation complete!"
    info "Results folder: $RESULTS_DIR"
    info "Star table:     $RESULTS_DIR/$tableName"
    info "Pipeline log:   $RESULTS_DIR/pipeline.log"
    exit 0
fi

# =============================================================================
# Normal flow: Collect parameters (interactive or CLI)
# =============================================================================

get_param "agn" "Do you need align the highRes to timeFrame 0? [y,n]: " "$opt_align"
get_param "dim" "Do you use 4D image as input or multiple 3D images? [4D,3D]: " "$opt_dim"

# P2: validate dim
if [[ "$dim" != "4D" && "$dim" != "3D" ]]; then
    error "Dimension must be '4D' or '3D', got: '$dim'"
fi

get_param "nro" "Do you want to make the nose rigid motion only? [y,n]: " "$opt_nose_rigid"

NoseRigidOnly=""
if [[ "$nro" == y* || "$nro" == Y* ]]; then
    get_param "NoseRigidOnly" "What is the image mask for Nose Rigid only?: " "$opt_nose_mask"
fi

# Dimension-specific inputs
if [ "$dim" == "4D" ]; then
    get_param "Image4D" "What is the 4D image name?: " "$opt_image4d"
elif [ "$dim" == "3D" ]; then
    get_param "frames_dir" "Path to folder containing 3D frame images: " "$opt_frames_dir"
fi

if [[ "$agn" == y* || "$agn" == Y* ]]; then
    get_param "StaticImage" "What is the StaticImage name?: " "$opt_static_image"
fi

# Skip segmask in --reg-only mode (not needed for registration)
if [ "$opt_reg_only" != true ]; then
    get_param "SegMask" "What is the manual segmentation mask name?: " "$opt_segmask"
fi

# Read timing parameters
opt_input_txt="$(resolve_path "$opt_input_txt")"
parse_input_txt "$opt_input_txt"

get_param "subject" "What is the project and subject name: " "$opt_subject"

# B6 fix: default DS to 1 always
DS="1"
L=""
aBE=""
initial=""

if [[ "$agn" == y* || "$agn" == Y* ]]; then
    get_param "DS" "Please say the alignment ds in range 1 to 10: " "$opt_ds"
    get_param "L" "Please say the alignment levels choose 2 or 4: " "$opt_levels"
    get_param "aBE" "Please say the alignment bending energy (default 0.001): " "$opt_align_be"
    get_param "initial" "Please say the initial alignment (Id, guess, or dof.gz): " "$opt_initial"
fi

get_param "be" "What is the bending energy for Motion Registration (default 0.001): " "$opt_motion_be"

# Only ask interpolation params if not reg-only (they're not used during registration)
if [ "$opt_reg_only" != true ]; then
    get_param "inteStep" "Please tell the interpolation step (ms): " "$opt_interp_step"
fi

# Downsample parameter (CLI only, no interactive prompt needed)
downsample="${opt_downsample:-1}"

# Interactive config template selection (only if --config/--config-ct not given)
if [ "$opt_config" = "$DEFAULT_CONFIG" ] && [ "$cli_mode" = false ]; then
    echo ""
    echo "Select registration config template:"
    echo "  1) MRI  (cine MRI, few Z-slices, X-axis frozen)"
    echo "  2) CT   (isotropic CT, all axes active, memory-efficient)"
    echo "  3) Custom config file"
    read -e -p "Choose [1/2/3]: " config_choice
    case "$config_choice" in
        2)  opt_config="$PIPELINE_DIR/config/register_ct.cfg" ;;
        3)  read -e -p "Path to config file: " opt_config ;;
        *)  opt_config="$DEFAULT_CONFIG" ;;
    esac
fi

# =============================================================================
# Resolve all input paths to absolute (P3)
# =============================================================================

if [ "$dim" == "4D" ]; then
    Image4D="$(resolve_path "$Image4D")"
    [ -f "$Image4D" ] || error "4D image not found: $Image4D"
elif [ "$dim" == "3D" ]; then
    frames_dir="$(resolve_path "$frames_dir")"
    [ -d "$frames_dir" ] || error "Frames directory not found: $frames_dir"
fi

if [[ "$agn" == y* || "$agn" == Y* ]]; then
    StaticImage="$(resolve_path "$StaticImage")"
    [ -f "$StaticImage" ] || error "Static image not found: $StaticImage"
fi

if [ "$opt_reg_only" != true ]; then
    SegMask="$(resolve_path "$SegMask")"
    [ -f "$SegMask" ] || error "Segmentation mask not found: $SegMask"
fi

if [ -n "$NoseRigidOnly" ]; then
    NoseRigidOnly="$(resolve_path "$NoseRigidOnly")"
    [ -f "$NoseRigidOnly" ] || error "Nose rigid mask not found: $NoseRigidOnly"
fi

if [ -n "$opt_manual_stl" ]; then
    opt_manual_stl="$(resolve_path "$opt_manual_stl")"
    [ -f "$opt_manual_stl" ] || error "Manual STL not found: $opt_manual_stl"
fi

opt_config="$(resolve_path "$opt_config")"
[ -f "$opt_config" ] || error "Config file not found: $opt_config"

# =============================================================================
# F2: Subject-first output folder naming
# =============================================================================

if [[ "$agn" == y* || "$agn" == Y* ]]; then
    auto_output_dir="${subject}_aligned_ds${DS}_l${L}_aBE${aBE}_be${be}"
    alignOrnot="aligned"
else
    auto_output_dir="${subject}_noalign_ds${DS}_be${be}"
    alignOrnot="noalign"
fi

output_dir="${opt_output_dir:-$auto_output_dir}"
tableName="${output_dir}.csv"

BE_str="ds${DS}_l${L}_aBE${aBE}_be${be}"

alignedSTL="seg_0.stl"
alignedMask="seg_0.nii.gz"
man_segSTL="manual_seg.stl"
firstImageLink="img_0.nii.gz"

# =============================================================================
# F1: Create output dir FIRST, put config inside, cd into it
# =============================================================================

if [ -d "$WORK_DIR/$output_dir" ]; then
    # B7: ask before deleting in interactive mode
    if [ "$cli_mode" = true ]; then
        warn "Output dir '$output_dir' exists. Overwriting (CLI mode)."
        rm -rf "$WORK_DIR/$output_dir"
    else
        warn "Output dir '$output_dir' already exists."
        read -e -p "Overwrite? [y,n]: " overwrite
        if [[ "$overwrite" == y* || "$overwrite" == Y* ]]; then
            rm -rf "$WORK_DIR/$output_dir"
        else
            error "Aborted. Choose a different --output-dir or remove the existing folder."
        fi
    fi
fi

mkdir "$WORK_DIR/$output_dir"

# F4: Create working config INSIDE results folder (kept permanently for reproducibility)
# B5 fix: use | as sed delimiter
sed "s|+ \(.*\) BE|+ $be BE|" "$opt_config" > "$WORK_DIR/$output_dir/register_work.cfg"
info "register_work.cfg saved in results folder (bending energy = $be)"

# cd into results folder — everything runs here from now on
cd "$WORK_DIR/$output_dir"
RESULTS_DIR="$(pwd)"
info "All processing will run inside: $RESULTS_DIR"

# F5: Start logging (duplicate all output to pipeline.log)
exec > >(tee -a "$RESULTS_DIR/pipeline.log") 2>&1
info "Logging to: $RESULTS_DIR/pipeline.log"

# =============================================================================
# Stage 1: Image extraction and setup
# =============================================================================

if [ "$dim" == "4D" ]; then
    extract_4d_frames "$Image4D"
    create_symlinks "staticFrom4D"
elif [ "$dim" == "3D" ]; then
    copy_3d_frames "$frames_dir"
    create_symlinks "staticImage"
fi

# =============================================================================
# --reg-only: generate ffds.csv and stop here
# =============================================================================
if [ "$opt_reg_only" = true ]; then
    # Stage 3: Registration
    run_registration "$nro" "$NoseRigidOnly" "./register_work.cfg"

    # Stage 7: Generate ffds.csv
    generate_ffds_csv

    # Copy input.txt into results folder for later --reuse-reg
    cp "$opt_input_txt" "$RESULTS_DIR/input.txt" 2>/dev/null || true

    echo ""
    info "Registration-only mode complete!"
    info "FFD transforms saved in: $RESULTS_DIR"
    info "To propagate STL motion later, run:"
    info "  mirtk-pipeline --reuse-reg $RESULTS_DIR --segmask <mask.nii.gz> --manual-stl <stl> --interp-step <step_ms>"
    info "Pipeline log:   $RESULTS_DIR/pipeline.log"
    exit 0
fi

# =============================================================================
# Stage 2: STL extraction / manual STL + alignment
# =============================================================================

# F3: --manual-stl support with interactive selection
if [ -n "$opt_manual_stl" ]; then
    # CLI mode: explicit --manual-stl provided
    info "Using provided manual STL: $opt_manual_stl"
    cp "$opt_manual_stl" "$man_segSTL"
else
    # Interactive mode: let the user choose
    if [ -f "$WORK_DIR/manual_seg.stl" ]; then
        info "Found existing manual_seg.stl in subject folder"
    fi
    echo ""
    echo "How do you want to get the STL for propagation?"
    echo "  1) Auto-generate from segmentation mask"
    echo "  2) Provide path to an existing STL file"
    if [ -f "$WORK_DIR/manual_seg.stl" ]; then
        echo "  3) Use detected manual_seg.stl from subject folder"
    fi
    read -e -p "Choose [1/2/3]: " stl_choice
    case "$stl_choice" in
        2)
            # cd to WORK_DIR so tab-completion finds STL files in subject folder
            pushd "$WORK_DIR" > /dev/null
            read -e -p "Path to STL file: " custom_stl_path
            popd > /dev/null
            custom_stl_path="$(cd "$WORK_DIR" && resolve_path "$custom_stl_path")"
            [ -f "$custom_stl_path" ] || error "STL file not found: $custom_stl_path"
            info "Using: $custom_stl_path"
            cp "$custom_stl_path" "$man_segSTL"
            ;;
        3)
            if [ -f "$WORK_DIR/manual_seg.stl" ]; then
                info "Using existing manual_seg.stl"
                cp "$WORK_DIR/manual_seg.stl" "$man_segSTL"
            else
                error "No manual_seg.stl found in subject folder"
            fi
            ;;
        *)
            extract_stl_from_mask "$SegMask" "$man_segSTL"
            ;;
    esac
fi

if [[ "$agn" == y* || "$agn" == Y* ]]; then
    perform_alignment "$StaticImage" "$firstImageLink" "$man_segSTL" \
        "$alignedSTL" "$alignedMask" "alignment.dof.gz" \
        "$initial" "$DS" "$L" "$aBE"
else
    skip_alignment "$man_segSTL" "$SegMask" "$alignedSTL" "$alignedMask"
fi

# =============================================================================
# Stage 3: Temporal registration
# =============================================================================

run_registration "$nro" "$NoseRigidOnly" "./register_work.cfg"

# =============================================================================
# Stage 4: Apply transforms to all time points
# =============================================================================

apply_transforms "$alignedMask"

# =============================================================================
# Stage 5: Generate ffds.csv and run interpolation
# =============================================================================

generate_ffds_csv

run_interpolation "$firstImageLink" "$alignedSTL" \
    "$tableName" "$inteStep" "$alignOrnot" "$BE_str" "$downsample"

# =============================================================================
# Stage 6: Optional post-processing (video generation)
# =============================================================================

if [ "$opt_skip_video" = false ]; then
    POST_PROCESS="$SCRIPT_DIR/post_process.sh"
    if [ -f "$POST_PROCESS" ]; then
        if command -v ffmpeg &> /dev/null; then
            info "Running post-processing video generation"
            bash "$POST_PROCESS" "." "." "$BE_str"
        else
            warn "ffmpeg not found. Skipping video generation."
        fi
    else
        warn "post_process.sh not found. Skipping video generation."
    fi
else
    info "Video generation skipped (--skip-video)"
fi

# =============================================================================
# Done — no cleanup needed, everything is already in the right place
# =============================================================================

echo ""
info "Pipeline complete!"
info "Results folder: $RESULTS_DIR"
info "Star table:     $RESULTS_DIR/$tableName"
info "Config used:    $RESULTS_DIR/register_work.cfg"
info "Pipeline log:   $RESULTS_DIR/pipeline.log"
