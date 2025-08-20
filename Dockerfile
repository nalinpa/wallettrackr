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
RUN mkdir -p config templates static

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8001
ENV UVLOOP_ENABLED=1

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run FastAPI with uvicorn (with uvloop in production)
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--loop", "uvloop"]