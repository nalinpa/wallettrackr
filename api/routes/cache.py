from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any

from data_service import AnalysisService

router = APIRouter(tags=["cache"])

# Service instance
analysis_service = AnalysisService()

@router.get("/cache/status")
async def get_cache_status() -> Dict[str, Any]:
    """Get detailed cache status"""
    try:
        status = analysis_service.get_cache_status()
        metrics = analysis_service.get_cache_metrics()
        
        return {
            "cache_status": status,
            "cache_metrics": metrics,
            "performance_summary": analysis_service.get_performance_summary()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/cache")
async def clear_cache(
    networks: Optional[List[str]] = Query(None, description="Networks to clear (all if not specified)")
):
    """Clear cache for specified networks or all"""
    try:
        result = analysis_service.clear_cache(networks)
        return {
            "status": "success",
            "message": f"Cache cleared for: {networks or 'all networks'}",
            "details": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cache/warm")
async def warm_cache(
    networks: List[str] = Query(["ethereum", "base"]),
    wallets: int = Query(173, ge=1, le=500),
    days: float = Query(1.0, ge=0.1, le=7.0)
):
    """Warm cache by running analysis for specified networks"""
    try:
        from services.async_services.service_container import AsyncServiceContainer
        from core.analysis.async_buy_analyzer import AsyncBuyAnalyzer
        
        results = {}
        
        for network in networks:
            try:
                async with AsyncBuyAnalyzer(network) as analyzer:
                    result = await analyzer.analyze_wallets_concurrent(wallets, days)
                    
                    # Cache the result
                    cache_key = f'{network}_buy'
                    formatted_result = {
                        'network': network,
                        'total_purchases': result.total_transactions,
                        'unique_tokens': result.unique_tokens,
                        'total_eth_spent': result.total_eth_value,
                        'analysis_time_seconds': result.performance_metrics.get('analysis_time_seconds', 0)
                    }
                    
                    analysis_service.cache_data(cache_key, formatted_result)
                    results[network] = "warmed"
                    
            except Exception as e:
                results[network] = f"error: {str(e)}"
        
        return {
            "status": "success",
            "message": "Cache warming completed",
            "results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))