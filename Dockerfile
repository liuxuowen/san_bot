FROM python:3.9-slim

LABEL maintainer="San Bot Team"
LABEL description="WeChat Work File Analysis Bot"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py config.py wechat_api.py file_analyzer.py ./

# Create uploads directory
RUN mkdir -p /app/uploads

# Expose port
EXPOSE 5000

# Set environment variables
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/', timeout=5)"

# Run the application
CMD ["python", "app.py"]
