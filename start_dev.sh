#!/bin/bash
# Development server startup script

set -e

echo "🚀 Starting AI Workforce Simulation API..."
echo ""

# Check if .env exists
if [ ! -f ".env.example" ]; then
    echo "⚠️  No .env file found. Creating from template..."
    cp .env.example .env
    echo "✅ Created .env file. Please configure as needed."
    echo ""
fi

# Load environment variables from .env
if [ -f ".env.example" ]; then
    echo "📦 Loading environment from .env..."
    export $(grep -v '^#' .env | xargs)
fi

# Show current configuration
echo "🔧 Configuration:"
echo "   APP_ENV: ${APP_ENV:-dev}"
echo "   ACTIVE_GAME_MODULE: ${ACTIVE_GAME_MODULE:-business_sim}"
echo "   USE_MOCK_PROVIDER: ${USE_MOCK_PROVIDER:-true}"
echo "   DATABASE_URL: ${DATABASE_URL:-sqlite:///data/sim_engine.db}"
echo ""

# Create necessary directories
echo "📁 Creating data directories..."
mkdir -p data
mkdir -p data/tests
mkdir -p logs
echo ""

# Install dependencies if needed
if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
    echo "⚠️  No virtual environment found. Creating one..."
    python3 -m venv venv
    echo "✅ Virtual environment created. Please activate it:"
    echo "   source venv/bin/activate"
    echo ""
fi

# Check if dependencies are installed
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt 2>/dev/null || pip install fastapi uvicorn pydantic
    echo ""
fi

# Start the server
echo "🌐 Starting FastAPI server..."
echo "   URL: http://localhost:8000"
echo "   Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"
echo ""

uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
