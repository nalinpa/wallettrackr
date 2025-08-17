from fastapi import Request, HTTPException
from typing import Optional
import time
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# Configuration
REQUIRE_AUTH = os.environ.get('REQUIRE_AUTH', 'false').lower() == 'true'
AUTH_PASSWORD = os.environ.get('AUTH_PASSWORD', 'admin')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')

# Simple session store (use Redis in production)
sessions = {}

def create_session(request: Request, user_id: str = "user"):
    """Create a session for the user"""
    session_id = f"session_{len(sessions)}_{int(time.time())}"
    sessions[session_id] = {"user_id": user_id, "created": datetime.now()}
    return session_id

def get_session_from_cookie(request: Request) -> Optional[str]:
    """Get session from cookie"""
    session_id = request.cookies.get("session_id")
    return session_id if session_id and session_id in sessions else None

def require_auth(request: Request):
    """Dependency to require authentication"""
    if not REQUIRE_AUTH:
        return True
    
    session_id = get_session_from_cookie(request)
    if not session_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return True

def get_template_context(request: Request):
    """Get common template context"""
    return {
        "request": request,
        "current_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "environment": ENVIRONMENT,
        "require_auth": REQUIRE_AUTH,
        "authenticated": get_session_from_cookie(request) is not None or not REQUIRE_AUTH
    }

def cleanup_expired_sessions():
    """Clean up expired sessions"""
    current_time = datetime.now()
    expired_sessions = []
    
    for session_id, session_data in sessions.items():
        # Sessions expire after 24 hours of inactivity
        last_activity = session_data.get("last_activity", session_data["created"])
        if (current_time - last_activity).total_seconds() > 86400:
            expired_sessions.append(session_id)
    
    for session_id in expired_sessions:
        del sessions[session_id]
        
    if expired_sessions:
        logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
    
    return len(expired_sessions)

# Session management utilities
def get_session_status(request: Request):
    """Get current session status"""
    session_id = get_session_from_cookie(request)
    is_authenticated = session_id is not None or not REQUIRE_AUTH
    
    return {
        "authenticated": is_authenticated,
        "auth_required": REQUIRE_AUTH,
        "session_id": session_id if session_id else None,
        "user_id": sessions.get(session_id, {}).get("user_id") if session_id else None
    }

def refresh_session(request: Request):
    """Refresh current session"""
    session_id = get_session_from_cookie(request)
    if session_id and session_id in sessions:
        sessions[session_id]["last_activity"] = datetime.now()
        return {"status": "refreshed"}
    else:
        raise HTTPException(status_code=401, detail="No active session")