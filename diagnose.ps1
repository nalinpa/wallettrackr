# debug-dockerfile.ps1 - Complete debugging for the config module issue

Write-Host "=== Docker Config Module Debugging ===" -ForegroundColor Red
Write-Host ""

# Check if we're in the right directory
Write-Host "Step 1: Checking current directory and project structure..." -ForegroundColor Blue
$currentDir = Get-Location
Write-Host "Current directory: $currentDir" -ForegroundColor Gray

# List all files and directories
Write-Host ""
Write-Host "Current directory contents:" -ForegroundColor Yellow
Get-ChildItem | ForEach-Object {
    if ($_.PSIsContainer) {
        Write-Host "📁 $($_.Name)/" -ForegroundColor Cyan
        # If it's the config directory, show its contents
        if ($_.Name -eq "config") {
            Get-ChildItem $_.FullName | ForEach-Object {
                Write-Host "   📄 $($_.Name)" -ForegroundColor Gray
            }
        }
    } else {
        Write-Host "📄 $($_.Name)" -ForegroundColor White
    }
}

# Check for critical files
Write-Host ""
Write-Host "Step 2: Checking critical files..." -ForegroundColor Blue

$criticalFiles = @("main.py", "Dockerfile", "requirements.txt", "config/__init__.py", "config/settings.py")
$missingCritical = @()

foreach ($file in $criticalFiles) {
    if (Test-Path $file) {
        Write-Host "✅ $file exists" -ForegroundColor Green
    } else {
        Write-Host "❌ $file MISSING" -ForegroundColor Red
        $missingCritical += $file
    }
}

if ($missingCritical.Count -gt 0) {
    Write-Host ""
    Write-Host "❌ CRITICAL FILES MISSING!" -ForegroundColor Red
    Write-Host "Missing files: $($missingCritical -join ', ')" -ForegroundColor White
    Write-Host "Cannot proceed with deployment until these are fixed." -ForegroundColor Yellow
    exit 1
}

