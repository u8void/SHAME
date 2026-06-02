#!/usr/bin/env bash
# =============================================================================
# setup.sh — Iris AI One-Shot Setup
# Initialises git submodules, builds llama.cpp, and installs Python deps.
# Usage:  bash setup.sh [--no-pip] [--no-build] [--jobs N]
# =============================================================================

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }
section() { echo -e "\n${BOLD}${CYAN}══ $* ══${RESET}"; }

# ── Parse flags ───────────────────────────────────────────────────────────────
SKIP_PIP=false
SKIP_BUILD=false
JOBS=$(nproc 2>/dev/null || sysctl -n hw.logicalcpu 2>/dev/null || echo 4)

for arg in "$@"; do
  case "$arg" in
    --no-pip)   SKIP_PIP=true ;;
    --no-build) SKIP_BUILD=true ;;
    --jobs)     shift; JOBS="$1" ;;
    --jobs=*)   JOBS="${arg#*=}" ;;
    -h|--help)
      echo "Usage: bash setup.sh [--no-pip] [--no-build] [--jobs N]"
      echo ""
      echo "  --no-pip    Skip Python dependency installation"
      echo "  --no-build  Skip llama.cpp compilation"
      echo "  --jobs N    Parallel make jobs (default: auto-detect)"
      exit 0 ;;
  esac
done

# ── Header ────────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║         Iris AI — Setup Script           ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${RESET}"

# ── 1. Git submodules ─────────────────────────────────────────────────────────
section "Step 1/3 — Git Submodules"

if [ ! -d ".git" ]; then
  error "Run this script from the root of the Iris AI repository."
fi

if [ -f ".gitmodules" ]; then
  info "Initialising and updating submodules..."
  git submodule update --init --recursive --progress
  ok "Submodules up to date."
else
  warn ".gitmodules not found — skipping submodule step."
fi

# ── 2. Build llama.cpp ────────────────────────────────────────────────────────
section "Step 2/3 — Build llama.cpp"

LLAMA_DIR="$(pwd)/llama.cpp"

if [ "$SKIP_BUILD" = true ]; then
  warn "--no-build passed. Skipping llama.cpp compilation."
elif [ ! -d "$LLAMA_DIR" ]; then
  warn "llama.cpp/ directory not found. Skipping build."
else
  info "Building llama.cpp with cmake (${JOBS} parallel jobs)..."
  cd "$LLAMA_DIR"

  # Use cmake for a portable, optimised build
  BUILD_DIR="build"
  cmake -B "$BUILD_DIR" \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_NATIVE=ON \
    $([ "$(uname)" = "Darwin" ] && echo "-DGGML_METAL=ON" || true) \
    $(command -v nvcc &>/dev/null && echo "-DGGML_CUDA=ON" || true) \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_EXAMPLES=ON \
    -DLLAMA_BUILD_SERVER=ON \
    2>&1 | tail -5

  cmake --build "$BUILD_DIR" --config Release -j "$JOBS"

  cd - > /dev/null

  # Verify key binaries exist
  QUANTIZE_BIN=$(find "$LLAMA_DIR/build" -name "llama-quantize" -type f 2>/dev/null | head -1)
  if [ -n "$QUANTIZE_BIN" ]; then
    ok "llama.cpp built successfully."
    info "  llama-quantize → ${QUANTIZE_BIN}"
  else
    warn "Build completed but llama-quantize binary not found. GGUF quantization may fall back to F16."
  fi
fi

# ── 3. Python dependencies ────────────────────────────────────────────────────
section "Step 3/3 — Python Dependencies"

if [ "$SKIP_PIP" = true ]; then
  warn "--no-pip passed. Skipping Python installation."
else
  if ! command -v python3 &>/dev/null; then
    error "python3 not found. Please install Python 3.10+."
  fi

  PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  info "Python ${PYTHON_VER} detected."

  info "Installing requirements..."
  python3 -m pip install --upgrade pip -q
  python3 -m pip install -r requirements.txt

  # Platform-specific extras
  if [[ "$(uname)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
    info "Apple Silicon detected — installing mlx-lm..."
    python3 -m pip install mlx-lm
  fi

  ok "Python dependencies installed."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}  ✓ Setup complete!${RESET}"
echo ""
echo -e "  Next steps:"
echo -e "   ${CYAN}1.${RESET} Add your GGUF model files to ${BOLD}./src/models/${RESET}"
echo -e "   ${CYAN}2.${RESET} (Optional) Add training data to ${BOLD}./training/${RESET} subdirectories"
echo -e "   ${CYAN}3.${RESET} Run the app:  ${BOLD}python app.py${RESET}"
echo -e "   ${CYAN}4.${RESET} Train a role: ${BOLD}python train.py --train-role general${RESET}"
echo ""
