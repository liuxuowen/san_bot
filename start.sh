#!/bin/bash

# San Bot Startup Script

echo "=================================="
echo "San Bot - WeChat Work File Analysis Bot"
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
        echo ".env file created. Please edit it with your WeChat Work credentials."
        exit 0
    else
        echo "Continuing without .env file (using defaults)..."
    fi
fi

# Start the application
echo ""
echo "Starting San Bot..."
echo "Server will be available at http://0.0.0.0:5000"
echo "Press Ctrl+C to stop"
echo ""

python app.py