# Test Python import locally
Write-Host ""
Write-Host "Step 3: Testing Python import locally..." -ForegroundColor Blue
try {
    $pythonTest = python -c "import sys; sys.path.append('.'); from config.settings import settings; print('SUCCESS: Config imported locally')" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Local Python import works" -ForegroundColor Green
    } else {
        Write-Host "❌ Local Python import FAILS:" -ForegroundColor Red
        Write-Host $pythonTest -ForegroundColor Yellow
        Write-Host ""
        Write-Host "This means the issue is with your local setup, not Docker!" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Python test failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Check current Dockerfile
Write-Host ""
Write-Host "Step 4: Analyzing current Dockerfile..." -ForegroundColor Blue

if (Test-Path "Dockerfile") {
    $dockerfileContent = Get-Content "Dockerfile" -Raw
    
    # Check for the key fixes
    if ($dockerfileContent -match "COPY \. \.") {
        Write-Host "✅ Dockerfile copies all files (COPY . .)" -ForegroundColor Green
    } else {
        Write-Host "❌ Dockerfile doesn't copy all files properly" -ForegroundColor Red
    }
    
    if ($dockerfileContent -match "ENV PYTHONPATH") {
        Write-Host "✅ Dockerfile sets PYTHONPATH" -ForegroundColor Green
    } else {
        Write-Host "❌ Dockerfile missing PYTHONPATH" -ForegroundColor Red
    }
    
    Write-Host ""
    Write-Host "Current Dockerfile CMD line:" -ForegroundColor Yellow
    $cmdLine = $dockerfileContent | Select-String "CMD.*uvicorn"
    if ($cmdLine) {
        Write-Host $cmdLine.Line -ForegroundColor White
    }
} else {
    Write-Host "❌ No Dockerfile found!" -ForegroundColor Red
}

# Create a completely new, debug-enabled Dockerfile
Write-Host ""
Write-Host "Step 5: Creating FIXED Dockerfile with debugging..." -ForegroundColor Blue

$fixedDockerfile = @"
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
    curl \
    wget \
    tree \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# CRITICAL FIX: Copy ALL files and directories
COPY . .

# Create necessary directories
RUN mkdir -p templates static logs cache alerts

# DEBUGGING: Show what files are actually in the container
RUN echo "=== CONTAINER DEBUG INFO ===" && \
    echo "Current directory:" && pwd && \
    echo "Contents of /app:" && ls -la && \
    echo "Contents of /app/config:" && ls -la config/ && \
    echo "Python path check:" && python -c "import sys; print('\\n'.join(sys.path))" && \
    echo "Config import test:" && python -c "from config.settings import settings; print('SUCCESS: Config imported!')" || echo "FAILED: Config import failed"

# Set environment variables - CRITICAL
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/config:/app/api:/app/services:/app/core
ENV PORT=8080

# Create non-root user
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

# Switch to non-root user
USER app

# Expose port
EXPOSE `$PORT

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:`$PORT/health || exit 1

# FIXED CMD: Ensure Python can find all modules
CMD ["sh", "-c", "echo 'Starting FastAPI...' && python -c 'from config.settings import settings; print(\"Config loaded successfully\")' && python -m uvicorn main:app --host 0.0.0.0 --port `$PORT --workers 1"]
"@

# Backup existing Dockerfile
if (Test-Path "Dockerfile") {
    $timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    Copy-Item "Dockerfile" "Dockerfile.backup_$timestamp" -Force
    Write-Host "✅ Backed up existing Dockerfile to Dockerfile.backup_$timestamp" -ForegroundColor Green
}

# Write the fixed Dockerfile
$fixedDockerfile | Out-File -FilePath "Dockerfile" -Encoding UTF8
Write-Host "✅ Created FIXED Dockerfile with debugging" -ForegroundColor Green

Write-Host ""
Write-Host "Step 6: Testing Docker build locally..." -ForegroundColor Blue
Write-Host "This will show us exactly what's happening in the container..." -ForegroundColor Gray

# Test build locally
try {
    Write-Host "Running: docker build -t crypto-debug-test ." -ForegroundColor Yellow
    $buildResult = docker build -t crypto-debug-test . 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Docker build succeeded!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Build output contains debug info - check above for 'CONTAINER DEBUG INFO'" -ForegroundColor Cyan
        
        # Test running the container locally
        Write-Host ""
        Write-Host "Testing container run..." -ForegroundColor Blue
        $runTest = docker run --rm -p 8080:8080 crypto-debug-test
        
    } else {
        Write-Host "❌ Docker build failed!" -ForegroundColor Red
        Write-Host $buildResult -ForegroundColor Yellow
    }
    
} catch {
    Write-Host "❌ Docker build error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Make sure Docker is running!" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Step 7: Next actions..." -ForegroundColor Blue

if ($missingCritical.Count -eq 0) {
    Write-Host "✅ All critical files present" -ForegroundColor Green
    Write-Host "✅ Fixed Dockerfile created with debugging" -ForegroundColor Green
    Write-Host ""
    Write-Host "NOW RUN YOUR DEPLOYMENT:" -ForegroundColor Cyan
    Write-Host ".\secure-deploy.ps1" -ForegroundColor White
    Write-Host ""
    Write-Host "The new Dockerfile includes debugging output that will show:" -ForegroundColor Yellow
    Write-Host "- What files are actually in the container" -ForegroundColor White
    Write-Host "- Whether the config directory exists" -ForegroundColor White
    Write-Host "- Whether Python can import the config module" -ForegroundColor White
    Write-Host ""
    Write-Host "Check the Cloud Run logs for the debug output:" -ForegroundColor Yellow
    Write-Host "gcloud run services logs read crypto-alpha-analysis --region asia-southeast1" -ForegroundColor White
} else {
    Write-Host "❌ Fix missing files first!" -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to continue"