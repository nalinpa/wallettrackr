# services/cache/cache_service.py - FastAPI-native cache service

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json
import os
from pathlib import Path

from fastapi import Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import aiofiles

try:
    import orjson
    ORJSON_AVAILABLE = True
    def serialize(obj): return orjson.dumps(obj, default=str).decode()
    def deserialize(data): return orjson.loads(data)
except ImportError:
    ORJSON_AVAILABLE = False
    def serialize(obj): return json.dumps(obj, default=str)
    def deserialize(data): return json.loads(data)

logger = logging.getLogger(__name__)

# Pydantic Models
class CacheEntry(BaseModel):
    """Cache entry model with metadata"""
    data: Dict[str, Any]
    timestamp: datetime
    network: str
    analysis_type: str
    ttl_seconds: int = 3600
    orjson_optimized: bool = ORJSON_AVAILABLE
    version: str = "2.0"

class CacheMetrics(BaseModel):
    """Cache performance metrics"""
    hit_rate: float = 0.0
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_size_mb: float = 0.0
    oldest_entry: Optional[datetime] = None
    newest_entry: Optional[datetime] = None

class CacheConfig(BaseModel):
    """Cache configuration"""
    max_age_hours: int = 24
    max_entries: int = 100
    persist_to_disk: bool = True
    cache_dir: str = "cache"
    auto_cleanup: bool = True
    orjson_enabled: bool = ORJSON_AVAILABLE

