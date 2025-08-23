import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.templating import Jinja2Templates
import logging

from config.settings import settings

logger = logging.getLogger(__name__)

class SessionManager:
    """Simple in-memory session management"""
    
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._cleanup_interval = 3600  # 1 hour
        self._last_cleanup = time.time()
    
    def create_session(self, user_id: str = "admin") -> str:
        """Create a new session"""
        session_id = secrets.token_urlsafe(32)
        expiry = datetime.now() + timedelta(hours=settings.auth.session_timeout_hours)
        
        self._sessions[session_id] = {
            "user_id": user_id,
            "created_at": datetime.now(),
            "expires_at": expiry,
            "last_activity": datetime.now()
        }
        
        logger.info(f"✅ Session created: {session_id[:8]}... (expires: {expiry})")
        return session_id
    
    def validate_session(self, session_id: str) -> bool:
        """Validate a session"""
        self._cleanup_expired_sessions()
        
        if not session_id or session_id not in self._sessions:
            return False
        
        session = self._sessions[session_id]
        now = datetime.now()
        
        if now > session["expires_at"]:
            self.delete_session(session_id)
            return False
        
        # Update last activity
        session["last_activity"] = now
        return True
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"🗑️ Session deleted: {session_id[:8]}...")
            return True
        return False
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session information"""
        if session_id in self._sessions:
            return self._sessions[session_id].copy()
        return None
    
    def _cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        current_time = datetime.now()
        expired_sessions = [
            sid for sid, session in self._sessions.items()
            if current_time > session["expires_at"]
        ]
        
        for session_id in expired_sessions:
            del self._sessions[session_id]
        
        if expired_sessions:
            logger.info(f"🧹 Cleaned up {len(expired_sessions)} expired sessions")
        
        self._last_cleanup = now
    
    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        self._cleanup_expired_sessions()
        
        active_sessions = len(self._sessions)
        total_created = active_sessions  # Simplified
        
        oldest_session = None
        if self._sessions:
            oldest = min(self._sessions.values(), key=lambda s: s["created_at"])
            oldest_session = oldest["created_at"].isoformat()
        
        return {
            "active_sessions": active_sessions,
            "total_created_today": total_created,
            "oldest_session": oldest_session,
            "cleanup_interval_hours": self._cleanup_interval / 3600
        }

class AuthService:
    """Authentication service"""
    
    def __init__(self):
        self.session_manager = SessionManager()
        self.security = HTTPBearer(auto_error=False)
    
    def verify_password(self, password: str) -> bool:
        """Verify password against configured password"""
        if not settings.auth.require_auth:
            return True
        
        return password == settings.auth.app_password
    
    def authenticate(self, password: str) -> Optional[str]:
        """Authenticate user and return session ID"""
        if not self.verify_password(password):
            logger.warning("❌ Failed authentication attempt")
            return None
        
        session_id = self.session_manager.create_session()
        logger.info("✅ User authenticated successfully")
        return session_id
    
    def get_session_from_request(self, request: Request) -> Optional[str]:
        """Extract session ID from request cookies"""
        return request.cookies.get("session_id")
    
    def is_authenticated(self, request: Request) -> bool:
        """Check if request is authenticated"""
        if not settings.auth.require_auth:
            return True
        
        session_id = self.get_session_from_request(request)
        if not session_id:
            return False
        
        return self.session_manager.validate_session(session_id)
    
    def require_auth(self, request: Request) -> bool:
        """Dependency to require authentication"""
        if not settings.auth.require_auth:
            return True
        
        if not self.is_authenticated(request):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        return True
    
    def logout(self, request: Request) -> bool:
        """Logout user by invalidating session"""
        session_id = self.get_session_from_request(request)
        if session_id:
            return self.session_manager.delete_session(session_id)
        return False
    
    def get_template_context(self, request: Request) -> Dict[str, Any]:
        """Get authentication context for templates"""
        is_authenticated = self.is_authenticated(request)
        session_id = self.get_session_from_request(request)
        session_info = None
        
        if session_id and is_authenticated:
            session_info = self.session_manager.get_session_info(session_id)
        
        return {
            "request": request,
            "authenticated": is_authenticated,
            "auth_required": settings.auth.require_auth,
            "current_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "environment": settings.environment,
            "session_info": session_info,
            "app_name": "Crypto Alpha Tracker"
        }
    
    def get_auth_stats(self) -> Dict[str, Any]:
        """Get authentication statistics"""
        stats = self.session_manager.get_stats()
        stats.update({
            "auth_enabled": settings.auth.require_auth,
            "session_timeout_hours": settings.auth.session_timeout_hours,
            "password_configured": bool(settings.auth.app_password and settings.auth.app_password != "admin")
        })
        return stats

# Global auth service instance
auth_service = AuthService()

# FastAPI Dependencies
def require_auth(request: Request) -> bool:
    """FastAPI dependency for requiring authentication"""
    return auth_service.require_auth(request)

def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """FastAPI dependency to get current user info"""
    if not auth_service.is_authenticated(request):
        return None
    
    session_id = auth_service.get_session_from_request(request)
    if session_id:
        return auth_service.session_manager.get_session_info(session_id)
    return None

def get_template_context(request: Request) -> Dict[str, Any]:
    """FastAPI dependency for template context"""
    return auth_service.get_template_context(request)

# Utility functions
def hash_password(password: str) -> str:
    """Hash a password (for future use)"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_hashed_password(password: str, hashed: str) -> bool:
    """Verify a hashed password (for future use)"""
    return hash_password(password) == hashed