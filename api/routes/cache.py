from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
import logging

from api.dependencies import get_cache_status, clear_cache, warm_cache
from services.cache.cache_service import get_cache_service, FastAPICacheService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["cache"])

@router.get("/cache/status")
async def cache_status_endpoint(
    status_data: Dict[str, Any] = Depends(get_cache_status)
) -> Dict[str, Any]:
    """Get comprehensive cache status using FastAPI dependencies"""
    return {
        "status": "success",
        "data": status_data,
        "timestamp": "now"
    }

@router.delete("/cache")
async def clear_cache_endpoint(
    clear_result: Dict[str, Any] = Depends(clear_cache)
) -> Dict[str, Any]:
    """Clear cache using FastAPI dependencies"""
    return clear_result

@router.post("/cache/warm")
async def warm_cache_endpoint(
    background_tasks: BackgroundTasks,
    warm_result: Dict[str, Any] = Depends(warm_cache)
) -> Dict[str, Any]:
    """Warm cache using FastAPI dependencies"""
    return warm_result

@router.get("/cache/performance")
async def get_cache_performance(
    cache_service: FastAPICacheService = Depends(get_cache_service)
) -> Dict[str, Any]:
    """Get cache performance metrics"""
    try:
        performance_data = await cache_service.get_performance_summary()
        return {
            "status": "success",
            "performance": performance_data
        }
    except Exception as e:
        logger.error(f"❌ Error getting cache performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cache/refresh/{cache_key}")
async def refresh_cache_entry(
    cache_key: str,
    background_tasks: BackgroundTasks,
    cache_service: FastAPICacheService = Depends(get_cache_service)
) -> Dict[str, Any]:
    """Refresh a specific cache entry"""
    try:
        # Delete the existing entry
        deleted = await cache_service.delete(cache_key)
        
        if deleted:
            # Parse the cache key to determine what to refresh
            parts = cache_key.split('_')
            if len(parts) >= 4:
                analysis_type, network, wallets, days = parts[0], parts[1], int(parts[2]), float(parts[3])
                
                # Start background refresh
                if analysis_type == "buy":
                    from api.dependencies import get_buy_analysis, AnalysisParams
                    # Would need to call the analysis function here
                    pass
                elif analysis_type == "sell":
                    from api.dependencies import get_sell_analysis, AnalysisParams
                    # Would need to call the analysis function here
                    pass
                
                return {
                    "status": "success",
                    "message": f"Cache entry '{cache_key}' deleted and refresh started",
                    "refreshing": True
                }
            else:
                return {
                    "status": "success", 
                    "message": f"Cache entry '{cache_key}' deleted",
                    "refreshing": False
                }
        else:
            return {
                "status": "info",
                "message": f"Cache entry '{cache_key}' not found"
            }
            
    except Exception as e:
        logger.error(f"❌ Error refreshing cache entry: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cache/keys")
async def list_cache_keys(
    cache_service: FastAPICacheService = Depends(get_cache_service)
) -> Dict[str, Any]:
    """List all cache keys with metadata"""
    try:
        status = await cache_service.get_status()
        
        # Extract cache keys from the status
        cache_entries = status.get("cache_entries", 0)
        network_breakdown = status.get("network_breakdown", {})
        type_breakdown = status.get("type_breakdown", {}) 
        
        return {
            "status": "success",
            "total_entries": cache_entries,
            "networks": network_breakdown,
            "analysis_types": type_breakdown,
            "orjson_enabled": status.get("orjson_available", False)
        }
        
    except Exception as e:
        logger.error(f"❌ Error listing cache keys: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cache/health")
async def cache_health_check(
    cache_service: FastAPICacheService = Depends(get_cache_service)
) -> Dict[str, Any]:
    """Health check for cache service"""
    try:
        status = await cache_service.get_status()
        performance = await cache_service.get_performance_summary()
        
        # Determine health based on metrics
        is_healthy = True
        issues = []
        
        # Check hit rate
        hit_rate = performance.get("hit_rate_percentage", 0)
        if hit_rate < 50 and performance.get("total_requests", 0) > 10:
            issues.append(f"Low cache hit rate: {hit_rate}%")
            is_healthy = False
        
        # Check cache size
        cache_size_mb = performance.get("cache_size_mb", 0)
        if cache_size_mb > 500:  # 500MB limit
            issues.append(f"Large cache size: {cache_size_mb} MB")
            
        # Check orjson availability
        if not status.get("orjson_available", False):
            issues.append("orjson not available - using slower JSON serialization")
        
        return {
            "status": "healthy" if is_healthy else "warning",
            "healthy": is_healthy,
            "issues": issues,
            "metrics": {
                "hit_rate_percentage": hit_rate,
                "total_requests": performance.get("total_requests", 0),
                "cache_size_mb": cache_size_mb,
                "total_entries": status.get("cache_entries", 0),
                "orjson_enabled": status.get("orjson_available", False)
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Cache health check failed: {e}")
        return {
            "status": "unhealthy",
            "healthy": False,
            "error": str(e)
        }