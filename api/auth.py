# api/auth.py - Updated to use the new auth service
from fastapi import Request, HTTPException, Depends
from typing import Optional, Dict, Any
import logging

# Import the new auth service
from services.auth.auth_service import (
    auth_service, 
    require_auth as _require_auth,
    get_template_context as _get_template_context,
    get_current_user
)
from config.settings import settings

logger = logging.getLogger(__name__)

# Backward compatibility functions for existing code
def require_auth(request: Request = None):
    """Dependency to require authentication - Updated"""
    if request:
        return auth_service.require_auth(request)
    
    # If called without request, return the dependency
    def _auth_dependency(request: Request):
        return auth_service.require_auth(request)
    return _auth_dependency

def get_template_context(request: Request) -> Dict[str, Any]:
    """Get template context - Updated"""
    return auth_service.get_template_context(request)

def create_session(request: Request, user_id: str = "admin") -> str:
    """Create a session - Updated"""
    return auth_service.session_manager.create_session(user_id)

def get_session_from_cookie(request: Request) -> Optional[str]:
    """Get session from cookie - Updated"""
    return auth_service.get_session_from_request(request)

def get_session_status(request: Request) -> Dict[str, Any]:
    """Get current session status - Updated"""
    session_id = auth_service.get_session_from_request(request)
    is_authenticated = auth_service.is_authenticated(request)
    session_info = None
    
    if session_id and is_authenticated:
        session_info = auth_service.session_manager.get_session_info(session_id)
    
    return {
        "authenticated": is_authenticated,
        "auth_required": settings.auth.require_auth,
        "session_id": session_id,
        "user_id": session_info.get("user_id") if session_info else None,
        "expires_at": session_info.get("expires_at").isoformat() if session_info and session_info.get("expires_at") else None
    }

def refresh_session(request: Request) -> Dict[str, str]:
    """Refresh current session - Updated"""
    session_id = auth_service.get_session_from_request(request)
    if session_id and auth_service.session_manager.validate_session(session_id):
        return {"status": "refreshed"}
    else:
        raise HTTPException(status_code=401, detail="No active session")

def cleanup_expired_sessions() -> int:
    """Clean up expired sessions - Updated"""
    # The new auth service automatically cleans up sessions
    auth_service.session_manager._cleanup_expired_sessions()
    return len(auth_service.session_manager._sessions)

# Legacy compatibility
REQUIRE_AUTH = settings.auth.require_auth
AUTH_PASSWORD = settings.auth.app_password
ENVIRONMENT = settings.environment
sessions = auth_service.session_manager._sessions  # Direct access for compatibility