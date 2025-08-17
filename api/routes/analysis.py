from fastapi import APIRouter, Query, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from typing import Literal, Optional, Dict, Any
import asyncio
import time
from datetime import datetime
import logging

from services.service_container import ServiceContainer
from core.analysis.buy_analyzer import BuyAnalyzer
from core.analysis.sell_analyzer import SellAnalyzer

# Import models
from api.models.responses import (
    BuyAnalysisResponse, SellAnalysisResponse, ProgressUpdate,
    TokenAnalysis, Web3EnhancedData
)

# Import utilities
try:
    from utils.json_utils import orjson_dumps_str, sanitize_for_orjson
    ORJSON_AVAILABLE = True
except ImportError:
    import json
    ORJSON_AVAILABLE = False
    def orjson_dumps_str(obj): return json.dumps(obj, default=str)
    def sanitize_for_orjson(obj): return obj

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analysis"])

# Dependencies
def validate_network(network: Literal["ethereum", "base"]) -> str:
    """Validate and return network"""
    return network

def get_analysis_params(
    wallets: int = Query(173, ge=1, le=500, description="Number of top wallets to analyze"),
    days: float = Query(1.0, ge=0.1, le=7.0, description="Days back to analyze"),
    enhanced: bool = Query(True, description="Use Web3 enhanced analysis")
) -> Dict[str, Any]:
    """Get validated analysis parameters"""
    return {
        "wallets": wallets,
        "days": days,
        "enhanced": enhanced
    }