class FastAPICacheService:
    """FastAPI-native cache service with dependency injection"""
    
    def __init__(self, config: CacheConfig = None):
        self.config = config or CacheConfig()
        self._cache: Dict[str, CacheEntry] = {}
        self._metrics = CacheMetrics()
        self._lock = asyncio.Lock()
        
        # Setup cache directory
        if self.config.persist_to_disk:
            Path(self.config.cache_dir).mkdir(exist_ok=True)
        
        logger.info(f"🚀 FastAPI Cache Service initialized")
        logger.info(f"   - orjson: {'✅ enabled' if ORJSON_AVAILABLE else '❌ disabled'}")
        logger.info(f"   - persist: {'✅ enabled' if self.config.persist_to_disk else '❌ disabled'}")
        logger.info(f"   - max_entries: {self.config.max_entries}")
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached data with automatic expiry"""
        async with self._lock:
            self._metrics.total_requests += 1
            
            if key not in self._cache:
                self._metrics.cache_misses += 1
                logger.debug(f"❌ Cache miss: {key}")
                return None
            
            entry = self._cache[key]
            
            # Check expiry
            age_seconds = (datetime.now() - entry.timestamp).total_seconds()
            if age_seconds > entry.ttl_seconds:
                del self._cache[key]
                self._metrics.cache_misses += 1
                logger.debug(f"⏰ Cache expired: {key} (age: {age_seconds:.1f}s)")
                return None
            
            self._metrics.cache_hits += 1
            logger.debug(f"✅ Cache hit: {key} (age: {age_seconds:.1f}s)")
            return entry.data
    
    async def set(self, key: str, data: Dict[str, Any], ttl_seconds: int = 3600, 
                  network: str = "unknown", analysis_type: str = "unknown") -> None:
        """Set cached data with metadata"""
        async with self._lock:
            # Create cache entry
            entry = CacheEntry(
                data=data,
                timestamp=datetime.now(),
                network=network,
                analysis_type=analysis_type,
                ttl_seconds=ttl_seconds,
                orjson_optimized=ORJSON_AVAILABLE
            )
            
            # Store in memory
            self._cache[key] = entry
            
            # Cleanup if too many entries
            if len(self._cache) > self.config.max_entries:
                await self._cleanup_oldest()
            
            # Persist to disk if enabled
            if self.config.persist_to_disk:
                await self._persist_entry(key, entry)
            
            logger.debug(f"💾 Cached: {key} ({len(str(data))} bytes, ttl: {ttl_seconds}s)")
    
    async def delete(self, key: str) -> bool:
        """Delete cache entry"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                
                # Remove file if it exists
                if self.config.persist_to_disk:
                    file_path = Path(self.config.cache_dir) / f"{key}.json"
                    if file_path.exists():
                        file_path.unlink()
                
                logger.debug(f"🗑️ Deleted cache: {key}")
                return True
            return False
    
    async def clear(self, pattern: str = None) -> int:
        """Clear cache entries, optionally by pattern"""
        async with self._lock:
            if pattern:
                # Clear entries matching pattern
                to_delete = [k for k in self._cache.keys() if pattern in k]
                for key in to_delete:
                    await self.delete(key)
                logger.info(f"🧹 Cleared {len(to_delete)} cache entries matching '{pattern}'")
                return len(to_delete)
            else:
                # Clear all
                count = len(self._cache)
                self._cache.clear()
                
                # Clear disk cache
                if self.config.persist_to_disk:
                    cache_dir = Path(self.config.cache_dir)
                    for file_path in cache_dir.glob("*.json"):
                        file_path.unlink()
                
                logger.info(f"🧹 Cleared all {count} cache entries")
                return count
    
    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive cache status"""
        async with self._lock:
            # Calculate metrics
            total_size = sum(len(serialize(entry.data)) for entry in self._cache.values())
            size_mb = total_size / (1024 * 1024)
            
            timestamps = [entry.timestamp for entry in self._cache.values()]
            oldest = min(timestamps) if timestamps else None
            newest = max(timestamps) if timestamps else None
            
            # Update metrics
            self._metrics.total_size_mb = size_mb
            self._metrics.oldest_entry = oldest
            self._metrics.newest_entry = newest
            if self._metrics.total_requests > 0:
                self._metrics.hit_rate = self._metrics.cache_hits / self._metrics.total_requests
            
            # Get network/type breakdown
            network_stats = {}
            type_stats = {}
            
            for entry in self._cache.values():
                network_stats[entry.network] = network_stats.get(entry.network, 0) + 1
                type_stats[entry.analysis_type] = type_stats.get(entry.analysis_type, 0) + 1
            
            return {
                "cache_entries": len(self._cache),
                "metrics": self._metrics.dict(),
                "config": self.config.dict(),
                "network_breakdown": network_stats,
                "type_breakdown": type_stats,
                "orjson_available": ORJSON_AVAILABLE,
                "disk_persistence": self.config.persist_to_disk
            }
    
    async def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary with orjson info"""
        status = await self.get_status()
        
        return {
            "hit_rate_percentage": round(self._metrics.hit_rate * 100, 1),
            "total_requests": self._metrics.total_requests,
            "cache_size_mb": round(self._metrics.total_size_mb, 2),
            "orjson_enabled": ORJSON_AVAILABLE,
            "average_entry_size_kb": round(
                (self._metrics.total_size_mb * 1024) / max(len(self._cache), 1), 1
            ),
            "entries_by_network": status["network_breakdown"],
            "entries_by_type": status["type_breakdown"]
        }
    
    async def _cleanup_oldest(self) -> None:
        """Remove oldest cache entries to stay within limits"""
        if len(self._cache) <= self.config.max_entries:
            return
        
        # Sort by timestamp and remove oldest
        sorted_items = sorted(
            self._cache.items(), 
            key=lambda x: x[1].timestamp
        )
        
        to_remove = len(self._cache) - self.config.max_entries + 1
        for key, _ in sorted_items[:to_remove]:
            await self.delete(key)
        
        logger.debug(f"🧹 Cleaned up {to_remove} oldest cache entries")
    
    async def _persist_entry(self, key: str, entry: CacheEntry) -> None:
        """Persist cache entry to disk"""
        try:
            file_path = Path(self.config.cache_dir) / f"{key}.json"
            
            # Create serializable data
            data_to_save = {
                "entry": entry.dict(),
                "saved_at": datetime.now().isoformat(),
                "version": "2.0"
            }
            
            async with aiofiles.open(file_path, 'w') as f:
                await f.write(serialize(data_to_save))
                
        except Exception as e:
            logger.warning(f"⚠️ Failed to persist cache entry {key}: {e}")
    
    async def load_from_disk(self) -> int:
        """Load cache entries from disk"""
        if not self.config.persist_to_disk:
            return 0
        
        cache_dir = Path(self.config.cache_dir)
        if not cache_dir.exists():
            return 0
        
        loaded = 0
        for file_path in cache_dir.glob("*.json"):
            try:
                async with aiofiles.open(file_path, 'r') as f:
                    content = await f.read()
                
                data = deserialize(content)
                entry_data = data.get("entry", {})
                
                # Recreate cache entry
                entry = CacheEntry(**entry_data)
                
                # Check if still valid
                age_seconds = (datetime.now() - entry.timestamp).total_seconds()
                if age_seconds < entry.ttl_seconds:
                    key = file_path.stem
                    self._cache[key] = entry
                    loaded += 1
                else:
                    # Remove expired file
                    file_path.unlink()
                    
            except Exception as e:
                logger.warning(f"⚠️ Failed to load cache file {file_path}: {e}")
                # Remove corrupted file
                file_path.unlink()
        
        logger.info(f"📂 Loaded {loaded} cache entries from disk")
        return loaded

