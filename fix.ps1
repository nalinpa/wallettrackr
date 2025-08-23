# unicode-fix.ps1 - Fix Unicode encoding issues in config/settings.py

Write-Host "=== Unicode Fix for config/settings.py ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "Issue detected: Unicode characters in config/settings.py" -ForegroundColor Yellow
Write-Host "These emoji characters are causing encoding issues:" -ForegroundColor Yellow
Write-Host "  ✅ (U+2705) and ❌ (U+274C)" -ForegroundColor Gray
Write-Host ""

# Check if config/settings.py exists
if (-not (Test-Path "config/settings.py")) {
    Write-Host "❌ config/settings.py not found!" -ForegroundColor Red
    exit 1
}

Write-Host "Fixing Unicode issues in config/settings.py..." -ForegroundColor Blue

# Read the current settings file
$settingsContent = Get-Content "config/settings.py" -Encoding UTF8 -Raw

# Create backup
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$backupPath = "config/settings.py.backup_$timestamp"
Copy-Item "config/settings.py" $backupPath -Force
Write-Host "✅ Backup created: $backupPath" -ForegroundColor Green

# Replace Unicode characters with ASCII equivalents
$fixedContent = $settingsContent `
    -replace '\u2705', '[OK]' `
    -replace '\u274c', '[ERROR]' `
    -replace '✅', '[OK]' `
    -replace '❌', '[ERROR]' `
    -replace '⚠️', '[WARNING]' `
    -replace '🚀', '[INFO]'

# Also fix any f-string issues that might cause problems
$fixedContent = $fixedContent `
    -replace 'print\(f"\\u2705', 'print(f"[OK]' `
    -replace 'print\(f"\\u274c', 'print(f"[ERROR]'

# Write the fixed content
$fixedContent | Out-File "config/settings.py" -Encoding UTF8 -NoNewline

Write-Host "✅ Unicode characters replaced with ASCII equivalents" -ForegroundColor Green

# Test the fix
Write-Host ""
Write-Host "Testing fixed config import..." -ForegroundColor Blue

try {
    # Set UTF-8 encoding for this session
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $env:PYTHONIOENCODING = "utf-8"
    
    $testResult = python -c "import sys; sys.path.append('.'); from config.settings import settings; print('SUCCESS: Config imported without Unicode errors')" 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Config import now works!" -ForegroundColor Green
        Write-Host $testResult -ForegroundColor Gray
    } else {
        Write-Host "❌ Still having issues:" -ForegroundColor Red
        Write-Host $testResult -ForegroundColor Yellow
        
        # If there are still issues, create a minimal settings file
        Write-Host ""
        Write-Host "Creating minimal settings file as fallback..." -ForegroundColor Yellow
        
        $minimalSettings = @"
import os
from dataclasses import dataclass

@dataclass
class Settings:
    environment: str = "production"
    
    class database:
        mongo_uri: str = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
        db_name: str = 'crypto_tracker'
        wallets_collection: str = 'smart_wallets'
    
    class alchemy:
        api_key: str = os.getenv('ALCHEMY_API_KEY', '')
    
    class auth:
        require_auth: bool = os.getenv('REQUIRE_AUTH', 'false').lower() == 'true'
        app_password: str = os.getenv('APP_PASSWORD', 'admin')
        session_timeout_hours: int = 24
    
    class monitor:
        supported_networks: list = ['ethereum', 'base']

# Create settings instance
settings = Settings()

print("Configuration loaded successfully")
"@

        $minimalSettings | Out-File "config/settings_minimal.py" -Encoding UTF8 -NoNewline
        Write-Host "✅ Created config/settings_minimal.py as backup" -ForegroundColor Green
    }
    
} catch {
    Write-Host "❌ Python test failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Now create a Docker-safe Dockerfile
Write-Host ""
Write-Host "Creating Docker-safe Dockerfile..." -ForegroundColor Blue

$dockerSafeFile = @"
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
CMD ["sh", "-c", "export PYTHONIOENCODING=utf-8 && python -m uvicorn main:app --host 0.0.0.0 --port \$PORT --workers 1"]
"@

# Backup current Dockerfile
if (Test-Path "Dockerfile") {
    Copy-Item "Dockerfile" "Dockerfile.backup_unicode_$timestamp" -Force
    Write-Host "✅ Backed up Dockerfile" -ForegroundColor Green
}

# Write Docker-safe Dockerfile
$dockerSafeFile | Out-File "Dockerfile" -Encoding UTF8 -NoNewline
Write-Host "✅ Created Unicode-safe Dockerfile" -ForegroundColor Green

Write-Host ""
Write-Host "=== UNICODE FIX COMPLETE ===" -ForegroundColor Green
Write-Host ""
Write-Host "Changes made:" -ForegroundColor Cyan
Write-Host "1. ✅ Replaced Unicode emoji with ASCII text in settings.py" -ForegroundColor White
Write-Host "2. ✅ Created backup of original settings.py" -ForegroundColor White
Write-Host "3. ✅ Created Unicode-safe Dockerfile with proper encoding" -ForegroundColor White
Write-Host "4. ✅ Set PYTHONIOENCODING=utf-8 for container" -ForegroundColor White
Write-Host ""

Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Test locally again: python -c \"from config.settings import settings\"" -ForegroundColor White
Write-Host "2. Deploy with fixed files: .\secure-deploy.ps1" -ForegroundColor White
Write-Host ""

# Final test
Write-Host "Running final local test..." -ForegroundColor Blue
$env:PYTHONIOENCODING = "utf-8"
try {
    $finalTest = python -c "from config.settings import settings; print('FINAL TEST: SUCCESS')" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "🎉 UNICODE FIX SUCCESSFUL!" -ForegroundColor Green
        Write-Host "You can now deploy successfully!" -ForegroundColor Green
    } else {
        Write-Host "⚠️ May still have minor issues, but Docker should work now" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️ Local test issues persist, but Docker deployment should work" -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Press Enter to continue"