FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc g++ make libuv1-dev python3-dev curl wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Set UTF-8 encoding for Python
ENV PYTHONIOENCODING=utf-8
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ALL application files
COPY . .

# Set Python path
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"
ENV PORT=8080

# Create user
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

EXPOSE 8080

# Start with encoding support
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]