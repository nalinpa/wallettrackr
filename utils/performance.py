"""
Performance monitoring utilities for JSON operations
"""
import time
import functools
import logging
from utils.json_utils import orjson_dumps_str, benchmark_json_performance

logger = logging.getLogger(__name__)

def monitor_json_performance(func):
    """Decorator to monitor JSON serialization performance"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        
        # Log performance for large responses
        if isinstance(result, dict) and len(str(result)) > 10000:
            execution_time = (end_time - start_time) * 1000
            logger.info(f"🚀 {func.__name__} executed in {execution_time:.2f}ms")
            
            # Benchmark JSON performance for very large responses
            if len(str(result)) > 100000:
                metrics = benchmark_json_performance(result, iterations=10)
                logger.info(f"📊 JSON Performance: orjson {metrics['serialize_speedup']:.1f}x faster")
        
        return result
    return wrapper