from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, Dict, Any, List
import asyncio
import logging
from datetime import datetime
import time
import json
import httpx
import orjson

# Import your settings
from config.settings import settings, alchemy_config

# Try to import auth, but provide fallback
try:
    from api.auth import require_auth, get_template_context
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    def require_auth():
        return True
    def get_template_context(request):
        return {"request": request}

logger = logging.getLogger(__name__)
router = APIRouter(tags=["token"])
templates = Jinja2Templates(directory="templates")

@router.get("/token", response_class=HTMLResponse)
async def token_page(
    request: Request,
    contract: Optional[str] = Query(None, description="Token contract address"),
    token: Optional[str] = Query(None, description="Token symbol"),
    network: str = Query("ethereum", description="Network (ethereum or base)"),
    auth: bool = Depends(require_auth) if AUTH_AVAILABLE else None
):
    """Token details page using your settings configuration"""
    
    # Get template context
    if AUTH_AVAILABLE:
        context = get_template_context(request)
    else:
        context = {"request": request}
    
    # Determine contract address
    contract_address = contract or token
    
    logger.info(f"🔍 Token page request: contract={contract}, token={token}, network={network}")
    
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
    if not _is_valid_address(contract_address):
        context.update({
            "title": "Invalid Address",
            "message": f"Invalid contract address format: {contract_address}",
            "error_code": "400",
            "back_url": "/",
            "back_text": "Back to Dashboard"
        })
        return templates.TemplateResponse("error.html", context, status_code=400)
    
    logger.info(f"🔍 Loading token page for {contract_address} on {network}")
    
    try:
        # Load token data using your settings
        token_data = await get_token_data_with_settings(contract_address, network)
        
        # Update context with token data
        context.update({
            "contract": contract_address,
            "token": token,
            "network": network,
            "token_data": token_data,
            "token_data_json": json.dumps(token_data, default=str)  # For JavaScript
        })
        
        logger.info(f"✅ Rendering token page with status: {token_data.get('status', 'unknown')}")
        return templates.TemplateResponse("token.html", context)
        
    except Exception as e:
        logger.error(f"❌ Error loading token page for {contract_address}: {e}", exc_info=True)
        
        # Create fallback token data so template can still render
        fallback_data = {
            "contract_address": contract_address,
            "network": network,
            "metadata": {
                "symbol": "ERROR", 
                "name": "Error Loading Token",
                "decimals": 18,
                "totalSupply": None,
                "verified": False
            },
            "activity": {
                "wallet_count": 0, 
                "total_purchases": 0, 
                "total_eth_spent": 0.0, 
                "alpha_score": 0.0, 
                "platforms": [], 
                "avg_wallet_score": 0.0
            },
            "sell_pressure": {
                "sell_score": 0.0, 
                "wallet_count": 0, 
                "total_sells": 0, 
                "methods": [], 
                "total_eth_value": 0.0
            },
            "purchases": [],
            "is_base_native": False,
            "last_updated": datetime.now().isoformat(),
            "analysis_timestamp": datetime.now().isoformat(),
            "status": "error",
            "error": str(e)
        }
        
        context.update({
            "contract": contract_address,
            "token": token,
            "network": network,
            "token_data": fallback_data,
            "token_data_json": json.dumps(fallback_data, default=str)
        })
        
        return templates.TemplateResponse("token.html", context)

@router.get("/token/{contract_address}")
async def get_token_details_api(
    contract_address: str,
    network: str = Query("ethereum", description="Network (ethereum or base)"),
    auth: bool = Depends(require_auth) if AUTH_AVAILABLE else None
) -> Dict[str, Any]:
    """API endpoint for token details using your settings"""
    
    if not contract_address:
        raise HTTPException(status_code=400, detail="Contract address is required")
    
    # Validate network
    if network not in ["ethereum", "base"]:
        raise HTTPException(status_code=400, detail="Network must be 'ethereum' or 'base'")
    
    # Validate address
    if not _is_valid_address(contract_address):
        raise HTTPException(status_code=400, detail="Invalid contract address format")
    
    logger.info(f"🔍 API request for token {contract_address} on {network}")
    
    try:
        token_data = await get_token_data_with_settings(contract_address, network)
        return token_data
        
    except Exception as e:
        logger.error(f"❌ API error for token {contract_address}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get token details: {str(e)}")

