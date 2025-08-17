from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
import logging
from datetime import datetime

# Import auth functions from centralized auth module
from api.auth import (
    require_auth, 
    get_template_context, 
    create_session, 
    get_session_from_cookie,
    get_session_status,
    refresh_session,
    cleanup_expired_sessions,
    sessions,
    REQUIRE_AUTH,
    AUTH_PASSWORD,
    ENVIRONMENT
)

logger = logging.getLogger(__name__)

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Create router
router = APIRouter(tags=["frontend"])

# Frontend Routes
@router.get("/", response_class=HTMLResponse)
async def index(request: Request, auth: bool = Depends(require_auth)):
    """Dashboard page"""
    context = get_template_context(request)
    return templates.TemplateResponse("dashboard.html", context)

@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    """Login page"""
    if not REQUIRE_AUTH:
        return RedirectResponse(url="/", status_code=302)
    
    # If already authenticated, redirect to dashboard
    if get_session_from_cookie(request):
        return RedirectResponse(url="/", status_code=302)
    
    context = get_template_context(request)
    return templates.TemplateResponse("login.html", context)

@router.post("/login")
async def login_post(request: Request, password: str = Form(...)):
    """Handle login form submission"""
    if not REQUIRE_AUTH:
        return RedirectResponse(url="/", status_code=302)
    
    if password == AUTH_PASSWORD:
        session_id = create_session(request)
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            "session_id", 
            session_id, 
            httponly=True, 
            secure=ENVIRONMENT == 'production',
            max_age=86400  # 24 hours
        )
        logger.info("User logged in successfully")
        return response
    else:
        context = get_template_context(request)
        context["error"] = "Invalid password"
        logger.warning("Failed login attempt")
        return templates.TemplateResponse("login.html", context)

@router.get("/logout")
async def logout(request: Request):
    """Logout user"""
    session_id = get_session_from_cookie(request)
    if session_id and session_id in sessions:
        del sessions[session_id]
        logger.info("User logged out")
    
    response = RedirectResponse(url="/login" if REQUIRE_AUTH else "/", status_code=302)
    response.delete_cookie("session_id")
    return response

@router.get("/monitor", response_class=HTMLResponse)
async def monitor_page(request: Request, auth: bool = Depends(require_auth)):
    """Monitor page"""
    context = get_template_context(request)
    return templates.TemplateResponse("monitor.html", context)

@router.get("/token", response_class=HTMLResponse)
async def token_details(
    request: Request, 
    contract: Optional[str] = Query(None, description="Token contract address"),
    token: Optional[str] = Query(None, description="Token symbol"),
    network: str = Query("ethereum", description="Network (ethereum or base)"),
    auth: bool = Depends(require_auth)
):
    """Token details page"""
    if not contract and not token:
        context = get_template_context(request)
        context.update({
            "title": "Missing Parameters",
            "message": "Token contract address or symbol is required",
            "error_code": "400",
            "back_url": "/",
            "back_text": "Back to Dashboard"
        })
        return templates.TemplateResponse("error.html", context, status_code=400)
    
    context = get_template_context(request)
    context.update({
        "contract": contract,
        "token": token,
        "network": network
    })
    return templates.TemplateResponse("token.html", context)

