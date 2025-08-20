import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json
import os
import hashlib
from pathlib import Path

from fastapi import Depends
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

class FastAPICacheService:
    """Improved cache service with better error handling and performance"""
    
    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._access_times: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        
        # Configuration
        self.max_entries = 150  # Increased limit
        self.max_age_hours = 24
        self.cache_dir = Path("cache")
        self.persist_to_disk = True
        
        # Performance metrics
        self._metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "disk_saves": 0,
            "disk_loads": 0
        }
        
        # Setup cache directory
        if self.persist_to_disk:
            self.cache_dir.mkdir(exist_ok=True)
        
        logger.info(f"🚀 Cache service initialized")
        logger.info(f"   - orjson: {'✅ enabled' if ORJSON_AVAILABLE else '❌ disabled'}")
        logger.info(f"   - persist: {'✅ enabled' if self.persist_to_disk else '❌ disabled'}")
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached data with automatic cleanup"""
        async with self._lock:
            self._metrics["total_requests"] += 1
            
            try:
                # Check if key exists and is not expired
                if key in self._cache:
                    entry = self._cache[key]
                    created_at = entry.get('created_at')
                    ttl_seconds = entry.get('ttl_seconds', 3600)
                    
                    if created_at:
                        age = (datetime.now() - created_at).total_seconds()
                        if age <= ttl_seconds:
                            # Update access time
                            self._access_times[key] = datetime.now()
                            self._metrics["cache_hits"] += 1
                            logger.debug(f"✅ Cache hit: {key} (age: {age:.1f}s)")
                            return entry['data']
                        else:
                            # Remove expired entry
                            await self._remove_entry(key)
                            logger.debug(f"⏰ Cache expired: {key} (age: {age:.1f}s)")
                
                # Try loading from disk if not in memory
                if self.persist_to_disk:
                    disk_data = await self._load_from_disk(key)
                    if disk_data:
                        # Add back to memory cache
                        self._cache[key] = disk_data
                        self._access_times[key] = datetime.now()
                        self._metrics["cache_hits"] += 1
                        self._metrics["disk_loads"] += 1
                        logger.debug(f"📂 Disk cache hit: {key}")
                        return disk_data['data']
                
                self._metrics["cache_misses"] += 1
                logger.debug(f"❌ Cache miss: {key}")
                return None
                
            except Exception as e:
                self._metrics["errors"] += 1
                logger.error(f"❌ Cache get error: {e}")
                return None
    
    async def set(self, key: str, data: Dict[str, Any], ttl_seconds: int = 3600, 
                  network: str = "unknown", analysis_type: str = "unknown") -> None:
        """Set cached data with better error handling"""
        async with self._lock:
            try:
                # Create cache entry
                entry = {
                    'data': data,
                    'created_at': datetime.now(),
                    'ttl_seconds': ttl_seconds,
                    'network': network,
                    'analysis_type': analysis_type,
                    'orjson_enabled': ORJSON_AVAILABLE,
                    'size_estimate': len(str(data))
                }
                
                # Store in memory
                self._cache[key] = entry
                self._access_times[key] = datetime.now()
                
                # Cleanup if needed
                await self._cleanup_if_needed()
                
                # Persist to disk asynchronously
                if self.persist_to_disk:
                    asyncio.create_task(self._save_to_disk(key, entry))
                
                logger.debug(f"💾 Cached: {key} (size: {entry['size_estimate']} chars, ttl: {ttl_seconds}s)")
                
            except Exception as e:
                self._metrics["errors"] += 1
                logger.error(f"❌ Cache set error: {e}")
    
    async def delete(self, key: str) -> bool:
        """Delete cache entry"""
        async with self._lock:
            try:
                removed = False
                
                if key in self._cache:
                    await self._remove_entry(key)
                    removed = True
                
                # Remove disk file
                if self.persist_to_disk:
                    disk_file = self.cache_dir / f"{self._hash_key(key)}.json"
                    if disk_file.exists():
                        disk_file.unlink()
                        removed = True
                
                logger.debug(f"🗑️ Deleted cache: {key}")
                return removed
                
            except Exception as e:
                self._metrics["errors"] += 1
                logger.error(f"❌ Cache delete error: {e}")
                return False
    
    async def clear(self, pattern: str = None) -> int:
        """Clear cache entries with pattern matching"""
        async with self._lock:
            try:
                if pattern:
                    # Clear entries matching pattern
                    to_delete = [k for k in self._cache.keys() if pattern in k]
                    for key in to_delete:
                        await self._remove_entry(key)
                    
                    # Clear matching disk files
                    if self.persist_to_disk:
                        for file_path in self.cache_dir.glob("*.json"):
                            try:
                                # This is basic - in production you'd want better pattern matching
                                if pattern in file_path.name:
                                    file_path.unlink()
                            except Exception:
                                pass
                    
                    logger.info(f"🧹 Cleared {len(to_delete)} cache entries matching '{pattern}'")
                    return len(to_delete)
                else:
                    # Clear all
                    count = len(self._cache)
                    self._cache.clear()
                    self._access_times.clear()
                    
                    # Clear disk cache
                    if self.persist_to_disk:
                        for file_path in self.cache_dir.glob("*.json"):
                            try:
                                file_path.unlink()
                            except Exception:
                                pass
                    
                    logger.info(f"🧹 Cleared all {count} cache entries")
                    return count
                    
            except Exception as e:
                self._metrics["errors"] += 1
                logger.error(f"❌ Cache clear error: {e}")
                return 0
    
    async def get_status(self) -> Dict[str, Any]:
        """Get cache status with better metrics"""
        async with self._lock:
            try:
                # Calculate size
                total_size = sum(entry.get('size_estimate', 0) for entry in self._cache.values())
                size_mb = total_size / (1024 * 1024)
                
                # Get timestamps
                entries = list(self._cache.values())
                timestamps = [e['created_at'] for e in entries if 'created_at' in e]
                oldest = min(timestamps) if timestamps else None
                newest = max(timestamps) if timestamps else None
                
                # Network/type breakdown
                network_stats = {}
                type_stats = {}
                
                for entry in entries:
                    network = entry.get('network', 'unknown')
                    analysis_type = entry.get('analysis_type', 'unknown')
                    network_stats[network] = network_stats.get(network, 0) + 1
                    type_stats[analysis_type] = type_stats.get(analysis_type, 0) + 1
                
                return {
                    "cache_entries": len(self._cache),
                    "total_size_mb": round(size_mb, 2),
                    "oldest_entry": oldest.isoformat() if oldest else None,
                    "newest_entry": newest.isoformat() if newest else None,
                    "network_breakdown": network_stats,
                    "type_breakdown": type_stats,
                    "orjson_available": ORJSON_AVAILABLE,
                    "disk_persistence": self.persist_to_disk,
                    "metrics": self._metrics.copy()
                }
                
            except Exception as e:
                self._metrics["errors"] += 1
                logger.error(f"❌ Cache status error: {e}")
                return {"error": str(e)}
    
    async def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance metrics"""
        try:
            total_requests = max(self._metrics["total_requests"], 1)
            hit_rate = (self._metrics["cache_hits"] / total_requests) * 100
            
            status = await self.get_status()
            
            return {
                "hit_rate_percentage": round(hit_rate, 1),
                "total_requests": self._metrics["total_requests"],
                "cache_size_mb": status.get("total_size_mb", 0),
                "orjson_enabled": ORJSON_AVAILABLE,
                "error_rate": round((self._metrics["errors"] / total_requests) * 100, 1),
                "disk_operations": {
                    "saves": self._metrics["disk_saves"],
                    "loads": self._metrics["disk_loads"]
                }
            }
        except Exception as e:
            logger.error(f"❌ Performance summary error: {e}")
            return {"error": str(e)}
    
    async def _cleanup_if_needed(self):
        """Clean up old entries if cache is too large"""
        if len(self._cache) <= self.max_entries:
            return
        
        try:
            # Remove entries by LRU (least recently used)
            sorted_by_access = sorted(
                self._access_times.items(),
                key=lambda x: x[1]
            )
            
            # Remove oldest entries
            to_remove = len(self._cache) - self.max_entries + 10  # Remove a few extra
            for key, _ in sorted_by_access[:to_remove]:
                await self._remove_entry(key)
            
            logger.debug(f"🧹 Cleaned up {to_remove} old cache entries")
            
        except Exception as e:
            logger.error(f"❌ Cache cleanup error: {e}")
    
    async def _remove_entry(self, key: str):
        """Remove entry from memory cache"""
        if key in self._cache:
            del self._cache[key]
        if key in self._access_times:
            del self._access_times[key]
    
    def _hash_key(self, key: str) -> str:
        """Create hash for disk filename"""
        return hashlib.md5(key.encode()).hexdigest()
    
    async def _save_to_disk(self, key: str, entry: Dict):
        """Save entry to disk asynchronously with UTF-8 encoding"""
        try:
            file_path = self.cache_dir / f"{self._hash_key(key)}.json"
            
            disk_data = {
                "key": key,
                "entry": {
                    **entry,
                    "created_at": entry["created_at"].isoformat()
                },
                "saved_at": datetime.now().isoformat()
            }
            
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(serialize(disk_data))
            
            self._metrics["disk_saves"] += 1
            logger.debug(f"💾 Saved to disk: {key}")
            
        except Exception as e:
            logger.error(f"❌ Disk save error for {key}: {e}")
    
    async def _load_from_disk(self, key: str) -> Optional[Dict]:
        """Load entry from disk with UTF-8 encoding"""
        try:
            file_path = self.cache_dir / f"{self._hash_key(key)}.json"
            
            if not file_path.exists():
                return None
            
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            disk_data = deserialize(content)
            entry = disk_data["entry"]
            
            # Parse datetime back
            entry["created_at"] = datetime.fromisoformat(entry["created_at"])
            
            # Check if still valid
            age = (datetime.now() - entry["created_at"]).total_seconds()
            if age <= entry.get("ttl_seconds", 3600):
                return entry
            else:
                # Remove expired file
                file_path.unlink()
                return None
                
        except Exception as e:
            logger.error(f"❌ Disk load error for {key}: {e}")
            return None
    
    async def load_from_disk(self) -> int:
        """Load all valid cache entries from disk on startup with UTF-8 encoding"""
        if not self.persist_to_disk or not self.cache_dir.exists():
            return 0
        
        loaded = 0
        
        try:
            for file_path in self.cache_dir.glob("*.json"):
                try:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                    
                    disk_data = deserialize(content)
                    key = disk_data["key"]
                    entry = disk_data["entry"]
                    
                    # Parse datetime
                    entry["created_at"] = datetime.fromisoformat(entry["created_at"])
                    
                    # Check if still valid
                    age = (datetime.now() - entry["created_at"]).total_seconds()
                    if age <= entry.get("ttl_seconds", 3600):
                        self._cache[key] = entry
                        self._access_times[key] = entry["created_at"]
                        loaded += 1
                    else:
                        # Remove expired file
                        file_path.unlink()
                        
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load {file_path}: {e}")
                    # Remove corrupted file
                    try:
                        file_path.unlink()
                    except Exception:
                        pass
            
            logger.info(f"📂 Loaded {loaded} cache entries from disk")
            return loaded
            
        except Exception as e:
            logger.error(f"❌ Disk loading error: {e}")
            return 0

# Global cache service instance
_cache_service: Optional[FastAPICacheService] = None

def get_cache_service() -> FastAPICacheService:
    """Get cache service instance"""
    global _cache_service
    if _cache_service is None:
        _cache_service = FastAPICacheService()
    return _cache_service

# Startup/shutdown functions
async def startup_cache_service():
    """Initialize cache service on startup"""
    cache_service = get_cache_service()
    await cache_service.load_from_disk()
    logger.info("🚀 Cache service started")

async def shutdown_cache_service():
    """Cleanup cache service on shutdown"""
    logger.info("🛑 Cache service stopped")