#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------
# run.sh - Audiogram generator for Shorts/Reels/TikTok
# ------------------------------------------------------------------
# Prerequisites:
#   ffmpeg  (required for video generation)
#     Ubuntu:  sudo apt install ffmpeg
#     macOS:   brew install ffmpeg
#
# This script automatically detects your GPU and installs the
# correct PyTorch version for Whisper.
# ------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# ---- venv ----
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtualenv at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
. "$VENV_DIR/bin/activate"
PY="$VENV_DIR/bin/python"

# Make sure pip is available in the venv
if ! "$PY" -m pip --version &>/dev/null; then
    echo "  Installing pip in virtualenv ..."
    "$PY" -m ensurepip --upgrade &>/dev/null || true
fi

# ---- GPU Detection & Torch Install ----
setup_deps() {
    echo "Checking dependencies ..."
    # Use $PY -m pip so we work even when venv was created without the pip package
    "$PY" -m pip install -q --upgrade pip

    # Check if torch is already installed
    if "$PY" -c "import torch" &>/dev/null; then
        echo "  PyTorch already installed."
    else
        echo "Detecting GPU environment..."
        TORCH_URL=""
        
        if command -v nvidia-smi &> /dev/null; then
            echo "  NVIDIA GPU detected -> Installing CUDA PyTorch"
            TORCH_URL="https://download.pytorch.org/whl/cu121"
        elif command -v rocm-smi &> /dev/null || command -v rocminfo &> /dev/null; then
            echo "  AMD GPU detected -> Installing ROCm PyTorch"
            TORCH_URL="https://download.pytorch.org/whl/rocm6.0"
        elif [[ "$OSTYPE" == "darwin"* ]]; then
            echo "  macOS detected -> Installing standard PyTorch (MPS)"
            TORCH_URL=""
        else
            echo "  No GPU detected -> Installing CPU PyTorch"
            TORCH_URL=""
        fi

        echo "Installing PyTorch ..."
        if [ -n "$TORCH_URL" ]; then
            "$PY" -m pip install -q torch --index-url "$TORCH_URL"
        else
            "$PY" -m pip install -q torch
        fi
    fi

    if ! "$PY" -c "import whisper" &>/dev/null; then
        echo "Installing openai-whisper ..."
        "$PY" -m pip install -q openai-whisper
    fi
}

# ---- usage ----
usage() {
    cat <<EOF
Usage: ./run.sh <command> [options]

Commands:
  transcribe <audio> [model]       Generate SRT/VTT captions → <audio_stem>-out/
  audiogram <audio> <srt>          Create vertical video with captions → <audio_stem>-out/
  setup                            Force reinstall dependencies
  help                             Show this help message

Examples:
  ./run.sh transcribe podcast.wav
  ./run.sh audiogram podcast.wav podcast-out/podcast.srt

Options:
  model:  tiny | base | small | medium | large-v3  (default: large-v3)
EOF
    exit 0
}

# ---- dispatch ----
CMD="${1:-}"
case "$CMD" in
    help|--help|-h)
        usage
        ;;
    setup)
        setup_deps
        echo "Setup complete."
        ;;
    transcribe)
        AUDIO="${2:-}"
        if [ -z "$AUDIO" ]; then
            echo "Error: audio file required"
            usage
        fi
        MODEL="${3:-large-v3}"
        setup_deps
        echo "Transcribing: $AUDIO (model=$MODEL)"
        "$PY" "$SCRIPT_DIR/transcribe.py" "$AUDIO" -f srt vtt -m "$MODEL"
        ;;
    audiogram)
        AUDIO="${2:-}"
        SRT="${3:-}"
        if [ -z "$AUDIO" ] || [ -z "$SRT" ]; then
            echo "Error: audio and SRT file required"
            usage
        fi
        shift 3
        if ! command -v ffmpeg &> /dev/null; then
            echo "Error: ffmpeg is required. Install with: sudo apt install ffmpeg"
            exit 1
        fi
        echo "Generating audiogram: $AUDIO + $SRT"
        "$PY" "$SCRIPT_DIR/audiogram.py" "$AUDIO" "$SRT" "$@"
        ;;
    *)
        echo "Unknown command: $CMD"
        usage
        ;;
esac
