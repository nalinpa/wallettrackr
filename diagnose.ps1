# diagnose-and-fix.ps1 - Diagnose and fix the deployment issue

$SERVICE_NAME = "crypto-alpha-analysis"
$REGION = "asia-southeast1"
$PROJECT_ID = "crypto-track-468604"

Write-Host "=== Crypto Alpha Diagnostic Tool ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check service status
Write-Host "🔍 Checking service status..." -ForegroundColor Blue

try {
    $serviceInfo = gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format=json | ConvertFrom-Json
    
    Write-Host "✅ Service exists" -ForegroundColor Green
    Write-Host "Service Name: $($serviceInfo.metadata.name)" -ForegroundColor Gray
    Write-Host "Region: $($serviceInfo.metadata.labels.'cloud.googleapis.com/location')" -ForegroundColor Gray
    
    # Check URL
    $serviceUrl = $serviceInfo.status.url
    if ($serviceUrl) {
        Write-Host "✅ Service URL: $serviceUrl" -ForegroundColor Green
    } else {
        Write-Host "❌ No service URL found - deployment likely failed" -ForegroundColor Red
    }
    
    # Check conditions
    Write-Host ""
    Write-Host "🔍 Service Conditions:" -ForegroundColor Blue
    foreach ($condition in $serviceInfo.status.conditions) {
        $status = if ($condition.status -eq "True") { "✅" } else { "❌" }
        $color = if ($condition.status -eq "True") { "Green" } else { "Red" }
        
        Write-Host "$status $($condition.type): $($condition.status)" -ForegroundColor $color
        
        if ($condition.message -and $condition.status -ne "True") {
            Write-Host "   Message: $($condition.message)" -ForegroundColor Yellow
        }
        
        if ($condition.reason -and $condition.status -ne "True") {
            Write-Host "   Reason: $($condition.reason)" -ForegroundColor Yellow
        }
    }
    
    # Check latest revision
    Write-Host ""
    Write-Host "🔍 Latest Revision:" -ForegroundColor Blue
    $latestRevision = $serviceInfo.status.latestReadyRevisionName
    if ($latestRevision) {
        Write-Host "✅ Ready Revision: $latestRevision" -ForegroundColor Green
    } else {
        Write-Host "❌ No ready revision found" -ForegroundColor Red
        $latestCreated = $serviceInfo.status.latestCreatedRevisionName
        if ($latestCreated) {
            Write-Host "⚠️ Latest Created: $latestCreated (not ready)" -ForegroundColor Yellow
        }
    }
    
} catch {
    Write-Host "❌ Error getting service info: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Step 2: Check recent logs
Write-Host ""
Write-Host "🔍 Checking recent logs (last 10 entries)..." -ForegroundColor Blue
Write-Host ""

try {
    gcloud run services logs read $SERVICE_NAME --platform managed --region $REGION --limit 10
} catch {
    Write-Host "❌ Could not retrieve logs" -ForegroundColor Red
}

# Step 3: Check for common issues
Write-Host ""
Write-Host "🔍 Common Issue Checks:" -ForegroundColor Blue

# Check if container image exists
try {
    $imageName = "gcr.io/$PROJECT_ID/$SERVICE_NAME"
    Write-Host "Checking container image: $imageName" -ForegroundColor Gray
    
    $imageInfo = gcloud container images describe $imageName --format=json 2>$null
    if ($imageInfo) {
        Write-Host "✅ Container image exists" -ForegroundColor Green
    } else {
        Write-Host "❌ Container image not found" -ForegroundColor Red
        Write-Host "   Need to build image first" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️ Could not check container image" -ForegroundColor Yellow
}

# Step 4: Suggested fixes
Write-Host ""
Write-Host "🛠️ Suggested Fixes:" -ForegroundColor Yellow
Write-Host ""

if (-not $serviceUrl) {
    Write-Host "Issue: No service URL (deployment failed)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Fix Options:" -ForegroundColor Blue
    Write-Host "1. Re-deploy with fixed configuration:" -ForegroundColor White
    Write-Host "   .\secure-deploy.ps1" -ForegroundColor Gray
    Write-Host ""
    Write-Host "2. Delete and redeploy:" -ForegroundColor White
    Write-Host "   gcloud run services delete $SERVICE_NAME --region $REGION" -ForegroundColor Gray
    Write-Host "   .\secure-deploy.ps1" -ForegroundColor Gray
    Write-Host ""
    Write-Host "3. Check detailed logs:" -ForegroundColor White
    Write-Host "   gcloud run services logs read $SERVICE_NAME --region $REGION --limit 50" -ForegroundColor Gray
    Write-Host ""
    
    # Offer to auto-fix
    $autoFix = Read-Host "Auto-fix by re-deploying? (y/N)"
    
    if ($autoFix -eq 'y' -or $autoFix -eq 'Y') {
        Write-Host ""
        Write-Host "🚀 Starting auto-fix deployment..." -ForegroundColor Green
        
        if (Test-Path ".\secure-deploy.ps1") {
            try {
                & ".\secure-deploy.ps1"
                Write-Host ""
                Write-Host "✅ Auto-fix deployment completed!" -ForegroundColor Green
            } catch {
                Write-Host "❌ Auto-fix failed: $($_.Exception.Message)" -ForegroundColor Red
                Write-Host "Try manual deployment" -ForegroundColor Yellow
            }
        } else {
            Write-Host "❌ secure-deploy.ps1 not found" -ForegroundColor Red
            Write-Host "Please ensure the deployment script exists" -ForegroundColor Yellow
        }
    }
    
} else {
    Write-Host "Service URL exists but may be slow to respond" -ForegroundColor Blue
    Write-Host ""
    Write-Host "Try these:" -ForegroundColor Yellow
    Write-Host "1. Wait 30-60 seconds for cold start" -ForegroundColor White
    Write-Host "2. Visit: $serviceUrl" -ForegroundColor White
    Write-Host "3. Check health: $serviceUrl/health" -ForegroundColor White
    Write-Host "4. Scale to min-instances=1:" -ForegroundColor White
    Write-Host "   gcloud run services update $SERVICE_NAME --region $REGION --min-instances 1" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Done! 🎉" -ForegroundColor Green