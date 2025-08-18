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
        print(f"🚀 Starting {network} buy analysis: {params['wallets']} wallets, {params['days']} days")
        
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
                print(f"⚠️ Analysis returned None for {network} - creating empty result")
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
        print(f"❌ {network} buy analysis failed: {e} 115 - routes")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@router.get("/{network}/sell", response_model=SellAnalysisResponse)
async def analyze_sell_pressure(
    network: str = Depends(validate_network),
    params: Dict[str, Any] = Depends(get_analysis_params)
):
    """Sell pressure analysis with concurrent processing"""
    start_time = time.time()
    
    try:
        print(f"🚀 Starting {network} sell analysis: {params['wallets']} wallets, {params['days']} days")

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
                print(f"❌ Analysis returned None for {network} 148 - routes")
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
        print(f"❌ {network} sell analysis failed: {e} 173 - routes")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@router.get("/{network}/buy/stream")
async def stream_buy_analysis(
    network: str = Depends(validate_network),
    wallets: int = Query(173, ge=1, le=500),
    days: float = Query(1.0, ge=0.1, le=7.0)
):
    """Stream buy analysis - Flask style approach"""
    
    print(f"Starting stream for {network} buy analysis: {wallets} wallets, {days} days")
    
    def generate_stream():
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
            
            # Initialize analyzer (sync style)
            analyzer = None
            try:
                # Create analyzer synchronously
                print(f"📡 Initializing {network} buy analyzer")

                # Run async initialization in sync context
                import asyncio
                
                async def init_analyzer():
                    analyzer = BuyAnalyzer(network)
                    await analyzer.__aenter__()  # Initialize the context
                    return analyzer
                
                # Get event loop and run initialization
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                analyzer = loop.run_until_complete(init_analyzer())
                
                init_msg = ProgressUpdate(
                    type="progress",
                    processed=1,
                    total=wallets,
                    percentage=1,
                    message=f"Analyzer initialized for {network}"
                )
                yield f"data: {orjson_dumps_str(init_msg.dict())}\n\n"
                
            except Exception as e:
                error_msg = ProgressUpdate(type="error", error=f"Failed to initialize analyzer: {str(e)}")
                yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
                return
            
            # Test connections
            try:
                print(f"🔌 Testing connections for {network}")
                
                async def test_connections():
                    return await analyzer.services.test_connections()
                
                connections = loop.run_until_complete(test_connections())
                
                if not all(connections.values()):
                    failed_services = [k for k, v in connections.items() if not v]
                    error_msg = ProgressUpdate(type="error", error=f"Connection failed: {failed_services}")
                    yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
                    return
                
                conn_msg = ProgressUpdate(
                    type="progress",
                    processed=5,
                    total=wallets,
                    percentage=5,
                    message=f"Connected to {network} services"
                )
                yield f"data: {orjson_dumps_str(conn_msg.dict())}\n\n"
                
            except Exception as e:
                error_msg = ProgressUpdate(type="error", error=f"Connection test failed: {str(e)}")
                yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
                return
            
            # Run main analysis
            try:
                print(f"📊 Starting main analysis: {wallets} wallets over {days} days")

                # Send analysis start message
                analysis_msg = ProgressUpdate(
                    type="progress",
                    processed=10,
                    total=wallets,
                    percentage=10,
                    message=f"Analyzing {wallets} wallets over {days} days..."
                )
                yield f"data: {orjson_dumps_str(analysis_msg.dict())}\n\n"
                
                # Run the analysis
                start_time = time.time()
                
                async def run_analysis():
                    return await analyzer.analyze_wallets_concurrent(
                        num_wallets=wallets,
                        days_back=days
                    )
                
                result = loop.run_until_complete(run_analysis())
                analysis_time = time.time() - start_time

                print(f"✅ Analysis completed in {analysis_time:.2f}s")

                # Send progress completion
                complete_msg = ProgressUpdate(
                    type="progress",
                    processed=wallets,
                    total=wallets,
                    percentage=100,
                    message=f"Analysis complete in {analysis_time:.1f}s, formatting results..."
                )
                yield f"data: {orjson_dumps_str(complete_msg.dict())}\n\n"
                
                # Format and send results
                if result and result.total_transactions > 0:
                    print(f"📋 Found {result.total_transactions} transactions, formatting response...")

                    # Build response data (Flask style)
                    response_data = {
                        "status": "success",
                        "network": network,
                        "analysis_type": "buy",
                        "total_purchases": result.total_transactions,
                        "unique_tokens": result.unique_tokens,
                        "total_eth_spent": result.total_eth_value,
                        "total_usd_spent": result.total_eth_value * 2500,  # Rough ETH price
                        "top_tokens": [],
                        "platform_summary": result.performance_metrics.get('platform_summary', {}),
                        "web3_enhanced": result.web3_enhanced,
                        "orjson_enabled": ORJSON_AVAILABLE,
                        "analysis_time_seconds": analysis_time,
                        "last_updated": datetime.now()
                    }
                    
                    # Add top tokens
                    for i, (token, data, score) in enumerate(result.ranked_tokens[:20], 1):
                        token_analysis = {
                            "rank": i,
                            "token": token,
                            "alpha_score": score,
                            "wallet_count": len(data.get('wallets', [])),
                            "total_eth_spent": data.get('total_eth_spent', 0),
                            "platforms": list(data.get('platforms', [])),
                            "contract_address": data.get('contract_address', ''),
                            "avg_wallet_score": data.get('avg_wallet_score', 0),
                            "sophistication_score": data.get('avg_sophistication'),
                            "is_base_native": data.get('is_base_native', False)
                        }
                        response_data['top_tokens'].append(token_analysis)
                    
                    results_msg = ProgressUpdate(
                        type="results",
                        data=sanitize_for_orjson(response_data)
                    )
                    yield f"data: {orjson_dumps_str(results_msg.dict())}\n\n"
                    print(f"📤 Results sent to client")

                else:
                    print("⚠️ No results found in analysis")
                    no_results_msg = ProgressUpdate(
                        type="results",
                        data={
                            "status": "success",
                            "network": network,
                            "analysis_type": "buy",
                            "total_purchases": 0,
                            "unique_tokens": 0,
                            "total_eth_spent": 0.0,
                            "total_usd_spent": 0.0,
                            "top_tokens": [],
                            "platform_summary": {},
                            "message": "No significant activity found",
                            "analysis_time_seconds": analysis_time,
                            "last_updated": datetime.now()
                        }
                    )
                    yield f"data: {orjson_dumps_str(no_results_msg.dict())}\n\n"
                
            except Exception as analysis_error:
                analysis_time = time.time() - start_time if 'start_time' in locals() else 0
                print(f"❌ Analysis failed after {analysis_time:.2f}s: {str(analysis_error)} 369 - routes")

                error_msg = ProgressUpdate(
                    type="error",
                    error=f"Analysis failed: {str(analysis_error)}"
                )
                yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
                return
            
            # Send completion
            final_msg = ProgressUpdate(type="complete", message="Analysis complete")
            yield f"data: {orjson_dumps_str(final_msg.dict())}\n\n"
            print(f"🎉 Stream completed successfully")

            # Cleanup
            if analyzer:
                try:
                    loop.run_until_complete(analyzer.__aexit__(None, None, None))
                except:
                    pass
            
        except Exception as e:
            print(f"💥 Stream error: {str(e)}")
            error_msg = ProgressUpdate(type="error", error=f"Stream error: {str(e)}")
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
    wallets: int = Query(173, ge=1, le=500),
    days: float = Query(1.0, ge=0.1, le=7.0)
):
    """Stream sell analysis - Flask style approach"""
    
    def generate_stream():
        try:
            # Send start message
            start_msg = ProgressUpdate(
                type="progress",
                processed=0,
                total=wallets,
                percentage=0,
                message=f"Starting {network} sell pressure analysis..."
            )
            yield f"data: {orjson_dumps_str(start_msg.dict())}\n\n"
            
            # Initialize analyzer
            analyzer = None
            try:
                import asyncio
                
                async def init_analyzer():
                    analyzer = SellAnalyzer(network)
                    await analyzer.__aenter__()
                    return analyzer
                
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                analyzer = loop.run_until_complete(init_analyzer())
                
                init_msg = ProgressUpdate(
                    type="progress",
                    processed=1,
                    total=wallets,
                    percentage=1,
                    message=f"Sell analyzer initialized for {network}"
                )
                yield f"data: {orjson_dumps_str(init_msg.dict())}\n\n"
                
            except Exception as e:
                error_msg = ProgressUpdate(type="error", error=f"Failed to initialize analyzer: {str(e)}")
                yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
                return
            
            # Test connections
            try:
                async def test_connections():
                    return await analyzer.services.test_connections()
                
                connections = loop.run_until_complete(test_connections())
                
                if not all(connections.values()):
                    failed_services = [k for k, v in connections.items() if not v]
                    error_msg = ProgressUpdate(type="error", error=f"Connection failed: {failed_services}")
                    yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
                    return
                
                conn_msg = ProgressUpdate(
                    type="progress",
                    processed=5,
                    total=wallets,
                    percentage=5,
                    message=f"Connected to {network} services"
                )
                yield f"data: {orjson_dumps_str(conn_msg.dict())}\n\n"
                
            except Exception as e:
                error_msg = ProgressUpdate(type="error", error=f"Connection test failed: {str(e)}")
                yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
                return
            
            # Run analysis
            try:
                analysis_msg = ProgressUpdate(
                    type="progress",
                    processed=10,
                    total=wallets,
                    percentage=10,
                    message=f"Analyzing sell pressure for {wallets} wallets..."
                )
                yield f"data: {orjson_dumps_str(analysis_msg.dict())}\n\n"
                
                start_time = time.time()
                
                async def run_analysis():
                    return await analyzer.analyze_wallets_concurrent(
                        num_wallets=wallets,
                        days_back=days
                    )
                
                result = loop.run_until_complete(run_analysis())
                analysis_time = time.time() - start_time
                
                complete_msg = ProgressUpdate(
                    type="progress",
                    processed=wallets,
                    total=wallets,
                    percentage=100,
                    message=f"Sell analysis complete in {analysis_time:.1f}s"
                )
                yield f"data: {orjson_dumps_str(complete_msg.dict())}\n\n"
                
                # Format results
                if result and result.total_transactions > 0:
                    response_data = {
                        "status": "success",
                        "network": network,
                        "analysis_type": "sell",
                        "total_sells": result.total_transactions,
                        "unique_tokens": result.unique_tokens,
                        "total_estimated_eth": result.total_eth_value,
                        "top_tokens": [],
                        "method_summary": result.performance_metrics.get('method_summary', {}),
                        "web3_enhanced": result.web3_enhanced,
                        "orjson_enabled": ORJSON_AVAILABLE,
                        "analysis_time_seconds": analysis_time,
                        "last_updated": datetime.now()
                    }
                    
                    # Add top tokens
                    for i, (token, data, score) in enumerate(result.ranked_tokens[:20], 1):
                        token_analysis = {
                            "rank": i,
                            "token": token,
                            "sell_score": score,  # Different field for sells
                            "wallet_count": len(data.get('wallets', [])),
                            "total_estimated_eth": data.get('total_estimated_eth', 0),
                            "methods": list(data.get('platforms', [])),  # Different field
                            "contract_address": data.get('contract_address', ''),
                            "avg_wallet_score": data.get('avg_wallet_score', 0),
                            "sophistication_score": data.get('avg_sophistication'),
                            "is_base_native": data.get('is_base_native', False)
                        }
                        response_data['top_tokens'].append(token_analysis)
                    
                    results_msg = ProgressUpdate(
                        type="results",
                        data=sanitize_for_orjson(response_data)
                    )
                    yield f"data: {orjson_dumps_str(results_msg.dict())}\n\n"
                    
                else:
                    no_results_msg = ProgressUpdate(
                        type="results",
                        data={
                            "status": "success",
                            "network": network,
                            "analysis_type": "sell",
                            "total_sells": 0,
                            "unique_tokens": 0,
                            "total_estimated_eth": 0.0,
                            "top_tokens": [],
                            "method_summary": {},
                            "message": "No sell pressure detected",
                            "analysis_time_seconds": analysis_time,
                            "last_updated": datetime.now()
                        }
                    )
                    yield f"data: {orjson_dumps_str(no_results_msg.dict())}\n\n"
                
            except Exception as analysis_error:
                error_msg = ProgressUpdate(
                    type="error",
                    error=f"Sell analysis failed: {str(analysis_error)}"
                )
                yield f"data: {orjson_dumps_str(error_msg.dict())}\n\n"
                return
            
            # Send completion
            final_msg = ProgressUpdate(type="complete", message="Sell analysis complete")
            yield f"data: {orjson_dumps_str(final_msg.dict())}\n\n"
            
            # Cleanup
            if analyzer:
                try:
                    loop.run_until_complete(analyzer.__aexit__(None, None, None))
                except:
                    pass
            
        except Exception as e:
            print(f"💥 Sell stream error: {str(e)}")
            error_msg = ProgressUpdate(type="error", error=f"Stream error: {str(e)}")
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