# shutdown-service.ps1 - Complete service deletion to stop all charges

$SERVICE_NAME = "crypto-alpha-analysis"
$REGION = "asia-southeast1"
$PROJECT_ID = "crypto-track-468604" 

Write-Host "=== Crypto Alpha Service Shutdown ===" -ForegroundColor Red
Write-Host ""
Write-Host "This will COMPLETELY DELETE your Cloud Run service to stop all charges." -ForegroundColor Yellow
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

# Get current service URL before deletion
try {
    $SERVICE_URL = gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format='value(status.url)' 2>$null
    if ($SERVICE_URL) {
        Write-Host "Current service URL: $SERVICE_URL" -ForegroundColor Cyan
    }
} catch {
    # Service might not be responding
}

Write-Host ""
Write-Host "After deletion:" -ForegroundColor Green
Write-Host "   Cloud Run charges: $0.00/month" -ForegroundColor Green
Write-Host "   MongoDB Atlas: ~$9/month (still active)" -ForegroundColor Yellow
Write-Host ""

# Confirmation prompt
$confirm = Read-Host "Type 'DELETE' to confirm deletion (or anything else to cancel)"

if ($confirm -eq "DELETE") {
    Write-Host ""
    Write-Host "Deleting service..." -ForegroundColor Red
    
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
        Write-Host ""
        
    } catch {
        Write-Host "Error deleting service: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "You can also delete it manually in the Cloud Console:" -ForegroundColor Yellow
        Write-Host "   https://console.cloud.google.com/run?project=$PROJECT_ID" -ForegroundColor White
    }
    
} else {
    Write-Host ""
    Write-Host "Deletion cancelled. Service is still running." -ForegroundColor Gray
    Write-Host ""
    Write-Host "Alternative - Scale to zero (no idle costs):" -ForegroundColor Blue
    Write-Host "   gcloud run services update $SERVICE_NAME --platform managed --region $REGION --min-instances=0" -ForegroundColor White
    Write-Host ""
}

Read-Host "Press Enter to exit"