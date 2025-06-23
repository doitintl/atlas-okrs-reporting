#!/bin/bash

# Script to create a virtual environment with uv and install dependencies from requirements.txt
# Usage: source setup_venv_uv.sh

set -e

# Create venv with uv
uv venv .venv

# Activate venv
source .venv/bin/activate

# Upgrade pip (optional, uv handles it well)
# uv pip install --upgrade pip

# Install all dependencies from requirements.txt
uv sync

echo "Virtual environment created and dependencies installed from requirements.txt."
echo "To activate later: source .venv/bin/activate" 