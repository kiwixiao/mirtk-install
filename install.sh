#!/bin/bash
set -euo pipefail

ENV_NAME="mirtk"
MIN_CONDA_VERSION="23.0"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHANNEL_DIR="${SCRIPT_DIR}/packages"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# --- Check conda ---
if ! command -v conda &> /dev/null; then
    error "conda not found. Install Miniconda first:
    https://docs.conda.io/en/latest/miniconda.html"
fi

CONDA_VER=$(conda --version 2>&1 | awk '{print $2}')
info "Found conda ${CONDA_VER}"

# --- Check platform ---
PLATFORM=$(conda info --json 2>/dev/null | python -c "import sys,json; print(json.load(sys.stdin)['platform'])" 2>/dev/null || echo "unknown")
info "Platform: ${PLATFORM}"

if [ ! -d "${CHANNEL_DIR}/${PLATFORM}" ]; then
    error "No pre-built package for platform '${PLATFORM}'.
Available platforms: $(ls "${CHANNEL_DIR}" 2>/dev/null | tr '\n' ' ')
To build from source on this platform, see HOW_TO_BUILD.md"
fi

# --- Index the local channel ---
info "Indexing local channel..."
conda index "${CHANNEL_DIR}" 2>/dev/null || {
    warn "conda-index not found, installing..."
    conda install conda-build -y -q > /dev/null 2>&1
    conda index "${CHANNEL_DIR}"
}

# --- Create env if needed ---
if conda env list | grep -q "^${ENV_NAME} "; then
    warn "Conda env '${ENV_NAME}' already exists. Updating..."
    conda install -n "${ENV_NAME}" -c "file://${CHANNEL_DIR}" mirtk -y
else
    info "Creating conda env '${ENV_NAME}'..."
    conda create -n "${ENV_NAME}" -c "file://${CHANNEL_DIR}" mirtk -y
fi

# --- Verify mirtk binary ---
info "Verifying MIRTK installation..."
if ! conda run -n "${ENV_NAME}" mirtk help > /dev/null 2>&1; then
    error "Installation failed. 'mirtk help' did not run successfully."
fi
info "MIRTK binary installed successfully."

# --- Install Python dependencies for pipeline ---
info "Installing Python dependencies..."
conda run -n "${ENV_NAME}" pip install pyvista trimesh matplotlib SimpleITK pandas scipy numpy || {
    warn "Some pip packages may have failed. Check manually with: conda activate ${ENV_NAME} && pip list"
}
info "Python dependencies installed."

# --- Install pipeline commands ---
PIPELINE_SETUP="${SCRIPT_DIR}/mirtk_pipeline/setup_commands.sh"
if [ -f "$PIPELINE_SETUP" ]; then
    info "Installing pipeline commands..."
    conda run -n "${ENV_NAME}" bash "$PIPELINE_SETUP"
else
    warn "mirtk_pipeline/setup_commands.sh not found. Pipeline commands not installed."
fi

echo ""
info "Installation complete!"
echo ""
echo "  To use:"
echo "    conda activate ${ENV_NAME}"
echo "    mirtk help"
echo "    mirtk-pipeline --help"
echo ""
