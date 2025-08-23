
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging
from config.settings import settings

logger = logging.getLogger(__name__)

class AuthRedirectMiddleware(BaseHTTPMiddleware):
    """Middleware to redirect unauthenticated users to login page"""
    
    def __init__(self, app):
        super().__init__(app)
        
        # Pages that don't require authentication
        self.public_paths = {
            "/login",
            "/logout", 
            "/health",
            "/favicon.ico",
            "/manifest.json",
            "/sw.js",
            "/api/auth/login",
            "/api/auth/status",
            "/debug/auth",  # Temporary debug endpoint
        }
        
        # Static file prefixes that don't require auth
        self.public_prefixes = {
            "/static/",
            "/docs",
            "/redoc",
            "/openapi.json"
        }
    
    async def dispatch(self, request: Request, call_next):
        # Skip auth middleware if auth is disabled
        if not settings.auth.require_auth:
            return await call_next(request)
        
        path = request.url.path
        
        # Allow public paths
        if path in self.public_paths:
            return await call_next(request)
        
        # Allow public prefixes
        if any(path.startswith(prefix) for prefix in self.public_prefixes):
            return await call_next(request)
        
        # Check authentication
        from services.auth.auth_service import auth_service
        
        try:
            is_authenticated = auth_service.is_authenticated(request)
            
            if not is_authenticated:
                # For API calls, return 401
                if path.startswith("/api/"):
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Authentication required"}
                    )
                
                # For web pages, redirect to login
                logger.info(f"🔒 Redirecting unauthenticated user from {path} to /login")
                return RedirectResponse(url="/login", status_code=302)
            
            # User is authenticated, continue
            return await call_next(request)
            
        except Exception as e:
            logger.error(f"❌ Auth middleware error: {e}")
            # On error, redirect to login for safety
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Authentication system error"}
                )
            return RedirectResponse(url="/login", status_code=302)

# Add this to your main.py after creating the FastAPI app
from fastapi.responses import JSONResponse

# Add the middleware to your app
app.add_middleware(AuthRedirectMiddleware)