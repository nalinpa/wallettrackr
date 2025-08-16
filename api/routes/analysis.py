from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import Literal, Optional
import asyncio
import time
from datetime import datetime

# Import your existing components (we'll adapt them)
from data_service import AnalysisService
from tracker.buy_tracker import ComprehensiveBuyTracker
from tracker.sell_tracker import ComprehensiveSellTracker
from api.models.responses import BuyAnalysisResponse, SellAnalysisResponse, ProgressUpdate

# Enhanced imports
try:
    from utils.json_utils import orjson_dumps_str, sanitize_for_orjson
    ORJSON_AVAILABLE = True
except ImportError:
    import json
    ORJSON_AVAILABLE = False
    def orjson_dumps_str(obj): return json.dumps(obj, default=str)
    def sanitize_for_orjson(obj): return obj

router = APIRouter(tags=["analysis"])

# Analysis service instance
service = AnalysisService()

@router.get("/{network}/buy", response_model=BuyAnalysisResponse)
async def analyze_buy_transactions(
    network: Literal["ethereum", "base"],
    wallets: int = Query(173, ge=1, le=500, description="Number of wallets to analyze"),
    days: float = Query(1.0, ge=0.1, le=7.0, description="Days back to analyze"),
    enhanced: bool = Query(True, description="Use Web3 enhanced analysis")
):
    """
    Analyze buy transactions for alpha discovery
    
    This endpoint analyzes recent buy transactions from top-performing wallets
    to identify potential alpha opportunities in the crypto market.
    """
    try:
        start_time = time.time()
        
        # Check cache first
        cache_key = f'{network}_buy'
        cached_data = service.get_cached_data(cache_key)
        
        if cached_data:
            # Return cached data with FastAPI model validation
            cached_data['analysis_time_seconds'] = 0.0  # Cached
            return BuyAnalysisResponse(**cached_data)
        
        # Run analysis (currently sync, will make async later)
        tracker = ComprehensiveBuyTracker(network)
        
        if not tracker.test_connection():
            raise HTTPException(status_code=503, detail=f"{network} connection failed")
        
        # Run analysis
        results = tracker.analyze_all_trading_methods(
            num_wallets=wallets,
            days_back=days,
            max_wallets_for_sse=False
        )
        
        if not results or not results.get('ranked_tokens'):
            return BuyAnalysisResponse(
                network=network,
                total_purchases=0,
                unique_tokens=0,
                total_eth_spent=0.0,
                total_usd_spent=0.0,
                top_tokens=[],
                platform_summary={},
                analysis_time_seconds=time.time() - start_time,
                last_updated=datetime.now()
            )
        
        # Format response
        response_data = service.format_buy_response(results, network)
        response_data['analysis_time_seconds'] = time.time() - start_time
        
        # Cache results
        service.cache_data(cache_key, response_data)
        
        return BuyAnalysisResponse(**response_data)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{network}/sell", response_model=SellAnalysisResponse)
async def analyze_sell_pressure(
    network: Literal["ethereum", "base"],
    wallets: int = Query(173, ge=1, le=500, description="Number of wallets to analyze"),
    days: float = Query(1.0, ge=0.1, le=7.0, description="Days back to analyze"),
    enhanced: bool = Query(True, description="Use Web3 enhanced analysis")
):
    """
    Analyze sell pressure for risk assessment
    
    This endpoint analyzes recent sell transactions from top-performing wallets
    to identify potential sell pressure and risk factors.
    """
    try:
        start_time = time.time()
        
        # Check cache first
        cache_key = f'{network}_sell'
        cached_data = service.get_cached_data(cache_key)
        
        if cached_data:
            cached_data['analysis_time_seconds'] = 0.0
            return SellAnalysisResponse(**cached_data)
        
        # Run analysis
        tracker = ComprehensiveSellTracker(network)
        
        if not tracker.test_connection():
            raise HTTPException(status_code=503, detail=f"{network} connection failed")
        
        results = tracker.analyze_all_sell_methods(
            num_wallets=wallets,
            days_back=days,
            max_wallets_for_sse=False
        )
        
        if not results or not results.get('ranked_tokens'):
            return SellAnalysisResponse(
                network=network,
                total_sells=0,
                unique_tokens=0,
                total_estimated_eth=0.0,
                top_tokens=[],
                method_summary={},
                analysis_time_seconds=time.time() - start_time,
                last_updated=datetime.now()
            )
        
        # Format response
        response_data = service.format_sell_response(results, network)
        response_data['analysis_time_seconds'] = time.time() - start_time
        
        # Cache results
        service.cache_data(cache_key, response_data)
        
        return SellAnalysisResponse(**response_data)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{network}/buy/stream")
