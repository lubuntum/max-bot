#!/bin/bash
# start.sh - Quick start script

set -e

echo "🚀 Starting MAX Schedule Bot..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "Please create .env file with your MAX_TOKEN and Yandex Disk URLs"
    exit 1
fi

# Build and start
echo "📦 Building Docker image..."
docker-compose build

echo "🔄 Starting bot..."
docker-compose up -d

echo "✅ Bot started successfully!"
echo ""
echo "📊 Useful commands:"
echo "  - View logs:  docker-compose logs -f bot"
echo "  - Stop bot:   docker-compose down"
echo "  - Restart:    docker-compose restart"
echo "  - Shell:      docker-compose exec bot /bin/bash"

# Show initial logs
sleep 2
echo ""
echo "📋 Initial logs:"
docker-compose logs --tail=10 bot