@router.get("/{network}/buy", response_model=BuyAnalysisResponse)
async def analyze_buy_transactions(
    network: str = Depends(validate_network),
    params: Dict[str, Any] = Depends(get_analysis_params)
):
    """Buy transaction analysis with concurrent processing"""
    start_time = time.time()
    
    try:
        logger.info(f"🚀 Starting {network} buy analysis: {params['wallets']} wallets, {params['days']} days")
        
        # Use clean analyzer - no "async" prefix
        async with BuyAnalyzer(network) as analyzer:
            # Test connections
            connections = await analyzer.services.test_connections()
            if not all(connections.values()):
                failed_services = [k for k, v in connections.items() if not v]
                raise HTTPException(
                    status_code=503, 
                    detail=f"Service connections failed: {failed_services}"
                )
            
            # Run analysis
            result = await analyzer.analyze_wallets_concurrent(
                num_wallets=params["wallets"],
                days_back=params["days"]
            )
            
            # Check if analysis returned a valid result
            if result is None:
                logger.warning(f"⚠️ Analysis returned None for {network} - creating empty result")
                # Return empty result instead of error since this is normal when no transactions found
                return BuyAnalysisResponse(
                    network=network,
                    total_purchases=0,
                    unique_tokens=0,
                    total_eth_spent=0.0,
                    total_usd_spent=0.0,
                    top_tokens=[],
                    platform_summary={},
                    web3_enhanced=False,
                    analysis_time_seconds=time.time() - start_time,
                    last_updated=datetime.now(),
                    from_cache=False
                )
            
            if result.total_transactions == 0:
                return BuyAnalysisResponse(
                    network=network,
                    total_purchases=0,
                    unique_tokens=0,
                    total_eth_spent=0.0,
                    total_usd_spent=0.0,
                    top_tokens=[],
                    platform_summary={},
                    analysis_time_seconds=time.time() - start_time,
                    last_updated=datetime.now(),
                    from_cache=False
                )
            
            # Format response data
            response_data = await _format_buy_response(result, network, start_time)
            
            return response_data
            
    except Exception as e:
        logger.error(f"❌ {network} buy analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@router.get("/{network}/sell", response_model=SellAnalysisResponse)
async def analyze_sell_pressure(
    network: str = Depends(validate_network),
    params: Dict[str, Any] = Depends(get_analysis_params)
):
    """Sell pressure analysis with concurrent processing"""
    start_time = time.time()
    
    try:
        logger.info(f"🚀 Starting {network} sell analysis: {params['wallets']} wallets, {params['days']} days")
        
        # Use clean analyzer - no "async" prefix
        async with SellAnalyzer(network) as analyzer:
            # Test connections
            connections = await analyzer.services.test_connections()
            if not all(connections.values()):
                failed_services = [k for k, v in connections.items() if not v]
                raise HTTPException(
                    status_code=503, 
                    detail=f"Service connections failed: {failed_services}"
                )
            
            # Run analysis
            result = await analyzer.analyze_wallets_concurrent(
                num_wallets=params["wallets"],
                days_back=params["days"]
            )
            
            # Check if analysis returned a valid result
            if result is None:
                logger.error(f"❌ Analysis returned None for {network}")
                raise HTTPException(
                    status_code=500, 
                    detail="Analysis failed - no result returned"
                )
            
            if result.total_transactions == 0:
                return SellAnalysisResponse(
                    network=network,
                    total_sells=0,
                    unique_tokens=0,
                    total_estimated_eth=0.0,
                    top_tokens=[],
                    method_summary={},
                    analysis_time_seconds=time.time() - start_time,
                    last_updated=datetime.now(),
                    from_cache=False
                )
            
            # Format response data
            response_data = await _format_sell_response(result, network, start_time)
            
            return response_data
            
    except Exception as e:
        logger.error(f"❌ {network} sell analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@router.get("/{network}/buy/stream")
async def stream_buy_analysis(
    network: str = Depends(validate_network),
    wallets: int = Query(173, ge=1, le=500),
    days: float = Query(1.0, ge=0.1, le=7.0)
):
    """Stream buy analysis with real-time progress updates"""
    
    async def generate_stream():
        try:
            async with BuyAnalyzer(network) as analyzer:
                async for update in analyzer.analyze_with_progress(wallets, days):
                    sanitized_update = sanitize_for_orjson(update)
                    yield f"data: {orjson_dumps_str(sanitized_update)}\n\n"
                    
        except Exception as e:
            error_update = {'type': 'error', 'error': str(e)}
            yield f"data: {orjson_dumps_str(error_update)}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/{network}/sell/stream")
async def stream_sell_analysis(
    network: str = Depends(validate_network),
    wallets: int = Query(173, ge=1, le=500),
    days: float = Query(1.0, ge=0.1, le=7.0)
):
    """Stream sell analysis with real-time progress updates"""
    
    async def generate_stream():
        try:
            async with SellAnalyzer(network) as analyzer:
                async for update in analyzer.analyze_with_progress(wallets, days):
                    sanitized_update = sanitize_for_orjson(update)
                    yield f"data: {orjson_dumps_str(sanitized_update)}\n\n"
                    
        except Exception as e:
            error_update = {'type': 'error', 'error': str(e)}
            yield f"data: {orjson_dumps_str(error_update)}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# Helper functions for response formatting
async def _format_buy_response(result, network: str, start_time: float) -> BuyAnalysisResponse:
    """Format buy analysis result into response model"""
    # Extract top tokens
    top_tokens = []
    for i, (token, data, score) in enumerate(result.ranked_tokens[:10], 1):
        token_analysis = TokenAnalysis(
            rank=i,
            token=token,
            alpha_score=score,
            wallet_count=len(data.get('wallets', [])),
            total_eth_spent=data.get('total_eth_spent', 0),
            platforms=list(data.get('platforms', [])),
            contract_address=data.get('contract_address', ''),
            avg_wallet_score=data.get('avg_wallet_score', 0),
            sophistication_score=data.get('avg_sophistication', None),
            is_base_native=data.get('is_base_native', False)
        )
        top_tokens.append(token_analysis)
    
    return BuyAnalysisResponse(
        network=network,
        total_purchases=result.total_transactions,
        unique_tokens=result.unique_tokens,
        total_eth_spent=result.total_eth_value,
        total_usd_spent=result.total_eth_value * 2000,  # Rough estimate
        top_tokens=top_tokens,
        platform_summary=result.performance_metrics.get('platform_summary', {}),
        web3_enhanced=result.web3_enhanced,
        analysis_time_seconds=time.time() - start_time,
        last_updated=datetime.now(),
        from_cache=False
    )

async def _format_sell_response(result, network: str, start_time: float) -> SellAnalysisResponse:
    """Format sell analysis result into response model"""
    # Extract top tokens
    top_tokens = []
    for i, (token, data, score) in enumerate(result.ranked_tokens[:10], 1):
        token_analysis = TokenAnalysis(
            rank=i,
            token=token,
            alpha_score=score,  # Using alpha_score field for sell_score
            wallet_count=len(data.get('wallets', [])),
            total_eth_spent=data.get('total_estimated_eth', 0),
            platforms=list(data.get('platforms', [])),
            contract_address=data.get('contract_address', ''),
            avg_wallet_score=data.get('avg_wallet_score', 0),
            sophistication_score=data.get('avg_sophistication', None),
            is_base_native=data.get('is_base_native', False)
        )
        top_tokens.append(token_analysis)
    
    return SellAnalysisResponse(
        network=network,
        total_sells=result.total_transactions,
        unique_tokens=result.unique_tokens,
        total_estimated_eth=result.total_eth_value,
        top_tokens=top_tokens,
        method_summary=result.performance_metrics.get('method_summary', {}),
        web3_enhanced=result.web3_enhanced,
        analysis_time_seconds=time.time() - start_time,
        last_updated=datetime.now(),
        from_cache=False
    )