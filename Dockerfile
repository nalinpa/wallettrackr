FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including uvloop requirements
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

# Create necessary directories
RUN mkdir -p templates static

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8001
ENV UVLOOP_ENABLED=1

# Expose port
ENV PORT=8080
# CRITICAL FIX: Use PORT environment variable from Cloud Run
ENV PORT=8080

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

# Switch to non-root user
USER app

# Expose the port (Cloud Run will set PORT environment variable)
EXPOSE $PORT

# Health check for Cloud Run - FIXED to use dynamic port
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:$PORT/health || exit 1

# Run FastAPI with dynamic port from environment
CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port $PORT --loop uvloop --workers 1"]