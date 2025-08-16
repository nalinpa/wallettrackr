# utils/optimized_http.py - Quick HTTP optimization
import httpx
import orjson
import logging
from typing import Dict, List
from config.settings import alchemy_config

logger = logging.getLogger(__name__)

class QuickHTTPClient:
    """Quick HTTP optimization - drop-in replacement"""
    
    def __init__(self):
        self.client = httpx.Client(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(
                max_connections=30,
                max_keepalive_connections=15
            ),
            headers={
                'User-Agent': 'CryptoAlpha-Optimized/1.0',
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate'
            },
            http2=True
        )
    
    def make_request(self, url: str, payload: Dict) -> Dict:
        """Optimized Alchemy request"""
        try:
            # Use orjson for serialization
            json_data = orjson.dumps(payload)
            
            response = self.client.post(
                url,
                content=json_data,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            
            # Use orjson for deserialization
            return orjson.loads(response.content)
            
        except Exception as e:
            logger.error(f"HTTP request failed: {e}")
            return {}
    
    def close(self):
        """Clean shutdown"""
        self.client.close()

# Global instance
quick_http_client = QuickHTTPClient()

def get_optimized_client():
    return quick_http_client
