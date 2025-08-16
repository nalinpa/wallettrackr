# Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libuv1-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

COPY static/ ./static/

# Create necessary directories
RUN mkdir -p logs config templates

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV UVLOOP_ENABLED=1

# Expose port
EXPOSE 8080

# Run the application with gunicorn for production
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 --worker-class gevent app:app