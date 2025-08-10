# startup-service.ps1 - Quick redeploy after shutdown

$SERVICE_NAME = "crypto-alpha-analysis"
$REGION = "asia-southeast1"
$PROJECT_ID = "crypto-track-468604" 

Write-Host "=== Crypto Alpha Service Startup ===" -ForegroundColor Green
Write-Host ""

# Check if service already exists
try {
    $serviceExists = gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format="value(metadata.name)" 2>$null
    if ($serviceExists) {
        $SERVICE_URL = gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format='value(status.url)'
        Write-Host "Service '$SERVICE_NAME' already exists!" -ForegroundColor Blue
        Write-Host "URL: $SERVICE_URL" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Testing if it's responding..." -ForegroundColor Yellow
        
        try {
            $response = Invoke-WebRequest -Uri "$SERVICE_URL/api/status" -TimeoutSec 15 -UseBasicParsing
            if ($response.StatusCode -eq 200) {
                Write-Host "Service is already running and responding!" -ForegroundColor Green
                Write-Host "Dashboard: $SERVICE_URL" -ForegroundColor Cyan
                Write-Host "Monitor: $SERVICE_URL/monitor" -ForegroundColor Cyan
                Read-Host "Press Enter to exit"
                exit 0
            }
        } catch {
            Write-Host "Service exists but not responding (cold start needed)" -ForegroundColor Yellow
            Write-Host "Visit: $SERVICE_URL" -ForegroundColor Cyan
            Read-Host "Press Enter to exit"
            exit 0
        }
    }
} catch {
    Write-Host "Service not found. Need to deploy..." -ForegroundColor Yellow
}

Write-Host "Starting deployment process..." -ForegroundColor Blue
Write-Host ""

# Check if secure-deploy.ps1 exists
if (Test-Path ".\secure-deploy.ps1") {
    Write-Host "Found deploy script. Running deployment..." -ForegroundColor Green
    Write-Host ""
    
    # Run the deployment script
    try {
        & ".\secure-deploy.ps1"
        Write-Host ""
        Write-Host "Deployment completed!" -ForegroundColor Green
    } catch {
        Write-Host "Deployment failed: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host ""
        Write-Host "Try running manually:" -ForegroundColor Yellow
        Write-Host "   .\secure-deploy.ps1" -ForegroundColor White
    }
    
} else {
    Write-Host "secure-deploy.ps1 not found in current directory!" -ForegroundColor Red
    Write-Host ""
    Write-Host "To deploy manually, run:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "gcloud run deploy $SERVICE_NAME --image gcr.io/$PROJECT_ID/$SERVICE_NAME --platform managed --region $REGION --allow-unauthenticated" -ForegroundColor White
    Write-Host ""
}

Read-Host "Press Enter to exit"