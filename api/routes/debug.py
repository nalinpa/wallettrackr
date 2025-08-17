# debug_streaming.py - Let's find the exact issue with your streaming

from fastapi import APIRouter, Query, Depends
from fastapi.responses import StreamingResponse
from typing import Literal
import json
import logging
import time

router = APIRouter(tags=["debug-stream"])
logger = logging.getLogger(__name__)

@router.get("/debug-stream/simple")
async def debug_simple_stream():
    """Simple stream to test basic functionality"""
    
    def simple_generator():
        """Basic generator that should work"""
        try:
            for i in range(5):
                message = {
                    "type": "progress",
                    "step": i + 1,
                    "message": f"Step {i + 1} of 5"
                }
                yield f"data: {json.dumps(message)}\n\n"
                time.sleep(0.5)  # Simulate work
            
            final_message = {
                "type": "complete",
                "message": "Simple stream test complete"
            }
            yield f"data: {json.dumps(final_message)}\n\n"
            
        except Exception as e:
            error_message = {
                "type": "error", 
                "error": f"Simple stream error: {str(e)}"
            }
            yield f"data: {json.dumps(error_message)}\n\n"
    
    return StreamingResponse(
        simple_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/debug-stream/tracker-import")
async def debug_tracker_import():
    """Test if the issue is with tracker import"""
    
    def tracker_import_generator():
        try:
            # Test 1: Basic message
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Starting tracker import test'})}\n\n"
            
            # Test 2: Try importing tracker
            try:
                from tracker.buy_tracker import ComprehensiveBuyTracker
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Successfully imported ComprehensiveBuyTracker'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': f'Import failed: {str(e)}'})}\n\n"
                return
            
            # Test 3: Try initializing tracker
            try:
                tracker = ComprehensiveBuyTracker("base")
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Successfully initialized tracker'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': f'Tracker init failed: {str(e)}'})}\n\n"
                return
            
            # Test 4: Try connection test
            try:
                connection_result = tracker.test_connection()
                yield f"data: {json.dumps({'type': 'progress', 'message': f'Connection test: {connection_result}'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': f'Connection test failed: {str(e)}'})}\n\n"
                return
            
            yield f"data: {json.dumps({'type': 'complete', 'message': 'Tracker import test complete'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': f'Unexpected error: {str(e)}'})}\n\n"
    
    return StreamingResponse(
        tracker_import_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/debug-stream/your-function-structure")
async def debug_your_function():
    """Test the exact structure of your current function"""
    
    def generate_stream():  # This matches your structure
        try:
            logger.info("🚀 Debug: Starting stream")
            
            # Send start message (like your code)
            start_msg = {
                "type": "progress",
                "processed": 0,
                "total": 5,
                "percentage": 0,
                "message": "Debug: Starting analysis..."
            }
            yield f"data: {json.dumps(start_msg)}\n\n"
            
            # Test if this is where the error occurs
            try:
                # Simulate what your tracker initialization does
                logger.info("📡 Debug: Initializing tracker")
                
                init_msg = {
                    "type": "progress",
                    "processed": 1,
                    "total": 5,
                    "percentage": 20,
                    "message": "Debug: Tracker initialized"
                }
                yield f"data: {json.dumps(init_msg)}\n\n"
                
            except Exception as e:
                error_msg = {"type": "error", "error": f"Debug: Init failed: {str(e)}"}
                yield f"data: {json.dumps(error_msg)}\n\n"
                return
            
            # Test connection simulation
            try:
                logger.info("🔌 Debug: Testing connection")
                
                conn_msg = {
                    "type": "progress",
                    "processed": 2,
                    "total": 5,
                    "percentage": 40,
                    "message": "Debug: Connection successful"
                }
                yield f"data: {json.dumps(conn_msg)}\n\n"
                
            except Exception as e:
                error_msg = {"type": "error", "error": f"Debug: Connection failed: {str(e)}"}
                yield f"data: {json.dumps(error_msg)}\n\n"
                return
            
            # Simulate the analysis part
            for i in range(3, 6):
                progress_msg = {
                    "type": "progress",
                    "processed": i,
                    "total": 5,
                    "percentage": i * 20,
                    "message": f"Debug: Step {i} complete"
                }
                yield f"data: {json.dumps(progress_msg)}\n\n"
                time.sleep(0.2)  # Brief pause
            
            # Send completion
            final_msg = {"type": "complete", "message": "Debug: Function structure test complete"}
            yield f"data: {json.dumps(final_msg)}\n\n"
            logger.info("🎉 Debug: Stream completed successfully")
            
        except Exception as e:
            logger.error(f"💥 Debug: Stream error: {str(e)}", exc_info=True)
            error_msg = {"type": "error", "error": f"Debug: Stream error: {str(e)}"}
            yield f"data: {json.dumps(error_msg)}\n\n"
    
    return StreamingResponse(
        generate_stream(),  # This matches your exact syntax
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/debug-stream/find-async-issue")
async def find_async_issue():
    """Check if there's an async/await issue in your code"""
    
    def check_async_generator():
        try:
            yield f"data: {json.dumps({'message': 'Testing for async issues'})}\n\n"
            
            # This would cause the async error if incorrectly used:
            # async def bad_generator():
            #     yield "something"
            # 
            # The error happens when you try to use async def for a generator
            # that's passed to StreamingResponse
            
            yield f"data: {json.dumps({'message': 'No async issues in this generator'})}\n\n"
            
            # Check if your orjson_dumps_str function might be async
            try:
                # Import your JSON function if available
                try:
                    from utils.json_utils import orjson_dumps_str
                    test_data = {"test": "data"}
                    result = orjson_dumps_str(test_data)  # This should NOT be awaited
                    yield f"data: {json.dumps({'message': f'orjson_dumps_str works: {type(result)}'})}\n\n"
                except ImportError:
                    yield f"data: {json.dumps({'message': 'orjson_dumps_str not available, using json.dumps'})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'error': f'orjson_dumps_str error: {str(e)}'})}\n\n"
                    
            except Exception as e:
                yield f"data: {json.dumps({'error': f'JSON function test failed: {str(e)}'})}\n\n"
            
            yield f"data: {json.dumps({'type': 'complete', 'message': 'Async issue check complete'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': f'Async check error: {str(e)}'})}\n\n"
    
    return StreamingResponse(
        check_async_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )   