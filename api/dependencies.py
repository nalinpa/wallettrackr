# api/dependencies.py - Complete FastAPI dependencies for analysis

from fastapi import Depends, HTTPException, BackgroundTasks, Query
from typing import Dict, Any, Optional, List, Literal
import time
import logging
from datetime import datetime

from services.cache.cache_service import get_cache_service, FastAPICacheService
from core.analysis.buy_analyzer import BuyAnalyzer
from core.analysis.sell_analyzer import SellAnalyzer
from config.settings import settings

logger = logging.getLogger(__name__)

# Network validation
def validate_network(network: Literal["ethereum", "base"]) -> str:
    """Validate network parameter"""
    supported = [net.value for net in settings.monitor.supported_networks]
    if network not in supported:
        raise HTTPException(
            status_code=400, 
            detail=f"Network '{network}' not supported. Supported: {supported}"
        )
    return network

# Analysis parameters
class AnalysisParams:
    """Analysis parameters with validation"""
    def __init__(
        self,
        wallets: int = Query(173, ge=1, le=500, description="Number of wallets to analyze"),
        days: float = Query(1.0, ge=0.1, le=7.0, description="Days back to analyze"),
        use_cache: bool = Query(True, description="Use cached results if available"),
        cache_ttl: int = Query(3600, ge=300, le=86400, description="Cache TTL in seconds")
    ):
        self.wallets = wallets
        self.days = days
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl

# Response formatters
class ResponseFormatter:
    """Format analysis results for API responses"""
    
    @staticmethod
    def format_buy_response(result, network: str, analysis_time: float, from_cache: bool = False) -> Dict[str, Any]:
        """Format buy analysis response"""
        if not result or result.total_transactions == 0:
            return {
                "status": "success",
                "network": network,
                "analysis_type": "buy",
                "total_purchases": 0,
                "unique_tokens": 0,
                "total_eth_spent": 0.0,
                "total_usd_spent": 0.0,
                "top_tokens": [],
                "platform_summary": {},
                "web3_enhanced": False,
                "orjson_enabled": True,
                "analysis_time_seconds": analysis_time,
                "last_updated": datetime.now(),
                "from_cache": from_cache
            }
        
        # Format top tokens
        top_tokens = []
        for i, (token, data, score) in enumerate(result.ranked_tokens[:20], 1):
            top_tokens.append({
                "rank": i,
                "token": token,
                "alpha_score": round(float(score), 2),
                "wallet_count": len(data.get('wallets', [])),
                "total_eth_spent": round(float(data.get('total_eth_spent', 0)), 4),
                "platforms": list(data.get('platforms', [])),
                "contract_address": data.get('contract_address', ''),
                "avg_wallet_score": round(float(data.get('avg_wallet_score', 0)), 2),
                "sophistication_score": data.get('avg_sophistication'),
                "is_base_native": data.get('is_base_native', False) if network == 'base' else None
            })
        
        return {
            "status": "success",
            "network": network,
            "analysis_type": "buy",
            "total_purchases": result.total_transactions,
            "unique_tokens": result.unique_tokens,
            "total_eth_spent": round(float(result.total_eth_value), 4),
            "total_usd_spent": round(float(result.total_eth_value * 2500), 0),  # Rough estimate
            "top_tokens": top_tokens,
            "platform_summary": result.performance_metrics.get('platform_summary', {}),
            "web3_enhanced": result.web3_enhanced,
            "orjson_enabled": True,
            "analysis_time_seconds": analysis_time,
            "last_updated": datetime.now(),
            "from_cache": from_cache
        }
    
    @staticmethod
    def format_sell_response(result, network: str, analysis_time: float, from_cache: bool = False) -> Dict[str, Any]:
        """Format sell analysis response"""
        if not result or result.total_transactions == 0:
            return {
                "status": "success",
                "network": network,
                "analysis_type": "sell",
                "total_sells": 0,
                "unique_tokens": 0,
                "total_estimated_eth": 0.0,
                "top_tokens": [],
                "method_summary": {},
                "web3_enhanced": False,
                "orjson_enabled": True,
                "analysis_time_seconds": analysis_time,
                "last_updated": datetime.now(),
                "from_cache": from_cache
            }
        
        # Format top tokens
        top_tokens = []
        for i, (token, data, score) in enumerate(result.ranked_tokens[:20], 1):
            top_tokens.append({
                "rank": i,
                "token": token,
                "sell_score": round(float(score), 2),
                "wallet_count": len(data.get('wallets', [])),
                "total_estimated_eth": round(float(data.get('total_estimated_eth', 0)), 4),
                "methods": list(data.get('platforms', [])),  # Using platforms as methods
                "contract_address": data.get('contract_address', ''),
                "avg_wallet_score": round(float(data.get('avg_wallet_score', 0)), 2),
                "sophistication_score": data.get('avg_sophistication'),
                "is_base_native": data.get('is_base_native', False) if network == 'base' else None
            })
        
        return {
            "status": "success",
            "network": network,
            "analysis_type": "sell",
            "total_sells": result.total_transactions,
            "unique_tokens": result.unique_tokens,
            "total_estimated_eth": round(float(result.total_eth_value), 4),
            "top_tokens": top_tokens,
            "method_summary": result.performance_metrics.get('method_summary', {}),
            "web3_enhanced": result.web3_enhanced,
            "orjson_enabled": True,
            "analysis_time_seconds": analysis_time,
            "last_updated": datetime.now(),
            "from_cache": from_cache
        }

