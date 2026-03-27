#!/bin/bash
# Start Redis and API Server

set -e

echo "🚀 Starting AI Workforce Simulation Server"
echo ""

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "⚠️  Activating virtual environment..."
    source venv/bin/activate
fi

# Check if Redis container is running
REDIS_CONTAINER=$(docker ps --filter "name=redis-workforce" --format "{{.Names}}")

if [[ "$REDIS_CONTAINER" != "redis-workforce" ]]; then
    echo "📦 Starting Redis container..."
    
    # Remove old container if exists
    docker rm -f redis-workforce > /dev/null 2>&1 || true
    
    # Start new Redis container with authentication
    docker run -d \
        --name redis-workforce \
        -p 6379:6379 \
        redis:latest \
        redis-server --requirepass difyai123456
    
    echo "✅ Redis container started"
    sleep 2
else
    echo "✅ Redis container already running"
fi

# Test Redis connection
echo ""
echo "🔌 Testing Redis connection..."
python3 -c "from core_engine.cache import init_cache; init_cache('redis://:difyai123456@localhost:6379/0')" 2>/dev/null

if [ $? -eq 0 ]; then
    echo "✅ Redis connection successful"
else
    echo "❌ Redis connection failed"
    exit 1
fi

# Start API server
echo ""
echo "🌐 Starting API server on http://localhost:8001"
echo "Press Ctrl+C to stop"
echo ""

uvicorn api.app:app --host 0.0.0.0 --port 8001
