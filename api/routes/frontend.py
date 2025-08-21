from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
import logging
from datetime import datetime
import os
import json
import httpx

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
templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "../templates")
templates = Jinja2Templates(directory=templates_dir)

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

@router.get("/wallet/add", response_class=HTMLResponse)
async def add_wallet_page(
    request: Request
):
    """Add wallet form page"""
    context = get_template_context(request)
    context.update({
        "title": "Add Smart Wallet",
        "page": "add_wallet"
    })
    return templates.TemplateResponse("add_wallet.html", context)

@router.get("/wallet/manage", response_class=HTMLResponse)
async def manage_wallets_page(
    request: Request,
):
    """Wallet management page"""
    context = get_template_context(request)
    context.update({
        "title": "Manage Wallets",
        "page": "manage_wallets"
    })
    return templates.TemplateResponse("manage_wallets.html", context)


@router.get("/token", response_class=HTMLResponse)
async def token_page_frontend(
    request: Request,
    contract: Optional[str] = Query(None, description="Token contract address"),
    token: Optional[str] = Query(None, description="Token symbol"),
    network: str = Query("ethereum", description="Network (ethereum or base)"),
    auth: bool = Depends(require_auth)
):
    """FIXED: Token details page - calls API backend for data"""
    
    context = get_template_context(request)
    
    # Determine contract address
    contract_address = contract or token
    
    logger.info(f"🔍 [FRONTEND] Token page request: contract={contract}, token={token}, network={network}")
    
    if not contract_address:
        context.update({
            "title": "Missing Parameters",
            "message": "Token contract address or symbol is required",
            "error_code": "400",
            "back_url": "/",
            "back_text": "Back to Dashboard"
        })
        return templates.TemplateResponse("error.html", context, status_code=400)
    
    # Validate network
    if network not in ["ethereum", "base"]:
        context.update({
            "title": "Invalid Network",
            "message": f"Network must be 'ethereum' or 'base', got '{network}'",
            "error_code": "400",
            "back_url": "/",
            "back_text": "Back to Dashboard"
        })
        return templates.TemplateResponse("error.html", context, status_code=400)
    
    # Validate address format
    if not _is_valid_ethereum_address(contract_address):
        context.update({
            "title": "Invalid Address",
            "message": f"Invalid contract address format: {contract_address}",
            "error_code": "400",
            "back_url": "/",
            "back_text": "Back to Dashboard"
        })
        return templates.TemplateResponse("error.html", context, status_code=400)
    
    logger.info(f"🔍 [FRONTEND] Loading token page for {contract_address} on {network}")
    
    try:
        # Call the API backend to get token data
        logger.info(f"🔍 [FRONTEND] Calling API backend for token data")
        
        # Make internal API call to get token data
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            # Get the base URL for the API call
            base_url = str(request.base_url).rstrip('/')
            api_url = f"{base_url}/api/token/{contract_address}"
            
            logger.info(f"🔍 [FRONTEND] API URL: {api_url}")
            
            # Call the API endpoint
            response = await client.get(
                api_url,
                params={"network": network},
                headers={"User-Agent": "Frontend-Internal-Call"}
            )
            
            logger.info(f"🔍 [FRONTEND] API response status: {response.status_code}")
            
            if response.status_code == 200:
                token_data = response.json()
                logger.info(f"🔍 [FRONTEND] API response received, status: {token_data.get('status')}")
            else:
                logger.error(f"🔍 [FRONTEND] API call failed: {response.status_code} - {response.text}")
                raise Exception(f"API call failed: {response.status_code}")
        
        # Validate token data structure
        if not token_data or not isinstance(token_data, dict):
            logger.error(f"🔍 [FRONTEND] Invalid token_data: {token_data}")
            raise Exception("Invalid token data received from API")
        
        # Ensure all required fields exist
        if not token_data.get('metadata'):
            token_data['metadata'] = {
                'symbol': 'UNKNOWN',
                'name': 'Unknown Token',
                'decimals': 18,
                'totalSupply': None,
                'verified': False
            }
        
        if not token_data.get('activity'):
            token_data['activity'] = {
                'wallet_count': 0,
                'total_purchases': 0,
                'total_eth_spent': 0.0,
                'alpha_score': 0.0,
                'platforms': [],
                'avg_wallet_score': 0.0
            }
        
        if not token_data.get('sell_pressure'):
            token_data['sell_pressure'] = {
                'sell_score': 0.0,
                'wallet_count': 0,
                'total_sells': 0,
                'methods': [],
                'total_eth_value': 0.0
            }
        
        if not token_data.get('purchases'):
            token_data['purchases'] = []
        
        if 'is_base_native' not in token_data:
            token_data['is_base_native'] = False
        
        if not token_data.get('last_updated'):
            token_data['last_updated'] = datetime.now().isoformat()
        
        # Create JSON for JavaScript
        try:
            token_data_json = json.dumps(token_data, default=str, ensure_ascii=False)
            logger.info(f"🔍 [FRONTEND] JSON serialization successful, length: {len(token_data_json)}")
        except Exception as json_error:
            logger.error(f"🔍 [FRONTEND] JSON serialization failed: {json_error}")
            # Create minimal fallback
            fallback_data = {
                "status": "error",
                "error": "JSON serialization failed",
                "metadata": {"symbol": "ERROR", "name": "Serialization Error"},
                "activity": {"wallet_count": 0, "total_purchases": 0, "total_eth_spent": 0.0, "alpha_score": 0.0, "platforms": [], "avg_wallet_score": 0.0},
                "sell_pressure": {"sell_score": 0.0, "wallet_count": 0, "total_sells": 0, "methods": [], "total_eth_value": 0.0},
                "purchases": [],
                "is_base_native": False
            }
            token_data_json = json.dumps(fallback_data, default=str)
            token_data = fallback_data
        
        # Update context with all required variables
        context.update({
            "contract": contract_address,
            "token": token,
            "network": network,
            "token_data": token_data,
            "token_data_json": token_data_json
        })
        
        # Log what we're passing to template
        logger.info(f"🔍 [FRONTEND] Context keys: {list(context.keys())}")
        logger.info(f"🔍 [FRONTEND] Token data status: {token_data.get('status')}")
        logger.info(f"🔍 [FRONTEND] Token symbol: {token_data.get('metadata', {}).get('symbol')}")
        
        # Verify template exists
        try:
            templates.get_template("token.html")
            logger.info(f"🔍 [FRONTEND] Template 'token.html' found")
        except Exception as template_error:
            logger.error(f"🔍 [FRONTEND] Template error: {template_error}")
            raise HTTPException(status_code=500, detail=f"Template error: {template_error}")
        
        logger.info(f"🔍 [FRONTEND] ✅ Rendering token page")
        return templates.TemplateResponse("token.html", context)
        
    except Exception as e:
        logger.error(f"🔍 [FRONTEND] ❌ Error loading token page: {e}", exc_info=True)
        
        # Create comprehensive fallback data
        fallback_data = {
            "contract_address": contract_address,
            "network": network,
            "metadata": {
                "symbol": "ERROR", 
                "name": f"Error: {str(e)[:50]}",
                "decimals": 18,
                "totalSupply": None,
                "verified": False
            },
            "activity": {
                "wallet_count": 0, 
                "total_purchases": 0, 
                "total_eth_spent": 0.0, 
                "alpha_score": 0.0, 
                "platforms": ["Error"], 
                "avg_wallet_score": 0.0
            },
            "sell_pressure": {
                "sell_score": 0.0, 
                "wallet_count": 0, 
                "total_sells": 0, 
                "methods": ["Error"], 
                "total_eth_value": 0.0
            },
            "purchases": [],
            "is_base_native": False,
            "last_updated": datetime.now().isoformat(),
            "analysis_timestamp": datetime.now().isoformat(),
            "status": "error",
            "error": str(e)
        }
        
        fallback_json = json.dumps(fallback_data, default=str)
        
        context.update({
            "contract": contract_address,
            "token": token,
            "network": network,
            "token_data": fallback_data,
            "token_data_json": fallback_json
        })
        
        logger.info(f"🔍 [FRONTEND] Using fallback data")
        return templates.TemplateResponse("token.html", context)