# API Status page for debugging
@router.get("/api-status", response_class=HTMLResponse)
async def api_status_page(request: Request, auth: bool = Depends(require_auth)):
    """API status page for debugging"""
    context = get_template_context(request)
    
    # Get system status
    try:
        from data_service import AnalysisService
        service = AnalysisService()
        cache_stats = service.get_cache_stats()
        
        context.update({
            "cache_stats": cache_stats,
            "sessions_count": len(sessions),
            "auth_enabled": REQUIRE_AUTH,
            "environment": ENVIRONMENT
        })
    except Exception as e:
        context["error"] = str(e)
    
    # Create a simple status template response
    status_html = """
    {% extends "base.html" %}
    {% block title %}API Status{% endblock %}
    {% block content %}
    <div class="row">
        <div class="col-12">
            <div class="crypto-card p-4">
                <h2><i class="fas fa-cog text-primary me-2"></i>System Status</h2>
                
                <div class="row g-3 mt-3">
                    <div class="col-md-6">
                        <h5>Application</h5>
                        <ul class="list-unstyled">
                            <li><strong>Environment:</strong> {{ environment }}</li>
                            <li><strong>Authentication:</strong> {{ "Enabled" if auth_enabled else "Disabled" }}</li>
                            <li><strong>Active Sessions:</strong> {{ sessions_count }}</li>
                        </ul>
                    </div>
                    
                    <div class="col-md-6">
                        <h5>Cache Statistics</h5>
                        {% if cache_stats %}
                        <ul class="list-unstyled">
                            <li><strong>Total Entries:</strong> {{ cache_stats.total_entries }}</li>
                            <li><strong>Active Entries:</strong> {{ cache_stats.active_entries }}</li>
                            <li><strong>Cache TTL:</strong> {{ cache_stats.cache_ttl_seconds }}s</li>
                        </ul>
                        {% else %}
                        <p class="text-muted">Cache stats unavailable</p>
                        {% endif %}
                    </div>
                </div>
                
                {% if error %}
                <div class="alert alert-danger mt-3">
                    <strong>Error:</strong> {{ error }}
                </div>
                {% endif %}
                
                <div class="mt-4">
                    <a href="/" class="btn btn-primary">
                        <i class="fas fa-arrow-left me-2"></i>Back to Dashboard
                    </a>
                    <a href="/docs" class="btn btn-info ms-2" target="_blank">
                        <i class="fas fa-book me-2"></i>API Documentation
                    </a>
                </div>
            </div>
        </div>
    </div>
    {% endblock %}
    """
    
    # For now, return a simple JSON response instead of rendering template
    return JSONResponse({
        "status": "healthy",
        "environment": ENVIRONMENT,
        "auth_enabled": REQUIRE_AUTH,
        "sessions_count": len(sessions),
        "cache_stats": context.get("cache_stats"),
        "timestamp": datetime.now().isoformat()
    })

# Health check for frontend
@router.get("/health")
async def frontend_health():
    """Frontend health check"""
    return {
        "status": "healthy",
        "service": "frontend",
        "timestamp": datetime.now().isoformat(),
        "auth_enabled": REQUIRE_AUTH,
        "sessions_active": len(sessions)
    }

# PWA Support routes
@router.get("/manifest.json")
async def pwa_manifest():
    """PWA manifest file"""
    return {
        "name": "Crypto Alpha Analysis",
        "short_name": "CryptoAlpha", 
        "description": "Real-time smart wallet tracking and alpha token discovery",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f0f23",
        "theme_color": "#667eea",
        "orientation": "portrait-primary",
        "scope": "/",
        "icons": [
            {
                "src": "/static/icons/icon-72x72.png",
                "sizes": "72x72",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icons/icon-96x96.png", 
                "sizes": "96x96",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icons/icon-128x128.png",
                "sizes": "128x128", 
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icons/icon-144x144.png",
                "sizes": "144x144",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icons/icon-152x152.png",
                "sizes": "152x152",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icons/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icons/icon-384x384.png",
                "sizes": "384x384",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icons/icon-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ],
        "categories": ["finance", "productivity", "utilities"],
        "screenshots": [
            {
                "src": "/static/images/screenshot1.png",
                "sizes": "1280x720",
                "type": "image/png",
                "form_factor": "wide"
            }
        ]
    }

# Session management utilities
@router.get("/api/session/status")
async def session_status(request: Request):
    """Get current session status"""
    return get_session_status(request)

@router.post("/api/session/refresh")
async def refresh_session_endpoint(request: Request):
    """Refresh current session"""
    return refresh_session(request)