async def get_token_data_with_settings(contract_address: str, network: str) -> Dict[str, Any]:
    """Get comprehensive token data using your settings configuration"""
    
    logger.info(f"📊 Fetching token data for {contract_address} on {network}")
    
    # Initialize response structure
    response_data = {
        "contract_address": contract_address,
        "network": network,
        "metadata": {
            "symbol": "Loading", 
            "name": "Loading Token", 
            "decimals": 18, 
            "totalSupply": None, 
            "verified": False
        },
        "activity": {
            "wallet_count": 0, 
            "total_purchases": 0, 
            "total_eth_spent": 0.0, 
            "alpha_score": 0.0, 
            "platforms": [], 
            "avg_wallet_score": 0.0
        },
        "sell_pressure": {
            "sell_score": 0.0, 
            "wallet_count": 0, 
            "total_sells": 0, 
            "methods": [], 
            "total_eth_value": 0.0
        },
        "purchases": [],
        "is_base_native": False,
        "last_updated": datetime.now().isoformat(),
        "analysis_timestamp": datetime.now().isoformat(),
        "status": "loading"
    }
    
    try:
        # Validate alchemy config exists
        if not hasattr(alchemy_config, 'api_key') or not alchemy_config.api_key:
            raise Exception("Alchemy API key not configured")
        
        # Get Alchemy URL using your settings
        if network == "ethereum":
            alchemy_url = f"https://eth-mainnet.g.alchemy.com/v2/{alchemy_config.api_key}"
        elif network == "base":
            alchemy_url = f"https://base-mainnet.g.alchemy.com/v2/{alchemy_config.api_key}"
        else:
            raise Exception(f"Unsupported network: {network}")
        
        logger.info(f"🔗 Using Alchemy URL for {network}")
        
        # Get token metadata using direct API call
        metadata = await get_token_metadata_direct(alchemy_url, contract_address)
        response_data["metadata"].update(metadata)
        logger.info(f"✅ Token metadata: {metadata.get('symbol', 'Unknown')} - {metadata.get('name', 'Unknown')}")
        
        # Try to get wallet activity if services are available
        try:
            activity = await get_token_activity_simple(alchemy_url, contract_address, network)
            response_data["activity"].update(activity)
            logger.info(f"✅ Activity analysis: {activity.get('wallet_count', 0)} wallets found")
        except Exception as e:
            logger.warning(f"⚠️ Could not get activity data: {e}")
            response_data["activity"]["platforms"] = ["Analysis Unavailable"]
        
        # Set sell pressure to basic values for now
        response_data["sell_pressure"]["methods"] = ["Standard Transfer"]
        
        # Check if Base native token
        if network == "base":
            base_native_symbols = {
                "AERO", "BALD", "TOSHI", "BRETT", "DEGEN", "HIGHER", 
                "MOCHI", "NORMIE", "SPEC", "WELL", "EXTRA", "SEAM",
                "BASED", "BLUE", "MIGGLES", "KEYCAT", "DOGINME"
            }
            response_data["is_base_native"] = metadata.get("symbol", "").upper() in base_native_symbols
        
        response_data["status"] = "success"
        logger.info(f"✅ Complete token data compiled for {contract_address}")
        return response_data
        
    except Exception as e:
        logger.error(f"❌ Error getting token data: {e}", exc_info=True)
        response_data["status"] = "error"
        response_data["error"] = str(e)
        response_data["metadata"]["symbol"] = "ERROR"
        response_data["metadata"]["name"] = f"Error: {str(e)}"
        return response_data

