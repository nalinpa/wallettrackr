# shutdown-service.ps1 - Complete service deletion to stop all charges

$SERVICE_NAME = "crypto-alpha-analysis"
$REGION = "asia-southeast1"
$PROJECT_ID = "crypto-track-468604" 

Write-Host "=== Crypto Alpha Service Shutdown ===" -ForegroundColor Red
Write-Host ""
Write-Host "This will COMPLETELY DELETE your FastAPI service to stop all charges." -ForegroundColor Yellow
Write-Host "To use the app again, you'll need to run your deploy script." -ForegroundColor Yellow
Write-Host ""

# Check if service exists
try {
    $serviceExists = gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format="value(metadata.name)" 2>$null
    if (-not $serviceExists) {
        Write-Host "Service '$SERVICE_NAME' not found or already deleted." -ForegroundColor Blue
        Write-Host "No charges are occurring." -ForegroundColor Green
        Read-Host "Press Enter to exit"
        exit 0
    }
} catch {
    Write-Host "Service '$SERVICE_NAME' not found or already deleted." -ForegroundColor Blue
    Write-Host "No charges are occurring." -ForegroundColor Green
    Read-Host "Press Enter to exit"
    exit 0
}

# Get current service URL and info before deletion
try {
    $SERVICE_URL = gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format='value(status.url)' 2>$null
    if ($SERVICE_URL) {
        Write-Host "Current service URL: $SERVICE_URL" -ForegroundColor Cyan
        
        # Try to get service status
        try {
            $response = Invoke-RestMethod -Uri "$SERVICE_URL/health" -TimeoutSec 10
            Write-Host "Service status: $($response.status)" -ForegroundColor Gray
            Write-Host "Version: $($response.version)" -ForegroundColor Gray
        } catch {
            Write-Host "Service not responding (may be cold)" -ForegroundColor Gray
        }
    }
} catch {
    # Service might not be responding
    Write-Host "Service exists but not accessible" -ForegroundColor Gray
}

Write-Host ""
Write-Host "After deletion:" -ForegroundColor Green
Write-Host "   Cloud Run charges: $0.00/month" -ForegroundColor Green
Write-Host "   MongoDB Atlas: ~$57/month (still active)" -ForegroundColor Yellow
Write-Host "   Container images: ~$0.10/month (minimal storage)" -ForegroundColor Yellow
Write-Host ""
Write-Host "💡 Alternative to deletion:" -ForegroundColor Blue
Write-Host "   Scale to zero: Keeps service but stops charges when idle" -ForegroundColor White
Write-Host "   Command: gcloud run services update $SERVICE_NAME --region $REGION --min-instances=0" -ForegroundColor Gray
Write-Host ""

# Confirmation prompt
$confirm = Read-Host "Type 'DELETE' to confirm deletion, 'SCALE' to scale to zero, or anything else to cancel"

if ($confirm -eq "DELETE") {
    Write-Host ""
    Write-Host "Deleting FastAPI service..." -ForegroundColor Red
    
    try {
        gcloud run services delete $SERVICE_NAME --platform managed --region $REGION --quiet
        
        Write-Host "Service '$SERVICE_NAME' deleted successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Result:" -ForegroundColor Cyan
        Write-Host "   - No more Cloud Run charges" -ForegroundColor Green
        Write-Host "   - Container images still stored (minimal cost)" -ForegroundColor Yellow
        Write-Host "   - MongoDB Atlas still active" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "To restart:" -ForegroundColor Blue
        Write-Host "   Run your deploy script: .\secure-deploy.ps1" -ForegroundColor White
        Write-Host "   Or use startup script: .\startup-service.ps1" -ForegroundColor White
        Write-Host ""
        
    } catch {
        Write-Host "Error deleting service: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "You can also delete it manually in the Cloud Console:" -ForegroundColor Yellow
        Write-Host "   https://console.cloud.google.com/run?project=$PROJECT_ID" -ForegroundColor White
    }
    
} elseif ($confirm -eq "SCALE") {
    Write-Host ""
    Write-Host "Scaling service to zero instances..." -ForegroundColor Blue
    
    try {
        gcloud run services update $SERVICE_NAME --platform managed --region $REGION --min-instances=0 --quiet
        
        Write-Host "Service scaled to zero successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Result:" -ForegroundColor Cyan
        Write-Host "   - No charges when idle (99% cost reduction)" -ForegroundColor Green
        Write-Host "   - Service still exists and accessible" -ForegroundColor Green
        Write-Host "   - First request after idle will have 10-30s cold start" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "To restore always-on:" -ForegroundColor Blue
        Write-Host "   gcloud run services update $SERVICE_NAME --region $REGION --min-instances=1" -ForegroundColor White
        Write-Host ""
        
        if ($SERVICE_URL) {
            Write-Host "Service URL (still works): $SERVICE_URL" -ForegroundColor Cyan
        }
        
    } catch {
        Write-Host "Error scaling service: $($_.Exception.Message)" -ForegroundColor Red
    }
    
} else {
    Write-Host ""
    Write-Host "Operation cancelled. Service is still running." -ForegroundColor Gray
    Write-Host ""
    if ($SERVICE_URL) {
        Write-Host "Service URL: $SERVICE_URL" -ForegroundColor Cyan
    }
    Write-Host ""
    Write-Host "Current configuration:" -ForegroundColor Blue
    try {
        $serviceInfo = gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format="value(spec.template.metadata.annotations[run.googleapis.com/cpu],spec.template.spec.containers[0].resources.limits.memory)" 2>$null
        if ($serviceInfo) {
            Write-Host "   Memory: 4GB, CPU: 2 vCPU" -ForegroundColor White
            Write-Host "   Estimated cost: ~$15-40/month" -ForegroundColor White
        }
    } catch {
        Write-Host "   Could not get service configuration" -ForegroundColor Gray
    }
}

Read-Host "Press Enter to exit"