def _is_valid_ethereum_address(address: str) -> bool:
    """Validate Ethereum address format"""
    if not address:
        return False
    
    # Remove 0x prefix if present
    if address.startswith('0x'):
        address = address[2:]
    
    # Check length (40 hex characters)
    if len(address) != 40:
        return False
    
    # Check if all characters are hex
    try:
        int(address, 16)
        return True
    except ValueError:
        return False

# Test endpoint to verify API connectivity
@router.get("/token/test-api")
async def test_api_connectivity(request: Request):
    """Test API connectivity from frontend"""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            base_url = str(request.base_url).rstrip('/')
            test_url = f"{base_url}/api/token/test"
            
            logger.info(f"🧪 Testing API connectivity to: {test_url}")
            
            response = await client.get(test_url)
            
            return {
                "status": "success",
                "api_url": test_url,
                "api_status": response.status_code,
                "api_response": response.json() if response.status_code == 200 else response.text,
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        logger.error(f"🧪 API connectivity test failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Test template rendering
@router.get("/token/test-template", response_class=HTMLResponse)
async def test_template_rendering(request: Request):
    """Test template rendering with sample data"""
    
    test_token_data = {
        "contract_address": "0x1234567890123456789012345678901234567890",
        "network": "ethereum",
        "metadata": {
            "symbol": "TEST",
            "name": "Test Token",
            "decimals": 18,
            "totalSupply": "1000000000000000000000000",
            "verified": True
        },
        "activity": {
            "wallet_count": 5,
            "total_purchases": 10,
            "total_eth_spent": 1.5,
            "alpha_score": 75.0,
            "platforms": ["Uniswap", "SushiSwap"],
            "avg_wallet_score": 80.0
        },
        "sell_pressure": {
            "sell_score": 25.0,
            "wallet_count": 2,
            "total_sells": 3,
            "methods": ["Direct Sale"],
            "total_eth_value": 0.5
        },
        "purchases": [
            {
                "wallet": "0xtest1234567890123456789012345678901234",
                "amount": 1000,
                "eth_spent": 0.1,
                "platform": "Uniswap",
                "tx_hash": "0xtestTransaction123456789",
                "timestamp": "2025-08-19T12:00:00",
                "wallet_score": 85
            }
        ],
        "is_base_native": False,
        "last_updated": "2025-08-19T12:00:00",
        "analysis_timestamp": "2025-08-19T12:00:00",
        "status": "success"
    }
    
    context = get_template_context(request)
    context.update({
        "contract": "0x1234567890123456789012345678901234567890",
        "token": "TEST",
        "network": "ethereum",
        "token_data": test_token_data,
        "token_data_json": json.dumps(test_token_data, default=str)
    })
    
    logger.info(f"🧪 Test template rendering")
    return templates.TemplateResponse("token.html", context)

# API Status page for debugging
@router.get("/api-status", response_class=HTMLResponse)
async def api_status_page(request: Request, auth: bool = Depends(require_auth)):
    """API status page for debugging"""
    context = get_template_context(request)
    
    # Get system status
    try:
        # Test API connectivity
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            base_url = str(request.base_url).rstrip('/')
            
            # Test various API endpoints
            api_tests = {
                "token_test": f"{base_url}/api/token/test",
                "token_settings": f"{base_url}/api/token/test-settings"
            }
            
            api_results = {}
            for test_name, url in api_tests.items():
                try:
                    response = await client.get(url)
                    api_results[test_name] = {
                        "status": response.status_code,
                        "response": response.json() if response.status_code == 200 else response.text[:200]
                    }
                except Exception as e:
                    api_results[test_name] = {
                        "status": "error",
                        "error": str(e)
                    }
            
            context.update({
                "api_results": api_results,
                "sessions_count": len(sessions),
                "auth_enabled": REQUIRE_AUTH,
                "environment": ENVIRONMENT
            })
    except Exception as e:
        context["error"] = str(e)
    
    # Return JSON response for now
    return JSONResponse({
        "status": "healthy",
        "environment": ENVIRONMENT,
        "auth_enabled": REQUIRE_AUTH,
        "sessions_count": len(sessions),
        "api_tests": context.get("api_results", {}),
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

# Static file fallbacks for missing icons
@router.get("/favicon.ico")
async def favicon():
    """Serve favicon"""
    favicon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "icons", "icon-32x32.png")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/png")
    else:
        # Return 404 or a default favicon
        raise HTTPException(status_code=404, detail="Favicon not found")

# Service worker
@router.get("/sw.js")
async def service_worker():
    """Serve service worker"""
    sw_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "sw.js")
    if os.path.exists(sw_path):
        return FileResponse(sw_path, media_type="application/javascript")
    else:
        # Return a minimal service worker
        minimal_sw = """
        const CACHE_NAME = 'crypto-alpha-v1';
        
        self.addEventListener('install', function(event) {
            console.log('Service Worker installing');
        });
        
        self.addEventListener('fetch', function(event) {
            // Let the browser handle requests normally
        });
        """
        return JSONResponse(content=minimal_sw, media_type="application/javascript")

# Session management utilities
@router.get("/api/session/status")
async def session_status(request: Request):
    """Get current session status"""
    return get_session_status(request)

@router.post("/api/session/refresh")
async def refresh_session_endpoint(request: Request):
    """Refresh current session"""
    return refresh_session(request)

# Debug route for static files
@router.get("/debug/files")
async def debug_files():
    """Debug route to check file structure"""
    base_dir = os.path.dirname(os.path.dirname(__file__))
    static_dir = os.path.join(base_dir, "static")
    templates_dir = os.path.join(base_dir, "templates")
    
    result = {
        "base_directory": base_dir,
        "static_directory": static_dir,
        "templates_directory": templates_dir,
        "static_exists": os.path.exists(static_dir),
        "templates_exists": os.path.exists(templates_dir),
        "files": {}
    }
    
    if os.path.exists(static_dir):
        result["files"]["static"] = []
        for root, dirs, files in os.walk(static_dir):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), static_dir)
                result["files"]["static"].append(rel_path)
    
    if os.path.exists(templates_dir):
        result["files"]["templates"] = []
        for root, dirs, files in os.walk(templates_dir):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), templates_dir)
                result["files"]["templates"].append(rel_path)
    
    return result