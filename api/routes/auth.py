from fastapi import APIRouter, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import logging
from datetime import datetime
import os

from services.auth.auth_service import auth_service
from config.settings import settings

logger = logging.getLogger(__name__)

# Initialize templates
templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "../templates")
templates = Jinja2Templates(directory=templates_dir)

router = APIRouter(tags=["authentication"])

# Pydantic models for API requests
class LoginRequest(BaseModel):
    password: str

class LoginResponse(BaseModel):
    success: bool
    message: str
    redirect_url: str = "/"

# HTML Login/Logout Routes
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    if not settings.auth.require_auth:
        return RedirectResponse(url="/", status_code=302)
    
    # If already authenticated, redirect to dashboard
    if auth_service.is_authenticated(request):
        return RedirectResponse(url="/", status_code=302)
    
    context = auth_service.get_template_context(request)
    context.update({
        "title": "Login - Crypto Alpha Tracker",
        "page": "login"
    })
    
    return templates.TemplateResponse("login.html", context)

@router.post("/login", response_class=HTMLResponse)
async def login_form(request: Request, password: str = Form(...)):
    """Handle HTML form login"""
    if not settings.auth.require_auth:
        return RedirectResponse(url="/", status_code=302)
    
    try:
        session_id = auth_service.authenticate(password)
        
        if session_id:
            # Successful login
            response = RedirectResponse(url="/", status_code=302)
            response.set_cookie(
                "session_id",
                session_id,
                httponly=True,
                secure=settings.environment == "production",
                max_age=settings.auth.session_timeout_hours * 3600,
                samesite="lax"
            )
            logger.info("✅ User logged in successfully via form")
            return response
        else:
            # Failed login
            context = auth_service.get_template_context(request)
            context.update({
                "title": "Login - Crypto Alpha Tracker",
                "page": "login",
                "error": "Invalid password. Please try again.",
                "password_hint": "Check your .env file for APP_PASSWORD"
            })
            return templates.TemplateResponse("login.html", context)
            
    except Exception as e:
        logger.error(f"❌ Login error: {e}")
        context = auth_service.get_template_context(request)
        context.update({
            "title": "Login - Crypto Alpha Tracker",
            "page": "login",
            "error": "Login system error. Please try again."
        })
        return templates.TemplateResponse("login.html", context)

@router.get("/logout")
async def logout(request: Request):
    """Logout user"""
    auth_service.logout(request)
    
    response = RedirectResponse(
        url="/login" if settings.auth.require_auth else "/", 
        status_code=302
    )
    response.delete_cookie("session_id")
    
    logger.info("✅ User logged out")
    return response

# JSON API Routes
@router.post("/api/auth/login", response_model=LoginResponse)
async def api_login(request: Request, login_data: LoginRequest):
    """API login endpoint"""
    if not settings.auth.require_auth:
        return LoginResponse(
            success=True,
            message="Authentication not required",
            redirect_url="/"
        )
    
    try:
        session_id = auth_service.authenticate(login_data.password)
        
        if session_id:
            # Create response
            response = JSONResponse(content={
                "success": True,
                "message": "Login successful",
                "redirect_url": "/"
            })
            
            # Set session cookie
            response.set_cookie(
                "session_id",
                session_id,
                httponly=True,
                secure=settings.environment == "production",
                max_age=settings.auth.session_timeout_hours * 3600,
                samesite="lax"
            )
            
            logger.info("✅ User logged in successfully via API")
            return response
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login system error"
        )

@router.post("/api/auth/logout")
async def api_logout(request: Request):
    """API logout endpoint"""
    success = auth_service.logout(request)
    
    response = JSONResponse(content={
        "success": True,
        "message": "Logged out successfully"
    })
    response.delete_cookie("session_id")
    
    logger.info("✅ User logged out via API")
    return response

@router.get("/api/auth/status")
async def auth_status(request: Request):
    """Get authentication status"""
    session_id = auth_service.get_session_from_request(request)
    is_authenticated = auth_service.is_authenticated(request)
    session_info = None
    
    if session_id and is_authenticated:
        session_info = auth_service.session_manager.get_session_info(session_id)
    
    return {
        "authenticated": is_authenticated,
        "auth_required": settings.auth.require_auth,
        "session_id": session_id[:8] + "..." if session_id else None,
        "user_id": session_info.get("user_id") if session_info else None,
        "expires_at": session_info.get("expires_at").isoformat() if session_info and session_info.get("expires_at") else None,
        "last_activity": session_info.get("last_activity").isoformat() if session_info and session_info.get("last_activity") else None
    }

@router.post("/api/auth/refresh")
async def refresh_session_api(request: Request):
    """Refresh current session"""
    session_id = auth_service.get_session_from_request(request)
    
    if session_id and auth_service.session_manager.validate_session(session_id):
        return {"success": True, "message": "Session refreshed"}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No active session to refresh"
        )

@router.get("/api/auth/stats")
async def auth_stats(request: Request):
    """Get authentication statistics (admin only)"""
    # Require authentication for stats
    if not auth_service.is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    stats = auth_service.get_auth_stats()
    return {
        "status": "success",
        "stats": stats,
        "timestamp": datetime.now().isoformat()
    }

# Development/Testing endpoints
@router.get("/auth/test")
async def test_auth_config():
    """Test authentication configuration"""
    return {
        "auth_enabled": settings.auth.require_auth,
        "password_configured": bool(settings.auth.app_password and settings.auth.app_password != "admin"),
        "session_timeout_hours": settings.auth.session_timeout_hours,
        "environment": settings.environment,
        "timestamp": datetime.now().isoformat(),
        "recommendations": [
            "Set a strong APP_PASSWORD in your .env file" if settings.auth.app_password == "admin" else "✅ Custom password configured",
            "Consider enabling HTTPS in production" if settings.environment == "production" else "✅ Development mode",
            f"Sessions expire after {settings.auth.session_timeout_hours} hours"
        ]
    }