#!/bin/bash
# =============================================================================
# Install mirtk_pipeline commands into the active conda environment
# After running this, these commands are available anywhere when env is active:
#   mirtk-pipeline       - main registration pipeline
#   mirtk-decimate       - mesh decimation
#   mirtk-scale-stl      - STL scaling
#   mirtk-interpolate    - mesh interpolation
#   mirtk-preprocess     - image smoothing
#   mirtk-visualize      - STL sequence rendering
#   mirtk-register-seq   - temporal sequence registration
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Check conda env is active
if [ -z "${CONDA_PREFIX:-}" ]; then
    error "No conda env active. Run: conda activate mirtk"
fi

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE_DIR="$CONDA_PREFIX/share/mirtk_pipeline"
BIN_DIR="$CONDA_PREFIX/bin"

info "Copying pipeline into conda env: $PIPELINE_DIR"
rm -rf "$PIPELINE_DIR"
cp -r "$SOURCE_DIR" "$PIPELINE_DIR"

info "Installing commands into: $BIN_DIR"

# --- Main pipeline command (bash wrapper) ---
cat > "$BIN_DIR/mirtk-pipeline" << WRAPPER
#!/bin/bash
exec bash "$PIPELINE_DIR/scripts/run_pipeline.sh" "\$@"
WRAPPER
chmod +x "$BIN_DIR/mirtk-pipeline"

# --- Python tool commands ---
for cmd_pair in \
    "mirtk-decimate:decimate.py" \
    "mirtk-scale-stl:scale_stl.py" \
    "mirtk-interpolate:interpolate.py" \
    "mirtk-preprocess:preprocess.py" \
    "mirtk-visualize:visualize.py" \
    "mirtk-register-seq:register.py" \
    "mirtk-nifti-slices:nifti_to_slices.py"; do

    cmd_name="${cmd_pair%%:*}"
    py_file="${cmd_pair##*:}"

    cat > "$BIN_DIR/$cmd_name" << WRAPPER
#!/bin/bash
exec python "$PIPELINE_DIR/$py_file" "\$@"
WRAPPER
    chmod +x "$BIN_DIR/$cmd_name"
done

# --- Slicer prep command ---
cat > "$BIN_DIR/mirtk-prepare-slicer" << WRAPPER
#!/bin/bash
exec bash "$PIPELINE_DIR/scripts/prepare_slicer.sh" "\$@"
WRAPPER
chmod +x "$BIN_DIR/mirtk-prepare-slicer"

echo ""
info "Commands installed. Available when 'mirtk' env is active:"
echo ""
echo "  mirtk-pipeline          Full registration pipeline"
echo "  mirtk-interpolate       Mesh interpolation + star table"
echo "  mirtk-register-seq      Temporal sequence registration"
echo "  mirtk-decimate          STL mesh decimation"
echo "  mirtk-scale-stl         STL coordinate scaling"
echo "  mirtk-preprocess        Image smoothing"
echo "  mirtk-visualize         STL sequence rendering"
echo "  mirtk-nifti-slices      NIfTI to PNG slices (x/y/z)"
echo "  mirtk-prepare-slicer    Package output for 3D Slicer"
echo ""
echo "  Example: cd /path/to/subject && mirtk-pipeline"
echo "  Help:    mirtk-pipeline --help"