# Global cache service instance
_cache_service: Optional[FastAPICacheService] = None

def get_cache_service() -> FastAPICacheService:
    """FastAPI dependency to get cache service"""
    global _cache_service
    if _cache_service is None:
        _cache_service = FastAPICacheService()
    return _cache_service

# Background task for cache warming
async def warm_cache_background(
    cache_service: FastAPICacheService, 
    networks: List[str], 
    wallets: int = 173, 
    days: float = 1.0
):
    """Background task to warm cache"""
    logger.info(f"🔥 Starting cache warming for {networks}")
    
    try:
        # Import here to avoid circular dependencies
        from core.analysis.buy_analyzer import BuyAnalyzer
        from core.analysis.sell_analyzer import SellAnalyzer
        
        for network in networks:
            try:
                logger.info(f"🔥 Warming cache for {network}")
                
                # Run buy analysis
                async with BuyAnalyzer(network) as analyzer:
                    result = await analyzer.analyze_wallets_concurrent(wallets, days)
                    
                    if result and result.total_transactions > 0:
                        # Cache the formatted result
                        cache_data = {
                            "status": "success",
                            "network": network,
                            "analysis_type": "buy",
                            "total_purchases": result.total_transactions,
                            "unique_tokens": result.unique_tokens,
                            "total_eth_spent": result.total_eth_value,
                            "ranked_tokens": result.ranked_tokens[:20],  # Limit size
                            "last_updated": datetime.now().isoformat(),
                            "from_cache_warming": True
                        }
                        
                        cache_key = f"{network}_buy_{wallets}_{days}"
                        await cache_service.set(
                            cache_key, cache_data, 
                            ttl_seconds=3600,  # 1 hour
                            network=network, 
                            analysis_type="buy"
                        )
                        
                        logger.info(f"✅ Cached buy analysis for {network}")
                
                # Brief pause between networks
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Cache warming failed for {network}: {e}")
        
        logger.info(f"✅ Cache warming completed for {networks}")
        
    except Exception as e:
        logger.error(f"❌ Cache warming failed: {e}")

# Cache decorators for FastAPI endpoints
def cache_response(ttl_seconds: int = 3600, key_prefix: str = ""):
    """Decorator to cache FastAPI endpoint responses"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Get cache service
            cache_service = get_cache_service()
            
            # Generate cache key from function name and args
            cache_key = f"{key_prefix}_{func.__name__}_{hash(str(kwargs))}"
            
            # Try to get from cache
            cached_result = await cache_service.get(cache_key)
            if cached_result is not None:
                logger.debug(f"📋 Returning cached response for {func.__name__}")
                return cached_result
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache the result
            if result and isinstance(result, dict):
                await cache_service.set(
                    cache_key, result, 
                    ttl_seconds=ttl_seconds,
                    network=kwargs.get('network', 'unknown'),
                    analysis_type=func.__name__
                )
            
            return result
        return wrapper
    return decorator

# FastAPI lifespan events
async def startup_cache_service():
    """Initialize cache service on startup"""
    cache_service = get_cache_service()
    await cache_service.load_from_disk()
    logger.info("🚀 Cache service started")

async def shutdown_cache_service():
    """Cleanup cache service on shutdown"""
    cache_service = get_cache_service()
    # Final cleanup
    await cache_service.clear()
    logger.info("🛑 Cache service stopped")