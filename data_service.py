from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging
import json
import os
from collections import defaultdict

# Import settings
from config.settings import settings, analysis_config, monitor_config

# Enhanced imports with orjson support
try:
    from utils.json_utils import orjson_dumps_str, orjson_loads, sanitize_for_orjson, benchmark_json_performance
    ORJSON_AVAILABLE = True
    print("✅ orjson integration enabled in data_service")
except ImportError as e:
    print(f"⚠️  orjson not available in data_service: {e}")
    ORJSON_AVAILABLE = False
    # Fallback functions
    def orjson_dumps_str(obj, **kwargs):
        return json.dumps(obj, default=str)
    def orjson_loads(data):
        return json.loads(data)
    def sanitize_for_orjson(obj):
        return obj
    def benchmark_json_performance(data, iterations=100):
        return {"serialize_speedup": 1.0, "roundtrip_speedup": 1.0}

# Configure logger
logger = logging.getLogger(__name__)

class AnalysisService:
    """Service for data processing and caching with orjson optimization"""
    
    def __init__(self):
        self.cache = {
            'ethereum_buy': None,    # Fixed: was 'eth_buy'
            'ethereum_sell': None,   # Fixed: was 'eth_sell'
            'base_buy': None,
            'base_sell': None,
            'last_updated': None,
            'cache_metadata': {}
        }
        
        # Enhanced cache configuration with orjson support
        self.cache_config = {
            'max_age_hours': 24,  # How long to keep cached data
            'auto_cleanup': True,
            'persist_to_file': True,  # Enable file persistence with orjson
            'cache_file': 'cache/analysis_cache.json',
            'use_orjson': ORJSON_AVAILABLE,  # Flag to enable orjson
            'benchmark_performance': True  # Set to True to log performance metrics
        }
        
        logger.info(f"AnalysisService initialized for {settings.environment} environment")
        logger.info(f"Supported networks: {[net.value for net in settings.monitor.supported_networks]}")
        logger.info(f"orjson optimization: {'✅ enabled' if ORJSON_AVAILABLE else '❌ disabled'}")
        
        # Load existing cache if available
        if self.cache_config['persist_to_file']:
            self.load_cache_from_file()
    
    def cache_data(self, key: str, data: Dict) -> None:
        """Enhanced cache with orjson performance"""
        # Validate key against supported networks
        valid_keys = self._get_valid_cache_keys()
        if key not in valid_keys:
            logger.warning(f"Invalid cache key: {key}. Valid keys: {valid_keys}")
            return
        
        # Sanitize data for orjson
        if ORJSON_AVAILABLE:
            sanitized_data = sanitize_for_orjson(data)
        else:
            sanitized_data = data
        
        # Add metadata with performance info
        cache_entry = {
            'data': sanitized_data,
            'timestamp': datetime.now().isoformat(),
            'environment': settings.environment,
            'config_hash': self._get_config_hash(),
            'serialization_method': 'orjson' if self.cache_config['use_orjson'] else 'json',
            'orjson_available': ORJSON_AVAILABLE
        }
        
        # Benchmark performance if enabled
        if self.cache_config['benchmark_performance'] and ORJSON_AVAILABLE:
            try:
                perf_metrics = benchmark_json_performance(sanitized_data, iterations=50)
                logger.info(f"📊 Cache performance for {key}: orjson {perf_metrics['serialize_speedup']:.1f}x faster")
                cache_entry['performance_metrics'] = {
                    'serialize_speedup': round(perf_metrics['serialize_speedup'], 1),
                    'cache_size_bytes': len(str(sanitized_data)),
                    'benchmark_iterations': 50
                }
            except Exception as e:
                logger.debug(f"Performance benchmarking failed: {e}")
        
        self.cache[key] = cache_entry
        self.cache['last_updated'] = datetime.now().isoformat()
        
        # Update metadata
        self.cache['cache_metadata'][key] = {
            'size_estimate': len(str(sanitized_data)),
            'token_count': data.get('unique_tokens', 0),
            'network': self._extract_network_from_key(key),
            'analysis_type': self._extract_analysis_type_from_key(key),
            'orjson_optimized': ORJSON_AVAILABLE
        }
        
        logger.info(f"✅ Cached data for {key}: {data.get('unique_tokens', 0)} tokens (orjson: {'✅' if ORJSON_AVAILABLE else '❌'})")
        
        # Auto-cleanup if enabled
        if self.cache_config['auto_cleanup']:
            self._cleanup_expired_cache()
        
        # Persist to file if enabled
        if self.cache_config['persist_to_file']:
            self._persist_cache_to_file()
    
    def get_cached_data(self, key: str) -> Optional[Dict]:
        """Enhanced get cached data with orjson validation"""
        cache_entry = self.cache.get(key)
        
        if not cache_entry:
            return None
        
        # Handle old cache format (direct data)
        if not isinstance(cache_entry, dict) or 'data' not in cache_entry:
            logger.warning(f"Old cache format detected for {key}, returning as-is")
            return cache_entry
        
        # Check if cache is expired
        if self._is_cache_expired(cache_entry):
            logger.info(f"Cache expired for {key}, removing")
            self.cache[key] = None
            return None
        
        # Check if config has changed significantly
        if self._has_config_changed(cache_entry):
            logger.info(f"Configuration changed since {key} was cached, data may be stale")
            # Could optionally invalidate here
        
        # Log cache hit with performance info
        if ORJSON_AVAILABLE and cache_entry.get('performance_metrics'):
            perf = cache_entry['performance_metrics']
            logger.debug(f"📊 Cache hit for {key}: {perf.get('serialize_speedup', 0)}x faster with orjson")
        
        return cache_entry['data']
    
    def get_cache_status(self) -> Dict[str, Any]:
        """Enhanced status with orjson information"""
        status = {}
        valid_keys = self._get_valid_cache_keys()
        
        for key in valid_keys:
            cache_entry = self.cache.get(key)
            
            if not cache_entry:
                status[key] = {
                    'available': False,
                    'status': 'empty'
                }
                continue
            
            # Handle old format
            if not isinstance(cache_entry, dict) or 'data' not in cache_entry:
                status[key] = {
                    'available': True,
                    'status': 'legacy_format',
                    'timestamp': 'unknown',
                    'orjson_optimized': False
                }
                continue
            
            # Check status
            is_expired = self._is_cache_expired(cache_entry)
            config_changed = self._has_config_changed(cache_entry)
            
            status[key] = {
                'available': True,
                'status': 'expired' if is_expired else 'fresh',
                'timestamp': cache_entry.get('timestamp'),
                'environment': cache_entry.get('environment'),
                'config_changed': config_changed,
                'serialization_method': cache_entry.get('serialization_method', 'json'),
                'orjson_optimized': cache_entry.get('orjson_available', False),
                'metadata': self.cache['cache_metadata'].get(key, {})
            }
            
            # Add performance metrics if available
            if cache_entry.get('performance_metrics'):
                status[key]['performance_metrics'] = cache_entry['performance_metrics']
        
        # Add overall cache info with orjson status
        status['_cache_info'] = {
            'last_updated': self.cache['last_updated'],
            'supported_networks': [net.value for net in settings.monitor.supported_networks],
            'environment': settings.environment,
            'auto_cleanup': self.cache_config['auto_cleanup'],
            'max_age_hours': self.cache_config['max_age_hours'],
            'orjson_available': ORJSON_AVAILABLE,
            'orjson_enabled': self.cache_config['use_orjson'],
            'performance_benchmarking': self.cache_config['benchmark_performance']
        }
        
        return status
    
    def _persist_cache_to_file(self) -> None:
        """Enhanced cache persistence using orjson"""
        try:
            os.makedirs(os.path.dirname(self.cache_config['cache_file']), exist_ok=True)
            
            # Prepare cache data for serialization
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'environment': settings.environment,
                'serialization_method': 'orjson' if self.cache_config['use_orjson'] else 'json',
                'orjson_available': ORJSON_AVAILABLE,
                'cache': {}
            }
            
            for key, value in self.cache.items():
                if value is not None and key != 'cache_metadata':
                    cache_data['cache'][key] = value
            
            # Use orjson for file persistence if available
            if self.cache_config['use_orjson'] and ORJSON_AVAILABLE:
                start_time = datetime.now()
                json_str = orjson_dumps_str(cache_data)
                persist_time = (datetime.now() - start_time).total_seconds() * 1000
                
                with open(self.cache_config['cache_file'], 'w', encoding='utf-8') as f:
                    f.write(json_str)
                
                logger.debug(f"📊 Cache persisted with orjson in {persist_time:.1f}ms to {self.cache_config['cache_file']}")
            else:
                # Fallback to standard json
                with open(self.cache_config['cache_file'], 'w') as f:
                    json.dump(cache_data, f, indent=2, default=str)
                
                logger.debug(f"Cache persisted with standard JSON to {self.cache_config['cache_file']}")
                
        except Exception as e:
            logger.error(f"Failed to persist cache: {e}")
    
    def load_cache_from_file(self) -> bool:
        """Load cache from file using orjson if available"""
        try:
            if not os.path.exists(self.cache_config['cache_file']):
                logger.debug(f"No cache file found at {self.cache_config['cache_file']}")
                return False
            
            start_time = datetime.now()
            
            with open(self.cache_config['cache_file'], 'r', encoding='utf-8') as f:
                if ORJSON_AVAILABLE:
                    cache_data = orjson_loads(f.read())
                    load_method = 'orjson'
                else:
                    cache_data = json.load(f)
                    load_method = 'json'
            
            load_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Validate and load cache data
            if isinstance(cache_data, dict) and 'cache' in cache_data:
                loaded_count = 0
                for key, value in cache_data['cache'].items():
                    if key not in ['last_updated', 'cache_metadata']:
                        self.cache[key] = value
                        loaded_count += 1
                
                self.cache['last_updated'] = cache_data.get('timestamp')
                
                logger.info(f"✅ Cache loaded with {load_method} in {load_time:.1f}ms: {loaded_count} entries")
                
                # Check if cache was created with orjson
                if cache_data.get('orjson_available') and not ORJSON_AVAILABLE:
                    logger.warning("⚠️  Cache was created with orjson but orjson is not currently available")
                elif not cache_data.get('orjson_available') and ORJSON_AVAILABLE:
                    logger.info("📊 Cache will be upgraded to orjson on next write")
                
                return True
            
        except Exception as e:
            logger.error(f"Failed to load cache from file: {e}")
        
        return False
    
    def clear_cache(self, networks: Optional[List[str]] = None) -> Dict[str, Any]:
        """Clear cached data with optional network filtering and performance info"""
        cleared_entries = []
        performance_summary = {}
        
        if networks:
            # Clear specific networks
            for network in networks:
                for analysis_type in ['buy', 'sell']:
                    # Handle both old and new key formats
                    if network == 'eth':
                        key = f"ethereum_{analysis_type}"
                    else:
                        key = f"{network}_{analysis_type}"
                    
                    if key in self.cache and self.cache[key]:
                        # Capture performance data before clearing
                        cache_entry = self.cache[key]
                        if isinstance(cache_entry, dict) and cache_entry.get('performance_metrics'):
                            performance_summary[key] = cache_entry['performance_metrics']
                        
                        self.cache[key] = None
                        cleared_entries.append(key)
                        
                        if key in self.cache['cache_metadata']:
                            del self.cache['cache_metadata'][key]
            
            logger.info(f"Cleared cache for networks: {networks}")
        else:
            # Clear all
            valid_keys = self._get_valid_cache_keys()
            for key in valid_keys:
                if self.cache.get(key):
                    # Capture performance data before clearing
                    cache_entry = self.cache[key]
                    if isinstance(cache_entry, dict) and cache_entry.get('performance_metrics'):
                        performance_summary[key] = cache_entry['performance_metrics']
                    
                    self.cache[key] = None
                    cleared_entries.append(key)
            
            self.cache['cache_metadata'] = {}
            self.cache['last_updated'] = None
            
            logger.info("Cleared all cached data")
        
        return {
            'status': 'success',
            'cleared_keys': cleared_entries,
            'performance_summary': performance_summary,
            'orjson_enabled': ORJSON_AVAILABLE
        }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary for all cached data"""
        summary = {
            'orjson_available': ORJSON_AVAILABLE,
            'total_cached_entries': 0,
            'total_cache_size_bytes': 0,
            'average_speedup': 0,
            'cache_entries': {}
        }
        
        speedups = []
        
        for key in self._get_valid_cache_keys():
            cache_entry = self.cache.get(key)
            if cache_entry and isinstance(cache_entry, dict):
                metadata = self.cache['cache_metadata'].get(key, {})
                perf_metrics = cache_entry.get('performance_metrics', {})
                
                entry_summary = {
                    'available': True,
                    'size_bytes': metadata.get('size_estimate', 0),
                    'token_count': metadata.get('token_count', 0),
                    'orjson_optimized': metadata.get('orjson_optimized', False)
                }
                
                if perf_metrics:
                    entry_summary['performance'] = perf_metrics
                    speedup = perf_metrics.get('serialize_speedup', 1.0)
                    speedups.append(speedup)
                
                summary['cache_entries'][key] = entry_summary
                summary['total_cached_entries'] += 1
                summary['total_cache_size_bytes'] += metadata.get('size_estimate', 0)
        
        if speedups:
            summary['average_speedup'] = round(sum(speedups) / len(speedups), 1)
        
        return summary
    
    def _get_valid_cache_keys(self) -> List[str]:
        """Get valid cache keys based on supported networks"""
        keys = []
        for network in settings.monitor.supported_networks:
            network_name = network.value
            # Map eth to ethereum for consistency
            if network_name == 'eth':
                network_name = 'ethereum'
            keys.extend([f'{network_name}_buy', f'{network_name}_sell'])
        return keys
    
    def format_buy_response(self, results: Dict, network: str) -> Dict:
        """Enhanced format buy analysis results with orjson optimization info"""
        # Validate network against settings
        supported_networks = [net.value for net in settings.monitor.supported_networks]
        if network not in supported_networks:
            logger.warning(f"Network {network} not in supported networks: {supported_networks}")
        
        response_data = {
            "status": "success",
            "network": network,
            "analysis_type": "buy",
            "total_purchases": results.get("total_purchases", 0),
            "unique_tokens": results.get("unique_tokens", 0),
            "total_eth_spent": round(results.get("total_eth_spent", 0), 4),
            "total_usd_spent": round(results.get("total_usd_spent", 0), 0),
            "top_tokens": [],
            "platform_summary": results.get("platform_summary", {}),
            "last_updated": datetime.now().isoformat(),
            "config_info": {
                "excluded_tokens_count": len(analysis_config.excluded_tokens),
                "min_eth_value": self._get_network_min_eth_value(network),
                "environment": settings.environment,
                "orjson_optimized": ORJSON_AVAILABLE  # Add orjson status
            }
        }
        
        # Add network-specific data
        if network == "base":
            response_data["base_native_summary"] = results.get("base_native_summary", {})
        
        # Format top tokens (filter excluded tokens)
        all_tokens = results.get("ranked_tokens", [])
        filtered_tokens = self._filter_excluded_tokens(all_tokens)
        response_data["top_tokens"] = self._format_buy_tokens(filtered_tokens)
        
        # Add filtering stats
        response_data["filtering_stats"] = {
            "total_tokens_before_filter": len(all_tokens),
            "tokens_after_filter": len(filtered_tokens),
            "tokens_excluded": len(all_tokens) - len(filtered_tokens)
        }
        
        return response_data
    
    def format_sell_response(self, results: Dict, network: str) -> Dict:
        """Enhanced format sell analysis results with orjson optimization info"""
        # Validate network against settings
        supported_networks = [net.value for net in settings.monitor.supported_networks]
        if network not in supported_networks:
            logger.warning(f"Network {network} not in supported networks: {supported_networks}")
        
        response_data = {
            "status": "success",
            "network": network,
            "analysis_type": "sell",
            "total_sells": results.get("total_sells", 0),
            "unique_tokens": results.get("unique_tokens", 0),
            "total_estimated_eth": round(results.get("total_estimated_eth", 0), 4),
            "top_tokens": [],
            "method_summary": results.get("method_summary", {}),
            "last_updated": datetime.now().isoformat(),
            "config_info": {
                "excluded_tokens_count": len(analysis_config.excluded_tokens),
                "min_eth_value": self._get_network_min_eth_value(network),
                "environment": settings.environment,
                "orjson_optimized": ORJSON_AVAILABLE  # Add orjson status
            }
        }
        
        # Add network-specific data
        if network == "base":
            response_data["base_native_summary"] = results.get("base_native_summary", {})
        
        # Format top tokens (filter excluded tokens)
        all_tokens = results.get("ranked_tokens", [])
        filtered_tokens = self._filter_excluded_tokens(all_tokens)
        response_data["top_tokens"] = self._format_sell_tokens(filtered_tokens)
        
        # Add filtering stats
        response_data["filtering_stats"] = {
            "total_tokens_before_filter": len(all_tokens),
            "tokens_after_filter": len(filtered_tokens),
            "tokens_excluded": len(all_tokens) - len(filtered_tokens)
        }
        
        return response_data
    
    # All your existing methods remain the same, just add this at the end:
    def get_last_updated(self) -> Optional[str]:
        """Get last update timestamp"""
        return self.cache['last_updated']
    
    def _filter_excluded_tokens(self, ranked_tokens: List) -> List:
        """Filter out excluded tokens based on settings"""
        excluded_tokens_upper = [token.upper() for token in analysis_config.excluded_tokens]
        filtered_tokens = []
        
        for token_data in ranked_tokens:
            token_name = token_data[0].upper() if isinstance(token_data, tuple) else str(token_data).upper()
            
            if token_name not in excluded_tokens_upper:
                filtered_tokens.append(token_data)
            else:
                logger.debug(f"Excluded token: {token_name}")
        
        logger.info(f"Filtered {len(ranked_tokens) - len(filtered_tokens)} excluded tokens")
        return filtered_tokens
    
    def _format_buy_tokens(self, ranked_tokens: List) -> List[Dict]:
        """Format buy tokens for API response"""
        formatted_tokens = []
        
        for i, (token, data, score) in enumerate(ranked_tokens[:10], 1):
            # Extract contract addresses
            contract_addresses = set()
            for purchase in data.get("purchases", []):
                ca = purchase.get("contract_address", "")
                if ca:
                    contract_addresses.add(ca)
            
            token_data = {
                "rank": i,
                "token": token,
                "alpha_score": round(score, 2),
                "wallet_count": len(data.get("wallets", [])),
                "total_eth_spent": round(data.get("total_eth_spent", 0), 4),
                "platforms": list(data.get("platforms", [])),
                "contract_address": list(contract_addresses)[0] if contract_addresses else "N/A",
                "avg_wallet_score": self._calculate_avg_wallet_score(data.get("wallet_scores", [])),
                "meets_alert_threshold": self._check_alert_threshold(data, score)
            }
            
            # Add Base-specific fields
            if "is_base_native" in data:
                token_data["is_base_native"] = data.get("is_base_native", False)
            
            formatted_tokens.append(token_data)
        
        return formatted_tokens
    
    def _format_sell_tokens(self, ranked_tokens: List) -> List[Dict]:
        """Format sell tokens for API response"""
        formatted_tokens = []
        
        for i, (token, data, score) in enumerate(ranked_tokens[:10], 1):
            # Extract contract addresses
            contract_addresses = set()
            for sell in data.get("sells", []):
                ca = sell.get("contract_address", "")
                if ca:
                    contract_addresses.add(ca)
            
            token_data = {
                "rank": i,
                "token": token,
                "sell_score": round(score, 2),
                "wallet_count": len(data.get("wallets", [])),
                "total_estimated_eth": round(data.get("total_estimated_eth", 0), 4),
                "methods": list(data.get("methods", [])),
                "platforms": list(data.get("platforms", [])),
                "contract_address": list(contract_addresses)[0] if contract_addresses else "N/A",
                "avg_wallet_score": self._calculate_avg_wallet_score(data.get("wallet_scores", [])),
                "meets_alert_threshold": self._check_sell_alert_threshold(data, score)
            }
            
            # Add Base-specific fields
            if "is_base_native" in data:
                token_data["is_base_native"] = data.get("is_base_native", False)
            
            formatted_tokens.append(token_data)
        
        return formatted_tokens
    
    def _check_alert_threshold(self, data: Dict, alpha_score: float) -> bool:
        """Check if token meets alert thresholds from settings"""
        wallet_count = len(data.get("wallets", []))
        eth_spent = data.get("total_eth_spent", 0)
        
        return (
            wallet_count >= monitor_config.alert_thresholds['min_wallets'] and
            eth_spent >= monitor_config.alert_thresholds['min_eth_spent'] and
            alpha_score >= monitor_config.alert_thresholds['min_alpha_score']
        )
    
    def _check_sell_alert_threshold(self, data: Dict, sell_score: float) -> bool:
        """Check if sell token meets alert thresholds"""
        wallet_count = len(data.get("wallets", []))
        eth_estimated = data.get("total_estimated_eth", 0)
        
        return (
            wallet_count >= monitor_config.alert_thresholds['min_wallets'] and
            eth_estimated >= monitor_config.alert_thresholds['min_eth_spent'] and
            sell_score >= monitor_config.alert_thresholds['min_alpha_score']
        )
    
    def _calculate_avg_wallet_score(self, wallet_scores: List[float]) -> float:
        """Calculate average wallet score"""
        if not wallet_scores:
            return 0.0
        return round(sum(wallet_scores) / len(wallet_scores), 1)
    
    def _extract_network_from_key(self, key: str) -> str:
        """Extract network name from cache key"""
        return key.split('_')[0] if '_' in key else 'unknown'
    
    def _extract_analysis_type_from_key(self, key: str) -> str:
        """Extract analysis type from cache key"""
        return key.split('_')[1] if '_' in key else 'unknown'
    
    def _get_network_min_eth_value(self, network: str) -> float:
        """Get minimum ETH value for network from settings"""
        try:
            network_config = settings.get_network_config(network)
            return network_config['min_eth_value']
        except ValueError:
            logger.warning(f"Unknown network {network}, using default min ETH value")
            return analysis_config.min_eth_value
    
    def _get_config_hash(self) -> str:
        """Generate a hash of current configuration for cache validation"""
        config_data = {
            'excluded_tokens': sorted(analysis_config.excluded_tokens),
            'min_eth_value': analysis_config.min_eth_value,
            'min_eth_value_base': analysis_config.min_eth_value_base,
            'alert_thresholds': monitor_config.alert_thresholds,
            'orjson_available': ORJSON_AVAILABLE
        }
        return str(hash(str(sorted(config_data.items()))))
    
    def _is_cache_expired(self, cache_entry: Dict) -> bool:
        """Check if cache entry is expired"""
        if 'timestamp' not in cache_entry:
            return True
        
        try:
            cache_time = datetime.fromisoformat(cache_entry['timestamp'])
            age_hours = (datetime.now() - cache_time).total_seconds() / 3600
            return age_hours > self.cache_config['max_age_hours']
        except (ValueError, TypeError):
            return True
    
    def _has_config_changed(self, cache_entry: Dict) -> bool:
        """Check if configuration has changed since cache entry was created"""
        if 'config_hash' not in cache_entry:
            return True
        
        return cache_entry['config_hash'] != self._get_config_hash()
    
    def _cleanup_expired_cache(self) -> None:
        """Remove expired cache entries"""
        keys_to_clean = []
        
        for key, cache_entry in self.cache.items():
            if key in ['last_updated', 'cache_metadata']:
                continue
                
            if isinstance(cache_entry, dict) and 'timestamp' in cache_entry:
                if self._is_cache_expired(cache_entry):
                    keys_to_clean.append(key)
        
        for key in keys_to_clean:
            logger.info(f"Cleaning expired cache entry: {key}")
            self.cache[key] = None
            if key in self.cache['cache_metadata']:
                del self.cache['cache_metadata'][key]
    
    def get_summary_stats(self) -> Dict:
        """Get summary statistics across all networks with orjson performance info"""
        stats = {
            "total_tokens_tracked": 0,
            "total_activity": 0,
            "networks_active": 0,
            "last_activity": None,
            "networks_summary": {},
            "settings_info": {
                "environment": settings.environment,
                "supported_networks": [net.value for net in settings.monitor.supported_networks],
                "excluded_tokens_count": len(analysis_config.excluded_tokens),
                "alert_thresholds": monitor_config.alert_thresholds,
                "orjson_optimization": ORJSON_AVAILABLE
            }
        }
        
        # Analyze each supported network
        for network in settings.monitor.supported_networks:
            network_name = network.value
            # Map eth to ethereum
            if network_name == 'eth':
                network_name = 'ethereum'
                
            network_stats = {
                "buy_data": False,
                "sell_data": False,
                "tokens_tracked": 0,
                "activity_count": 0,
                "last_updated": None,
                "orjson_optimized": False
            }
            
            # Check buy data
            buy_key = f"{network_name}_buy"
            buy_data = self.get_cached_data(buy_key)
            if buy_data and buy_data.get('status') == 'success':
                network_stats["buy_data"] = True
                network_stats["tokens_tracked"] += buy_data.get('unique_tokens', 0)
                network_stats["activity_count"] += buy_data.get('total_purchases', 0)
                network_stats["last_updated"] = buy_data.get('last_updated')
                network_stats["orjson_optimized"] = buy_data.get('config_info', {}).get('orjson_optimized', False)
                stats["networks_active"] += 1
            
            # Check sell data
            sell_key = f"{network_name}_sell"
            sell_data = self.get_cached_data(sell_key)
            if sell_data and sell_data.get('status') == 'success':
                network_stats["sell_data"] = True
                network_stats["tokens_tracked"] += sell_data.get('unique_tokens', 0)
                network_stats["activity_count"] += sell_data.get('total_sells', 0)
                if not network_stats["last_updated"] or (sell_data.get('last_updated') and sell_data['last_updated'] > network_stats["last_updated"]):
                    network_stats["last_updated"] = sell_data.get('last_updated')
                    network_stats["orjson_optimized"] = sell_data.get('config_info', {}).get('orjson_optimized', False)
            
            stats["networks_summary"][network_name] = network_stats
            stats["total_tokens_tracked"] += network_stats["tokens_tracked"]
            stats["total_activity"] += network_stats["activity_count"]
            
            # Update overall last activity
            if network_stats["last_updated"]:
                if not stats["last_activity"] or network_stats["last_updated"] > stats["last_activity"]:
                    stats["last_activity"] = network_stats["last_updated"]
        
        return stats
    
    def get_cache_metrics(self) -> Dict:
        """Get detailed cache performance metrics with orjson information"""
        metrics = {
            "cache_size": len([k for k, v in self.cache.items() if v is not None and k not in ['last_updated', 'cache_metadata']]),
            "memory_usage_estimate": sum(len(str(v)) for v in self.cache.values() if v is not None),
            "cache_hit_potential": {},
            "environment": settings.environment,
            "uptime": self._get_service_uptime(),
            "orjson_status": {
                "available": ORJSON_AVAILABLE,
                "enabled": self.cache_config['use_orjson'],
                "performance_benchmarking": self.cache_config['benchmark_performance']
            }
        }
        
        # Calculate cache freshness for each network
        for network in settings.monitor.supported_networks:
            network_name = network.value
            # Map eth to ethereum
            if network_name == 'eth':
                network_name = 'ethereum'
                
            for analysis_type in ['buy', 'sell']:
                key = f"{network_name}_{analysis_type}"
                cache_entry = self.cache.get(key)
                
                if cache_entry and isinstance(cache_entry, dict) and 'timestamp' in cache_entry:
                    try:
                        cache_time = datetime.fromisoformat(cache_entry['timestamp'])
                        age_minutes = (datetime.now() - cache_time).total_seconds() / 60
                        
                        entry_metrics = {
                            "age_minutes": round(age_minutes, 1),
                            "is_fresh": age_minutes < (self.cache_config['max_age_hours'] * 60),
                            "config_current": not self._has_config_changed(cache_entry),
                            "orjson_optimized": cache_entry.get('orjson_available', False),
                            "serialization_method": cache_entry.get('serialization_method', 'json')
                        }
                        
                        # Add performance metrics if available
                        if cache_entry.get('performance_metrics'):
                            entry_metrics["performance"] = cache_entry['performance_metrics']
                        
                        metrics["cache_hit_potential"][key] = entry_metrics
                        
                    except ValueError:
                        metrics["cache_hit_potential"][key] = {"status": "invalid_timestamp"}
                else:
                    metrics["cache_hit_potential"][key] = {"status": "no_data"}
        
        return metrics
    
    def _get_service_uptime(self) -> Optional[str]:
        """Get service uptime (simplified implementation)"""
        if self.cache['last_updated']:
            try:
                first_cache = datetime.fromisoformat(self.cache['last_updated'])
                uptime = datetime.now() - first_cache
                return str(uptime).split('.')[0]  # Remove microseconds
            except ValueError:
                return None
        return None