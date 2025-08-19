from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import Dict, Any
import logging
from datetime import datetime

# Import FastAPI dependencies instead of data_service
from api.dependencies import (
    get_buy_analysis,
    get_sell_analysis,
    AnalysisParams,
    validate_network,
    ResponseFormatter
)
from api.models.responses import BuyAnalysisResponse, SellAnalysisResponse
from services.cache.cache_service import get_cache_service, FastAPICacheService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analysis"])

@router.get("/{network}/buy", response_model=BuyAnalysisResponse)
async def analyze_buy_transactions(
    background_tasks: BackgroundTasks,
    analysis_result: Dict[str, Any] = Depends(get_buy_analysis)
):
    """Buy transaction analysis with FastAPI dependencies"""
    logger.info(f"📊 Buy analysis endpoint called")
    return analysis_result

@router.get("/{network}/sell", response_model=SellAnalysisResponse)
async def analyze_sell_pressure(
    background_tasks: BackgroundTasks,
    analysis_result: Dict[str, Any] = Depends(get_sell_analysis)
):
    """Sell pressure analysis with FastAPI dependencies"""
    logger.info(f"📊 Sell analysis endpoint called")
    return analysis_result

@router.get("/{network}/buy/stream")
async def stream_buy_analysis(
    network: str = Depends(validate_network),
    params: AnalysisParams = Depends(),
    cache_service: FastAPICacheService = Depends(get_cache_service)
):
    """Stream buy analysis with real-time updates"""
    
    async def generate_stream():
        try:
            import asyncio
            import time
            from core.analysis.buy_analyzer import BuyAnalyzer
            from utils.json_utils import orjson_dumps_str
            from api.models.responses import ProgressUpdate
            
            # Send start message
            start_msg = ProgressUpdate(
                type="progress",
                processed=0,
                total=params.wallets,
                percentage=0,
                message=f"Starting {network} buy analysis..."
            )
            yield f"data: {orjson_dumps_str(start_msg.dict())}\n\n"
            
            # Check cache first if enabled
            if params.use_cache:
                cache_key = f"buy_{network}_{params.wallets}_{params.days}"
                cached_result = await cache_service.get(cache_key)
                if cached_result:
                    logger.info(f"📋 Streaming cached result for {network}")
                    
                    cache_msg = ProgressUpdate(
                        type="progress",
                        processed=params.wallets,
                        total=params.wallets,
                        percentage=100,
                        message="Found cached results, streaming data..."
                    )
                    yield f"data: {orjson_dumps_str(cache_msg.dict())}\n\n"
                    
                    cached_result["from_cache"] = True
                    results_msg = ProgressUpdate(type="results", data=cached_result)
                    yield f"data: {orjson_dumps_str(results_msg.dict())}\n\n"
                    
                    final_msg = ProgressUpdate(type="complete", message="Cached analysis complete")
                    yield f"data: {orjson_dumps_str(final_msg.dict())}\n\n"
                    return
            
            # Run fresh analysis with progress updates
            start_time = time.time()
            
            # Initialize analyzer
            progress_msg = ProgressUpdate(
                type="progress",
                processed=5,
                total=params.wallets,
                percentage=5,
                message=f"Initializing {network} analyzer..."
            )
            yield f"data: {orjson_dumps_str(progress_msg.dict())}\n\n"
            
            async with BuyAnalyzer(network) as analyzer:
                # Test connections
                connections_msg = ProgressUpdate(
                    type="progress",
                    processed=10,
                    total=params.wallets,
                    percentage=10,
                    message="Testing blockchain connections..."
                )
                yield f"data: {orjson_dumps_str(connections_msg.dict())}\n\n"
                
                connections = await analyzer.services.test_connections()
                if not all(connections.values()):
                    failed_services = [k for k, v in connections.items() if not v]
                    error_msg = ProgressUpdate(
                        type="error", 
                        error=f"Service connections failed: {failed_services}"
                    )
                    yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
                    return
                
                # Start main analysis
                analysis_msg = ProgressUpdate(
                    type="progress",
                    processed=20,
                    total=params.wallets,
                    percentage=20,
                    message=f"Analyzing {params.wallets} wallets over {params.days} days..."
                )
                yield f"data: {orjson_dumps_str(analysis_msg.dict())}\n\n"
                
                # Run analysis
                result = await analyzer.analyze_wallets_concurrent(params.wallets, params.days)
                analysis_time = time.time() - start_time
                
                # Format and send results
                if result and result.total_transactions > 0:
                    response = ResponseFormatter.format_buy_response(result, network, analysis_time, False)
                    
                    # Cache the result in background
                    if params.use_cache:
                        cache_key = f"buy_{network}_{params.wallets}_{params.days}"
                        asyncio.create_task(
                            cache_service.set(cache_key, response, params.cache_ttl, network, "buy")
                        )
                    
                    results_msg = ProgressUpdate(type="results", data=response)
                    yield f"data: {orjson_dumps_str(results_msg.dict())}\n\n"
                    
                else:
                    # No results found
                    no_results = ResponseFormatter.format_buy_response(None, network, analysis_time, False)
                    results_msg = ProgressUpdate(type="results", data=no_results)
                    yield f"data: {orjson_dumps_str(results_msg.dict())}\n\n"
                
                # Send completion
                final_msg = ProgressUpdate(type="complete", message="Analysis complete")
                yield f"data: {orjson_dumps_str(final_msg.dict())}\n\n"
                
        except Exception as e:
            logger.error(f"❌ Stream analysis failed: {e}")
            error_msg = ProgressUpdate(type="error", error=f"Analysis failed: {str(e)}")
            yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
    
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
    params: AnalysisParams = Depends(),
    cache_service: FastAPICacheService = Depends(get_cache_service)
):
    """Stream sell analysis with real-time updates"""
    
    async def generate_stream():
        try:
            import asyncio
            import time
            from core.analysis.sell_analyzer import SellAnalyzer
            from utils.json_utils import orjson_dumps_str
            from api.models.responses import ProgressUpdate
            
            # Send start message
            start_msg = ProgressUpdate(
                type="progress",
                processed=0,
                total=params.wallets,
                percentage=0,
                message=f"Starting {network} sell analysis..."
            )
            yield f"data: {orjson_dumps_str(start_msg.dict())}\n\n"
            
            # Check cache first if enabled
            if params.use_cache:
                cache_key = f"sell_{network}_{params.wallets}_{params.days}"
                cached_result = await cache_service.get(cache_key)
                if cached_result:
                    logger.info(f"📋 Streaming cached sell result for {network}")
                    
                    cache_msg = ProgressUpdate(
                        type="progress",
                        processed=params.wallets,
                        total=params.wallets,
                        percentage=100,
                        message="Found cached sell analysis, streaming data..."
                    )
                    yield f"data: {orjson_dumps_str(cache_msg.dict())}\n\n"
                    
                    cached_result["from_cache"] = True
                    results_msg = ProgressUpdate(type="results", data=cached_result)
                    yield f"data: {orjson_dumps_str(results_msg.dict())}\n\n"
                    
                    final_msg = ProgressUpdate(type="complete", message="Cached sell analysis complete")
                    yield f"data: {orjson_dumps_str(final_msg.dict())}\n\n"
                    return
            
            # Run fresh analysis
            start_time = time.time()
            
            # Initialize analyzer
            progress_msg = ProgressUpdate(
                type="progress",
                processed=5,
                total=params.wallets,
                percentage=5,
                message=f"Initializing {network} sell analyzer..."
            )
            yield f"data: {orjson_dumps_str(progress_msg.dict())}\n\n"
            
            async with SellAnalyzer(network) as analyzer:
                # Test connections
                connections_msg = ProgressUpdate(
                    type="progress",
                    processed=10,
                    total=params.wallets,
                    percentage=10,
                    message="Testing blockchain connections..."
                )
                yield f"data: {orjson_dumps_str(connections_msg.dict())}\n\n"
                
                connections = await analyzer.services.test_connections()
                if not all(connections.values()):
                    failed_services = [k for k, v in connections.items() if not v]
                    error_msg = ProgressUpdate(
                        type="error", 
                        error=f"Service connections failed: {failed_services}"
                    )
                    yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
                    return
                
                # Start main analysis
                analysis_msg = ProgressUpdate(
                    type="progress",
                    processed=20,
                    total=params.wallets,
                    percentage=20,
                    message=f"Analyzing sell pressure from {params.wallets} wallets..."
                )
                yield f"data: {orjson_dumps_str(analysis_msg.dict())}\n\n"
                
                # Run analysis
                result = await analyzer.analyze_wallets_concurrent(params.wallets, params.days)
                analysis_time = time.time() - start_time
                
                # Format and send results
                if result and result.total_transactions > 0:
                    response = ResponseFormatter.format_sell_response(result, network, analysis_time, False)
                    
                    # Cache the result in background
                    if params.use_cache:
                        cache_key = f"sell_{network}_{params.wallets}_{params.days}"
                        asyncio.create_task(
                            cache_service.set(cache_key, response, params.cache_ttl, network, "sell")
                        )
                    
                    results_msg = ProgressUpdate(type="results", data=response)
                    yield f"data: {orjson_dumps_str(results_msg.dict())}\n\n"
                    
                else:
                    # No results found
                    no_results = ResponseFormatter.format_sell_response(None, network, analysis_time, False)
                    results_msg = ProgressUpdate(type="results", data=no_results)
                    yield f"data: {orjson_dumps_str(results_msg.dict())}\n\n"
                
                # Send completion
                final_msg = ProgressUpdate(type="complete", message="Sell analysis complete")
                yield f"data: {orjson_dumps_str(final_msg.dict())}\n\n"
                
        except Exception as e:
            logger.error(f"❌ Stream sell analysis failed: {e}")
            error_msg = ProgressUpdate(type="error", error=f"Sell analysis failed: {str(e)}")
            yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )