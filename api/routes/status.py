from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import time
from datetime import datetime

from data_service import AnalysisService
from config.settings import settings, analysis_config, monitor_config

# Clean import - no "async" prefix
from services.service_container import ServiceContainer

router = APIRouter(tags=["status"])

analysis_service = AnalysisService()

@router.get("/status")
async def get_api_status() -> Dict[str, Any]:
    """Get comprehensive API status"""
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
        
        # Get cache status
        cache_status = analysis_service.get_cache_status()
        
        return {
            "status": "online",
            "timestamp": datetime.now().isoformat(),
            "environment": settings.environment,
            "version": "2.0.0",
            "services": service_status,
            "cache": cache_status,
            "config": {
                "supported_networks": [net.value for net in settings.monitor.supported_networks],
                "max_wallets": analysis_config.max_wallet_count,
                "excluded_tokens": len(analysis_config.excluded_tokens),
                "concurrent_processing": True,
                "orjson_enabled": True
            },
            "endpoints": {
                "analysis": [
                    "GET /api/{network}/buy",
                    "GET /api/{network}/sell", 
                    "GET /api/{network}/buy/stream",
                    "GET /api/{network}/sell/stream"
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
async def health_check():
    """Simple health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "concurrent_processing": True
    }

@router.get("/performance")
async def get_performance_metrics():
    """Get performance metrics"""
    try:
        performance_data = {}
        
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
        
        return {
            "timestamp": datetime.now().isoformat(),
            "performance": performance_data,
            "cache_metrics": analysis_service.get_performance_summary()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))