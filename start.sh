#!/bin/bash
# Start the development server

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "🚀 Starting AI Workforce Simulation..."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠ Virtual environment not found${NC}"
    echo "   Running setup script..."
    ./setup.sh
fi

# Activate virtual environment
source venv/bin/activate

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠ .env file not found${NC}"
    echo "   Creating from template..."
    cp .env.example .env
fi

# Load environment variables
export $(grep -v '^#' .env | xargs) 2>/dev/null || true

# Show configuration
echo -e "${GREEN}Configuration:${NC}"
echo "   APP_ENV: ${APP_ENV:-dev}"
echo "   ACTIVE_GAME_MODULE: ${ACTIVE_GAME_MODULE:-business_sim}"
echo "   USE_MOCK_PROVIDER: ${USE_MOCK_PROVIDER:-true}"
echo "   DATABASE_URL: ${DATABASE_URL:-sqlite:///data/sim_engine.db}"
echo ""

# Create directories
mkdir -p data logs

# Start server
echo -e "${GREEN}Starting FastAPI server...${NC}"
echo "   URL: http://localhost:8000"
echo "   Docs: http://localhost:8000/docs"
echo "   Health: http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop"
echo ""

uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
