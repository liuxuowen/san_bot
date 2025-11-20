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
# pkill -f "${PROJECT_ROOT}/app.py" 2>/dev/null || true


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

# Restart service via systemd
echo ""
echo "Restarting San Bot service..."
# 尝试重启服务，如果失败（例如服务未安装）则提示
if sudo systemctl restart sanbot; then
    echo "Service restarted successfully."
    echo "Current Status:"
    sudo systemctl status sanbot --no-pager | head -n 10
else
    echo "ERROR: Failed to restart 'sanbot' service."
    echo "Please ensure the service is installed and configured."
    echo "See sanbot.service for a template."
fi

