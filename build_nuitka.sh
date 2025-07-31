#!/bin/bash

# Build script for DroneCAN Batch Updater using Nuitka

set -e  # Exit on any error

echo "🚀 Building DroneCAN Batch Updater with Nuitka..."

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Error: Virtual environment not found. Please create it first."
    exit 1
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source venv/bin/activate

# Check if Nuitka is installed
if ! python -c "import nuitka" 2>/dev/null; then
    echo "📥 Installing Nuitka..."
    pip install nuitka
fi

# Create output directory
mkdir -p dist/nuitka

# Build with Nuitka
echo "🔨 Building executable..."
python -m nuitka \
    --standalone \
    --output-filename=dronecan-batch-updater \
    --output-dir=dist/nuitka \
    --enable-plugin=multiprocessing \
    --include-data-dir=firmware=firmware \
    --include-data-dir=venv/lib/python3.10/site-packages/dronecan/dsdl_specs=dronecan/dsdl_specs \
    src/main.py

echo ""
echo "✅ Build completed successfully!"
echo "📦 Standalone application created at: dist/nuitka/main.dist/"
echo ""
echo "🧪 To test, run: ./dist/nuitka/main.dist/dronecan-batch-updater --help"