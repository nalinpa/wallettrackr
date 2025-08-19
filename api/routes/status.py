from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
import time
from datetime import datetime

# Import FastAPI cache service instead of data_service
from services.cache.cache_service import get_cache_service, FastAPICacheService
from config.settings import settings, analysis_config, monitor_config

# Import service container for testing
from services.service_container import ServiceContainer

router = APIRouter(tags=["status"])

@router.get("/status")
async def get_api_status(
    cache_service: FastAPICacheService = Depends(get_cache_service)
) -> Dict[str, Any]:
    """Get comprehensive API status with FastAPI cache service"""
    try:
        # Test services for all networks
        service_status = {}
        for network in ["ethereum", "base"]:
            try:
                async with ServiceContainer(network) as services:
                    connections = await services.test_connections()
                    service_status[network] = connections
            except Exception as e:
                service_status[network] = {"error": str(e)}
        
        # Get cache status from FastAPI cache service
        cache_status = await cache_service.get_status()
        cache_performance = await cache_service.get_performance_summary()
        
        return {
            "status": "online",
            "timestamp": datetime.now().isoformat(),
            "environment": settings.environment,
            "version": "2.0.0",
            "services": service_status,
            "cache": {
                "status": cache_status,
                "performance": cache_performance,
                "orjson_enabled": cache_status.get("orjson_available", False),
                "entries": cache_status.get("cache_entries", 0),
                "hit_rate": f"{cache_performance.get('hit_rate_percentage', 0):.1f}%"
            },
            "config": {
                "supported_networks": [net.value for net in settings.monitor.supported_networks],
                "max_wallets": getattr(analysis_config, 'max_wallet_count', 500),
                "excluded_tokens": len(getattr(analysis_config, 'excluded_tokens', [])),
                "concurrent_processing": True,
                "fastapi_native": True
            },
            "endpoints": {
                "analysis": [
                    "GET /api/{network}/buy",
                    "GET /api/{network}/sell", 
                    "GET /api/{network}/buy/stream",
                    "GET /api/{network}/sell/stream"
                ],
                "cache": [
                    "GET /api/cache/status",
                    "GET /api/cache/performance",
                    "DELETE /api/cache",
                    "POST /api/cache/warm"
                ],
                "status": [
                    "GET /api/status",
                    "GET /api/health",
                    "GET /api/performance"
                ]
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check(
    cache_service: FastAPICacheService = Depends(get_cache_service)
):
    """Simple health check with cache info"""
    try:
        cache_status = await cache_service.get_status()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "fastapi_native": True,
            "cache": {
                "enabled": True,
                "entries": cache_status.get("cache_entries", 0),
                "orjson": cache_status.get("orjson_available", False)
            }
        }
    except Exception as e:
        # Return basic health if cache fails
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "fastapi_native": True,
            "cache": {
                "enabled": False,
                "error": str(e)
            }
        }

@router.get("/performance")
async def get_performance_metrics(
    cache_service: FastAPICacheService = Depends(get_cache_service)
):
    """Get performance metrics using FastAPI cache service"""
    try:
        performance_data = {}
        
        # Test each network performance
        for network in ["ethereum", "base"]:
            start_time = time.time()
            
            try:
                async with ServiceContainer(network) as services:
                    # Test database speed
                    db_start = time.time()
                    wallets = await services.database.get_top_wallets(network, 5)
                    db_time = time.time() - db_start
                    
                    # Test alchemy speed
                    alchemy_start = time.time()
                    await services.alchemy.get_block_number()
                    alchemy_time = time.time() - alchemy_start
                    
                    performance_data[network] = {
                        "total_init_time": time.time() - start_time,
                        "database_query_time": db_time,
                        "alchemy_request_time": alchemy_time,
                        "wallets_available": len(wallets),
                        "status": "healthy"
                    }
                    
            except Exception as e:
                performance_data[network] = {
                    "status": "error",
                    "error": str(e)
                }
        
        # Get cache performance metrics
        cache_performance = await cache_service.get_performance_summary()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "performance": performance_data,
            "cache_metrics": cache_performance,
            "fastapi_native": True
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cache-summary") 
async def get_cache_summary(
    cache_service: FastAPICacheService = Depends(get_cache_service)
):
    """Get cache summary information"""
    try:
        status = await cache_service.get_status()
        performance = await cache_service.get_performance_summary()
        
        return {
            "status": "success",
            "summary": {
                "total_entries": status.get("cache_entries", 0),
                "hit_rate": f"{performance.get('hit_rate_percentage', 0):.1f}%",
                "total_requests": performance.get("total_requests", 0),
                "cache_size_mb": performance.get("cache_size_mb", 0),
                "orjson_enabled": status.get("orjson_available", False),
                "networks": status.get("network_breakdown", {}),
                "analysis_types": status.get("type_breakdown", {})
            },
            "config": status.get("config", {}),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/system-info")
async def get_system_info():
    """Get system information"""
    try:
        import sys
        import platform
        from pathlib import Path
        
        # Check if orjson is available
        try:
            import orjson
            orjson_version = getattr(orjson, '__version__', 'unknown')
            orjson_available = True
        except ImportError:
            orjson_version = None
            orjson_available = False
        
        # Check cache directory
        cache_dir = Path("cache")
        cache_exists = cache_dir.exists()
        cache_files = len(list(cache_dir.glob("*.json"))) if cache_exists else 0
        
        return {
            "system": {
                "platform": platform.platform(),
                "python_version": sys.version,
                "architecture": platform.architecture()[0]
            },
            "dependencies": {
                "orjson": {
                    "available": orjson_available,
                    "version": orjson_version
                },
                "fastapi": "2.0.0",  # Your version
                "pydantic": "2.x"     # Your version
            },
            "cache_directory": {
                "exists": cache_exists,
                "path": str(cache_dir.absolute()),
                "files": cache_files
            },
            "environment": settings.environment,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))