# Cache-aware analysis functions
async def get_buy_analysis(
    network: str = Depends(validate_network),
    params: AnalysisParams = Depends(),
    cache_service: FastAPICacheService = Depends(get_cache_service),
    background_tasks: BackgroundTasks = None
) -> Dict[str, Any]:
    """Get buy analysis with caching"""
    
    # Generate cache key
    cache_key = f"buy_{network}_{params.wallets}_{params.days}"
    
    # Try cache first
    if params.use_cache:
        cached_result = await cache_service.get(cache_key)
        if cached_result:
            logger.info(f"📋 Returning cached buy analysis for {network}")
            cached_result["from_cache"] = True
            return cached_result
    
    # Run fresh analysis
    start_time = time.time()
    logger.info(f"🚀 Running fresh buy analysis: {network}, {params.wallets} wallets, {params.days} days")
    
    try:
        async with BuyAnalyzer(network) as analyzer:
            result = await analyzer.analyze_wallets_concurrent(params.wallets, params.days)
            analysis_time = time.time() - start_time
            
            # Format response
            response = ResponseFormatter.format_buy_response(result, network, analysis_time, False)
            
            # Cache the result in background
            if background_tasks and params.use_cache:
                background_tasks.add_task(
                    cache_service.set,
                    cache_key, response, params.cache_ttl, network, "buy"
                )
            
            logger.info(f"✅ Buy analysis completed for {network} in {analysis_time:.2f}s")
            return response
            
    except Exception as e:
        logger.error(f"❌ Buy analysis failed for {network}: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

async def get_sell_analysis(
    network: str = Depends(validate_network),
    params: AnalysisParams = Depends(),
    cache_service: FastAPICacheService = Depends(get_cache_service),
    background_tasks: BackgroundTasks = None
) -> Dict[str, Any]:
    """Get sell analysis with caching"""
    
    # Generate cache key
    cache_key = f"sell_{network}_{params.wallets}_{params.days}"
    
    # Try cache first
    if params.use_cache:
        cached_result = await cache_service.get(cache_key)
        if cached_result:
            logger.info(f"📋 Returning cached sell analysis for {network}")
            cached_result["from_cache"] = True
            return cached_result
    
    # Run fresh analysis
    start_time = time.time()
    logger.info(f"🚀 Running fresh sell analysis: {network}, {params.wallets} wallets, {params.days} days")
    
    try:
        async with SellAnalyzer(network) as analyzer:
            result = await analyzer.analyze_wallets_concurrent(params.wallets, params.days)
            analysis_time = time.time() - start_time
            
            # Format response
            response = ResponseFormatter.format_sell_response(result, network, analysis_time, False)
            
            # Cache the result in background
            if background_tasks and params.use_cache:
                background_tasks.add_task(
                    cache_service.set,
                    cache_key, response, params.cache_ttl, network, "sell"
                )
            
            logger.info(f"✅ Sell analysis completed for {network} in {analysis_time:.2f}s")
            return response
            
    except Exception as e:
        logger.error(f"❌ Sell analysis failed for {network}: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# Cache management dependencies
async def get_cache_status(
    cache_service: FastAPICacheService = Depends(get_cache_service)
) -> Dict[str, Any]:
    """Get cache status"""
    try:
        return await cache_service.get_status()
    except Exception as e:
        logger.error(f"❌ Error getting cache status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def clear_cache(
    pattern: Optional[str] = Query(None, description="Pattern to match for clearing"),
    cache_service: FastAPICacheService = Depends(get_cache_service)
) -> Dict[str, Any]:
    """Clear cache entries"""
    try:
        cleared_count = await cache_service.clear(pattern)
        return {
            "status": "success",
            "cleared_entries": cleared_count,
            "pattern": pattern or "all"
        }
    except Exception as e:
        logger.error(f"❌ Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def warm_cache(
    networks: List[str] = Query(["ethereum", "base"]),
    wallets: int = Query(173, ge=1, le=500),
    days: float = Query(1.0, ge=0.1, le=7.0),
    background_tasks: BackgroundTasks = None,
    cache_service: FastAPICacheService = Depends(get_cache_service)
) -> Dict[str, Any]:
    """Warm cache for specified networks"""
    try:
        if background_tasks:
            # Import the warming function
            from services.cache.cache_service import warm_cache_background
            
            background_tasks.add_task(
                warm_cache_background, cache_service, networks, wallets, days
            )
            
            return {
                "status": "success",
                "message": f"Cache warming started for {networks}",
                "networks": networks,
                "wallets": wallets,
                "days": days
            }
        else:
            return {
                "status": "error",
                "message": "Background tasks not available"
            }
    except Exception as e:
        logger.error(f"❌ Error starting cache warming: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Service health check dependency
async def check_services_health(
    network: str = Depends(validate_network)
) -> Dict[str, bool]:
    """Check health of all services for a network"""
    try:
        from services.service_container import ServiceContainer
        
        async with ServiceContainer(network) as services:
            connections = await services.test_connections()
            return connections
    except Exception as e:
        logger.error(f"❌ Health check failed for {network}: {e}")
        return {"error": True, "details": str(e)}

# Token validation dependency  
def validate_contract_address(contract_address: str) -> str:
    """Validate Ethereum contract address format"""
    if not contract_address:
        raise HTTPException(status_code=400, detail="Contract address is required")
    
    # Remove 0x prefix if present
    addr = contract_address.lower()
    if addr.startswith('0x'):
        addr = addr[2:]
    
    # Check length (40 hex characters)
    if len(addr) != 40:
        raise HTTPException(status_code=400, detail="Invalid address length")
    
    # Check if all characters are hex
    try:
        int(addr, 16)
        return contract_address.lower()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid address format")

# Rate limiting dependency (simple implementation)
class RateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}
    
    async def check_rate_limit(self, client_id: str = "default") -> bool:
        """Check if request is within rate limits"""
        now = time.time()
        
        # Clean old requests
        if client_id in self.requests:
            self.requests[client_id] = [
                req_time for req_time in self.requests[client_id]
                if now - req_time < self.window_seconds
            ]
        else:
            self.requests[client_id] = []
        
        # Check limit
        if len(self.requests[client_id]) >= self.max_requests:
            raise HTTPException(
                status_code=429, 
                detail=f"Rate limit exceeded: {self.max_requests} requests per {self.window_seconds} seconds"
            )
        
        # Add current request
        self.requests[client_id].append(now)
        return True

# Global rate limiter instance
rate_limiter = RateLimiter(max_requests=100, window_seconds=60)

async def check_rate_limit(client_ip: str = "127.0.0.1") -> bool:
    """Rate limiting dependency"""
    return await rate_limiter.check_rate_limit(client_ip)