async def get_token_metadata_direct(alchemy_url: str, contract_address: str) -> Dict[str, Any]:
    """Get token metadata using direct Alchemy API call"""
    try:
        logger.info(f"📊 Making direct metadata request for {contract_address}")
        
        # Set timeout with fallback
        timeout_seconds = getattr(alchemy_config, 'timeout_seconds', 30)
        
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(max_connections=10)
        ) as client:
            
            payload = {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "alchemy_getTokenMetadata",
                "params": [contract_address]
            }
            
            response = await client.post(
                alchemy_url,
                content=orjson.dumps(payload),
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                result = orjson.loads(response.content)
                logger.info(f"📊 Alchemy response received: {bool(result.get('result'))}")
                
                if result.get("result"):
                    metadata = result["result"]
                    
                    # Format the metadata - ensure all required fields exist
                    formatted_metadata = {
                        "name": metadata.get("name") or "Unknown Token",
                        "symbol": metadata.get("symbol") or "UNKNOWN",
                        "decimals": metadata.get("decimals") or 18,
                        "totalSupply": metadata.get("totalSupply"),
                        "logo": metadata.get("logo"),
                        "verified": bool(metadata.get("verified", False))
                    }
                    
                    logger.info(f"✅ Formatted metadata for {formatted_metadata.get('symbol', 'UNKNOWN')}")
                    return formatted_metadata
                else:
                    logger.warning(f"⚠️ No metadata in Alchemy response: {result}")
                    return {
                        "name": "No Metadata Available",
                        "symbol": "NO_META",
                        "decimals": 18,
                        "totalSupply": None,
                        "logo": None,
                        "verified": False,
                        "warning": "No metadata from Alchemy"
                    }
            else:
                logger.error(f"❌ Alchemy HTTP error: {response.status_code} - {response.text}")
                raise Exception(f"Alchemy API error: HTTP {response.status_code}")
                
    except Exception as e:
        logger.error(f"❌ Error getting token metadata: {e}")
        return {
            "name": "Error Loading Token",
            "symbol": "ERROR",
            "decimals": 18,
            "totalSupply": None,
            "logo": None,
            "verified": False,
            "error": str(e)
        }

async def get_token_activity_simple(alchemy_url: str, contract_address: str, network: str) -> Dict[str, Any]:
    """Get basic token activity using direct API calls"""
    try:
        logger.info(f"📈 Getting simple activity data for {contract_address}")
        
        # For now, return basic activity structure
        # You can enhance this later with actual wallet analysis
        activity = {
            "wallet_count": 0,
            "total_purchases": 0,
            "total_eth_spent": 0.0,
            "alpha_score": 0.0,
            "platforms": ["Uniswap", "Direct Transfer"],
            "avg_wallet_score": 0.0
        }
        
        # Try to get recent transfers to see if token is active
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            # Get recent transfers for this token
            payload = {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "alchemy_getAssetTransfers",
                "params": [{
                    "fromBlock": "latest",
                    "toBlock": "latest",
                    "contractAddresses": [contract_address],
                    "category": ["erc20"],
                    "maxCount": "0x5"  # Just 5 transfers to check activity
                }]
            }
            
            response = await client.post(
                alchemy_url,
                content=orjson.dumps(payload),
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                result = orjson.loads(response.content)
                transfers = result.get("result", {}).get("transfers", [])
                
                if transfers:
                    # Get unique wallets safely
                    unique_wallets = set()
                    for t in transfers:
                        if t.get("from"):
                            unique_wallets.add(t["from"])
                        if t.get("to"):
                            unique_wallets.add(t["to"])
                    
                    activity["wallet_count"] = len(unique_wallets)
                    activity["total_purchases"] = len(transfers)
                    activity["alpha_score"] = len(transfers) * 5  # Simple scoring
                    logger.info(f"✅ Found {len(transfers)} recent transfers")
                else:
                    logger.info(f"ℹ️ No recent transfers found")
            else:
                logger.warning(f"⚠️ Asset transfers API returned {response.status_code}")
        
        return activity
        
    except Exception as e:
        logger.warning(f"⚠️ Error getting activity data: {e}")
        return {
            "wallet_count": 0,
            "total_purchases": 0,
            "total_eth_spent": 0.0,
            "alpha_score": 0.0,
            "platforms": ["Unknown"],
            "avg_wallet_score": 0.0,
            "error": str(e)
        }

def _is_valid_address(address: str) -> bool:
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

# Test endpoints to verify everything works
@router.get("/token/test")
async def test_token_endpoint():
    """Test endpoint to verify token routes are working"""
    return {
        "status": "success",
        "message": "Token routes working with your settings",
        "timestamp": datetime.now().isoformat(),
        "alchemy_configured": bool(getattr(alchemy_config, 'api_key', None)),
        "environment": getattr(settings, 'environment', 'unknown')
    }

@router.get("/token/test-settings")
async def test_settings():
    """Test your settings configuration"""
    api_key = getattr(alchemy_config, 'api_key', None)
    return {
        "status": "success",
        "alchemy_key_set": bool(api_key),
        "alchemy_key_length": len(api_key) if api_key else 0,
        "environment": getattr(settings, 'environment', 'unknown'),
        "supported_networks": ["ethereum", "base"],
        "rate_limit": getattr(alchemy_config, 'rate_limit_per_second', 5),
        "timeout": getattr(alchemy_config, 'timeout_seconds', 30)
    }

@router.get("/token/test-metadata/{contract_address}")
async def test_metadata_endpoint(
    contract_address: str, 
    network: str = Query("ethereum", description="Network")
):
    """Test metadata retrieval for a specific token"""
    try:
        # Validate alchemy config exists
        if not hasattr(alchemy_config, 'api_key') or not alchemy_config.api_key:
            raise Exception("Alchemy API key not configured")
        
        # Get Alchemy URL
        if network == "ethereum":
            alchemy_url = f"https://eth-mainnet.g.alchemy.com/v2/{alchemy_config.api_key}"
        elif network == "base":
            alchemy_url = f"https://base-mainnet.g.alchemy.com/v2/{alchemy_config.api_key}"
        else:
            raise Exception(f"Unsupported network: {network}")
        
        # Get metadata
        metadata = await get_token_metadata_direct(alchemy_url, contract_address)
        
        return {
            "status": "success",
            "contract_address": contract_address,
            "network": network,
            "metadata": metadata,
            "alchemy_url_configured": bool(alchemy_url)
        }
        
    except Exception as e:
        return {
            "status": "error",
            "contract_address": contract_address,
            "network": network,
            "error": str(e)
        }