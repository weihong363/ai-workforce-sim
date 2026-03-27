#!/bin/bash
# Setup script for AI Workforce Simulation
# This script creates an isolated Python environment and installs all dependencies

set -e

echo "🚀 Setting up AI Workforce Simulation..."
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo "📦 Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}✓ Found: ${PYTHON_VERSION}${NC}"
else
    echo -e "${RED}✗ Python 3 not found. Please install Python 3.8+${NC}"
    exit 1
fi
echo ""

# Create virtual environment
echo "📦 Creating virtual environment..."
if [ -d "venv" ]; then
    echo -e "${YELLOW}⚠ Virtual environment already exists${NC}"
    echo "   To recreate, run: rm -rf venv && $0"
else
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi
echo ""

# Activate virtual environment
echo "📦 Activating virtual environment..."
source venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"
echo ""

# Upgrade pip
echo "📦 Upgrading pip..."
pip install --upgrade pip
echo -e "${GREEN}✓ pip upgraded${NC}"
echo ""

# Install dependencies
echo "📦 Installing dependencies from requirements.txt..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${RED}✗ requirements.txt not found${NC}"
    exit 1
fi
echo ""

# Copy environment file
echo "📦 Setting up environment configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}✓ Created .env file${NC}"
else
    echo -e "${YELLOW}⚠ .env file already exists${NC}"
fi
echo ""

# Create necessary directories
echo "📦 Creating data directories..."
mkdir -p data
mkdir -p data/tests
mkdir -p logs
echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Verify installation
echo "📦 Verifying installation..."
python -c "import pydantic; import fastapi; import uvicorn" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ All core dependencies imported successfully${NC}"
else
    echo -e "${RED}✗ Failed to import dependencies${NC}"
    exit 1
fi
echo ""

# Show summary
echo "=============================================="
echo -e "${GREEN}✅ Setup completed successfully!${NC}"
echo "=============================================="
echo ""
echo "Next steps:"
echo "1. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "2. Start the development server:"
echo "   uvicorn api.app:app --reload"
echo ""
echo "3. Or use the convenience script:"
echo "   ./start.sh"
echo ""
echo "4. Access the API documentation:"
echo "   http://localhost:8000/docs"
echo ""
