# startup-service.ps1 - Quick redeploy after shutdown

$SERVICE_NAME = "crypto-alpha-analysis"
$REGION = "asia-southeast1"
$PROJECT_ID = "crypto-track-468604" 

Write-Host "=== Crypto Alpha FastAPI Service Startup ===" -ForegroundColor Green
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
            # Test FastAPI health endpoint first
            $healthResponse = Invoke-RestMethod -Uri "$SERVICE_URL/health" -TimeoutSec 15
            if ($healthResponse.status -eq "healthy") {
                Write-Host "✅ FastAPI service is healthy and responding!" -ForegroundColor Green
                Write-Host "   Version: $($healthResponse.version)" -ForegroundColor Gray
                Write-Host "   Environment: $($healthResponse.environment)" -ForegroundColor Gray
                Write-Host ""
                Write-Host "Available endpoints:" -ForegroundColor Cyan
                Write-Host "   Dashboard: $SERVICE_URL/" -ForegroundColor White
                Write-Host "   Monitor: $SERVICE_URL/monitor" -ForegroundColor White
                Write-Host "   API Docs: $SERVICE_URL/docs" -ForegroundColor White
                Write-Host "   API Status: $SERVICE_URL/api/status" -ForegroundColor White
                Write-Host ""
                
                # Test if service is scaled to zero
                try {
                    $serviceInfo = gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format=json | ConvertFrom-Json
                    $minInstances = $serviceInfo.spec.template.metadata.annotations.'run.googleapis.com/execution-environment'
                    
                    # Check current scaling
                    $traffic = $serviceInfo.status.traffic
                    if ($traffic -and $traffic[0].percent -eq 100) {
                        Write-Host "✅ Service is fully active" -ForegroundColor Green
                    }
                } catch {
                    # Scaling info not critical
                }
                
                Read-Host "Press Enter to exit"
                exit 0
            } else {
                Write-Host "⚠️ Service responding but status: $($healthResponse.status)" -ForegroundColor Yellow
            }
        } catch {
            # Try the API status endpoint as fallback
            try {
                $response = Invoke-WebRequest -Uri "$SERVICE_URL/api/status" -TimeoutSec 15 -UseBasicParsing
                if ($response.StatusCode -eq 200) {
                    Write-Host "✅ Service is responding (via API status)!" -ForegroundColor Green
                    Write-Host "   Dashboard: $SERVICE_URL/" -ForegroundColor Cyan
                    Write-Host "   Monitor: $SERVICE_URL/monitor" -ForegroundColor Cyan
                    Write-Host "   API Docs: $SERVICE_URL/docs" -ForegroundColor Cyan
                    Read-Host "Press Enter to exit"
                    exit 0
                }
            } catch {
                Write-Host "⚠️ Service exists but not responding (cold start needed)" -ForegroundColor Yellow
                Write-Host "   This is normal if service was scaled to zero" -ForegroundColor Gray
                Write-Host "   First request may take 10-30 seconds" -ForegroundColor Gray
                Write-Host ""
                Write-Host "Try visiting: $SERVICE_URL" -ForegroundColor Cyan
                Write-Host ""
                
                # Check if service is scaled to zero
                $scaleChoice = Read-Host "Scale service to min-instances=1 to avoid cold starts? (y/N)"
                if ($scaleChoice -eq 'y' -or $scaleChoice -eq 'Y') {
                    try {
                        Write-Host "Scaling service to 1 minimum instance..." -ForegroundColor Blue
                        gcloud run services update $SERVICE_NAME --platform managed --region $REGION --min-instances=1 --quiet
                        Write-Host "✅ Service scaled to 1 minimum instance" -ForegroundColor Green
                        Write-Host "   Service will now respond immediately" -ForegroundColor Gray
                        Write-Host "   Cost: ~$15-40/month" -ForegroundColor Gray
                    } catch {
                        Write-Host "❌ Failed to scale service" -ForegroundColor Red
                    }
                }
                
                Read-Host "Press Enter to exit"
                exit 0
            }
        }
    }
} catch {
    Write-Host "Service not found. Need to deploy..." -ForegroundColor Yellow
}

Write-Host "Starting FastAPI deployment process..." -ForegroundColor Blue
Write-Host ""

# Check if secure-deploy.ps1 exists
if (Test-Path ".\secure-deploy.ps1") {
    Write-Host "Found deploy script. Running FastAPI deployment..." -ForegroundColor Green
    Write-Host ""
    
    # Run the deployment script
    try {
        & ".\secure-deploy.ps1"
        Write-Host ""
        Write-Host "FastAPI deployment completed!" -ForegroundColor Green
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
    Write-Host "# Build and deploy FastAPI service:" -ForegroundColor Gray
    Write-Host "gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME" -ForegroundColor White
    Write-Host "gcloud run deploy $SERVICE_NAME --image gcr.io/$PROJECT_ID/$SERVICE_NAME --platform managed --region $REGION --allow-unauthenticated --port 8001 --memory 4Gi --cpu 2" -ForegroundColor White
    Write-Host ""
    Write-Host "Or create the deployment script:" -ForegroundColor Yellow
    Write-Host "   Copy secure-deploy.ps1 from the provided templates" -ForegroundColor White
    Write-Host ""
}

Read-Host "Press Enter to exit"