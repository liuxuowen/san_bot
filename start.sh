#!/bin/bash

# San Bot Startup Script

echo "=================================="
echo "San Bot - 微信服务号 / 企业微信 文件分析助手"
echo "=================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Stop existing instances
echo "Stopping existing San Bot processes (if any)..."
PROJECT_ROOT=$(cd "$(dirname "$0")" && pwd)
pkill -f "${PROJECT_ROOT}/app.py" 2>/dev/null || true

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "WARNING: .env file not found!"
    echo "Please copy .env.example to .env and configure it."
    read -p "Would you like to create .env from .env.example now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cp .env.example .env
        echo ".env file created. Please edit it with your Service Account / WeCom credentials."
        exit 0
    else
        echo "Continuing without .env file (using defaults)..."
    fi
fi

# Start the application in background with log redirection
echo ""
echo "Starting San Bot in background..."
echo "Server will be available at http://0.0.0.0:7000 (override via .env)"
echo "Logs: /opt/projects/logs/sanbot.log"
echo ""

LOG_DIR=/opt/projects/logs
mkdir -p "$LOG_DIR"

nohup python app.py >> "$LOG_DIR/sanbot.log" 2>&1 &
echo "San Bot started with PID $!"
