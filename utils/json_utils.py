"""
JSON utilities using orjson for improved performance
"""
import orjson
import json
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, date
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class ORJSONEncoder:
    """Custom encoder for handling special types with orjson"""
    
    @staticmethod
    def default(obj: Any) -> Any:
        """Handle types that orjson doesn't natively support"""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, set):
            return list(obj)
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        else:
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def orjson_dumps(obj: Any, option: int = orjson.OPT_NAIVE_UTC) -> bytes:
    """
    Fast JSON serialization using orjson
    Returns bytes by default
    """
    try:
        return orjson.dumps(obj, default=ORJSONEncoder.default, option=option)
    except Exception as e:
        logger.error(f"orjson serialization failed: {e}")
        # Fallback to standard json
        return json.dumps(obj, default=str).encode('utf-8')

def orjson_dumps_str(obj: Any, option: int = orjson.OPT_NAIVE_UTC) -> str:
    """
    Fast JSON serialization returning string
    """
    return orjson_dumps(obj, option).decode('utf-8')

def orjson_loads(data: Union[str, bytes]) -> Any:
    """
    Fast JSON deserialization using orjson
    """
    try:
        if isinstance(data, str):
            data = data.encode('utf-8')
        return orjson.loads(data)
    except Exception as e:
        logger.error(f"orjson deserialization failed: {e}")
        # Fallback to standard json
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        return json.loads(data)

def sanitize_for_orjson(obj: Any) -> Any:
    """
    Recursively sanitize objects for orjson serialization
    Enhanced version of your existing sanitize_for_json function
    """
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, dict):
        return {k: sanitize_for_orjson(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_orjson(item) for item in obj]
    elif isinstance(obj, tuple):
        return list(sanitize_for_orjson(item) for item in obj)
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    elif hasattr(obj, '__dict__'):
        return sanitize_for_orjson(obj.__dict__)
    else:
        return obj

# Performance comparison utilities
def benchmark_json_performance(data: Dict, iterations: int = 1000) -> Dict[str, float]:
    """
    Benchmark orjson vs standard json performance
    """
    import time
    
    # Prepare data
    test_data = sanitize_for_orjson(data)
    
    # Test orjson serialization
    start_time = time.perf_counter()
    for _ in range(iterations):
        orjson_dumps(test_data)
    orjson_serialize_time = time.perf_counter() - start_time
    
    # Test standard json serialization
    start_time = time.perf_counter()
    for _ in range(iterations):
        json.dumps(test_data, default=str)
    json_serialize_time = time.perf_counter() - start_time
    
    # Test serialization + deserialization round trip
    serialized_orjson = orjson_dumps(test_data)
    serialized_json = json.dumps(test_data, default=str)
    
    # orjson round trip
    start_time = time.perf_counter()
    for _ in range(iterations):
        orjson_loads(orjson_dumps(test_data))
    orjson_roundtrip_time = time.perf_counter() - start_time
    
    # json round trip
    start_time = time.perf_counter()
    for _ in range(iterations):
        json.loads(json.dumps(test_data, default=str))
    json_roundtrip_time = time.perf_counter() - start_time
    
    speedup_serialize = json_serialize_time / orjson_serialize_time if orjson_serialize_time > 0 else 0
    speedup_roundtrip = json_roundtrip_time / orjson_roundtrip_time if orjson_roundtrip_time > 0 else 0
    
    return {
        'orjson_serialize_ms': orjson_serialize_time * 1000,
        'json_serialize_ms': json_serialize_time * 1000,
        'orjson_roundtrip_ms': orjson_roundtrip_time * 1000,
        'json_roundtrip_ms': json_roundtrip_time * 1000,
        'serialize_speedup': speedup_serialize,
        'roundtrip_speedup': speedup_roundtrip,
        'serialized_size_orjson': len(serialized_orjson),
        'serialized_size_json': len(serialized_json.encode('utf-8'))
    }