async def stream_buy_analysis(
    network: Literal["ethereum", "base"],
    wallets: int = Query(173, ge=1, le=500),
    days: float = Query(1.0, ge=0.1, le=7.0)
):
    """
    Stream buy analysis with real-time progress updates
    
    This endpoint provides real-time updates during the analysis process,
    allowing clients to show progress and receive results as they're computed.
    """
    
    async def generate_analysis_stream():
        try:
            # Send start message
            start_msg = ProgressUpdate(
                type="progress",
                processed=0,
                total=wallets,
                percentage=0,
                message=f"Starting {network} buy analysis..."
            )
            yield f"data: {orjson_dumps_str(start_msg.dict())}\n\n"
            
            # TODO: This will be properly async in next phase
            # For now, we'll simulate with the existing sync tracker
            tracker = ComprehensiveBuyTracker(network)
            
            if not tracker.test_connection():
                error_msg = ProgressUpdate(type="error", error=f"{network} connection failed")
                yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
                return
            
            # Run analysis (will be async later)
            start_time = time.time()
            results = tracker.analyze_all_trading_methods(
                num_wallets=wallets,
                days_back=days,
                max_wallets_for_sse=True  # Use SSE mode
            )
            
            # Send progress completion
            complete_msg = ProgressUpdate(
                type="progress",
                processed=wallets,
                total=wallets,
                percentage=100,
                message="Analysis complete, formatting results..."
            )
            yield f"data: {orjson_dumps_str(complete_msg.dict())}\n\n"
            
            # Format and send results
            if results and results.get('ranked_tokens'):
                response_data = service.format_buy_response(results, network)
                response_data['analysis_time_seconds'] = time.time() - start_time
                
                results_msg = ProgressUpdate(
                    type="results",
                    data=sanitize_for_orjson(response_data)
                )
                yield f"data: {orjson_dumps_str(results_msg.dict())}\n\n"
            
            # Send completion
            final_msg = ProgressUpdate(type="complete", message="Analysis complete")
            yield f"data: {orjson_dumps_str(final_msg.dict())}\n\n"
            
        except Exception as e:
            error_msg = ProgressUpdate(type="error", error=str(e))
            yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
    
    return StreamingResponse(
        generate_analysis_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/{network}/sell/stream")
async def stream_sell_analysis(
    network: Literal["ethereum", "base"],
    wallets: int = Query(173, ge=1, le=500),
    days: float = Query(1.0, ge=0.1, le=7.0)
):
    """Stream sell analysis with real-time progress updates"""
    
    async def generate_sell_stream():
        try:
            # Similar to buy stream but for sell analysis
            start_msg = ProgressUpdate(
                type="progress",
                processed=0,
                total=wallets,
                percentage=0,
                message=f"Starting {network} sell pressure analysis..."
            )
            yield f"data: {orjson_dumps_str(start_msg.dict())}\n\n"
            
            tracker = ComprehensiveSellTracker(network)
            
            if not tracker.test_connection():
                error_msg = ProgressUpdate(type="error", error=f"{network} connection failed")
                yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
                return
            
            start_time = time.time()
            results = tracker.analyze_all_sell_methods(
                num_wallets=wallets,
                days_back=days,
                max_wallets_for_sse=True
            )
            
            complete_msg = ProgressUpdate(
                type="progress",
                processed=wallets,
                total=wallets,
                percentage=100,
                message="Sell analysis complete, formatting results..."
            )
            yield f"data: {orjson_dumps_str(complete_msg.dict())}\n\n"
            
            if results and results.get('ranked_tokens'):
                response_data = service.format_sell_response(results, network)
                response_data['analysis_time_seconds'] = time.time() - start_time
                
                results_msg = ProgressUpdate(
                    type="results",
                    data=sanitize_for_orjson(response_data)
                )
                yield f"data: {orjson_dumps_str(results_msg.dict())}\n\n"
            
            final_msg = ProgressUpdate(type="complete", message="Sell analysis complete")
            yield f"data: {orjson_dumps_str(final_msg.dict())}\n\n"
            
        except Exception as e:
            error_msg = ProgressUpdate(type="error", error=str(e))
            yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
    
    return StreamingResponse(
        generate_sell_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )