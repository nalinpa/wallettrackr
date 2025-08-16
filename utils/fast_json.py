# utils/fast_json.py - Quick JSON optimization
import orjson
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

def fast_dumps(obj: Any) -> str:
    """Fast JSON serialization"""
    try:
        # Sanitize first
        cleaned = sanitize_for_orjson(obj)
        return orjson.dumps(cleaned, option=orjson.OPT_NAIVE_UTC).decode('utf-8')
    except Exception as e:
        logger.warning(f"orjson failed, using json: {e}")
        return json.dumps(obj, default=str)

def fast_loads(data: str) -> Any:
    """Fast JSON deserialization"""
    try:
        return orjson.loads(data)
    except Exception as e:
        logger.warning(f"orjson loads failed: {e}")
        return json.loads(data)

def sanitize_for_orjson(obj: Any) -> Any:
    """Quick sanitization for orjson"""
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, dict):
        return {k: sanitize_for_orjson(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_orjson(item) for item in obj]
    elif isinstance(obj, tuple):
        return list(obj)
    elif hasattr(obj, '__dict__'):
        return sanitize_for_orjson(obj.__dict__)
    else:
        return obj

def benchmark_json_speed(data: Dict, iterations: int = 100) -> Dict:
    """Quick benchmark"""
    import time
    
    # Test orjson
    start = time.perf_counter()
    for _ in range(iterations):
        fast_dumps(data)
    orjson_time = time.perf_counter() - start
    
    # Test standard json
    start = time.perf_counter()
    for _ in range(iterations):
        json.dumps(data, default=str)
    json_time = time.perf_counter() - start
    
    speedup = json_time / orjson_time if orjson_time > 0 else 1
    
    return {
        'orjson_time_ms': orjson_time * 1000,
        'json_time_ms': json_time * 1000,
        'speedup': speedup
    }
