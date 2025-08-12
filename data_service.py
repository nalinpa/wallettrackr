from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging
import json
import os
from collections import defaultdict

# Import settings
from config.settings import settings, analysis_config, monitor_config

# Configure logger
logger = logging.getLogger(__name__)

class AnalysisService:
    """Service for data processing and caching with settings integration"""
    
    def __init__(self):
        self.cache = {
            'eth_buy': None,
            'eth_sell': None,
            'base_buy': None,
            'base_sell': None,
            'last_updated': None,
            'cache_metadata': {}
        }
        
        # Cache configuration from settings
        self.cache_config = {
            'max_age_hours': 24,  # How long to keep cached data
            'auto_cleanup': True,
            'persist_to_file': False,  # Could be configurable
            'cache_file': 'cache/analysis_cache.json'
        }
        
        logger.info(f"AnalysisService initialized for {settings.environment} environment")
        logger.info(f"Supported networks: {[net.value for net in settings.monitor.supported_networks]}")
    
    def cache_data(self, key: str, data: Dict) -> None:
        """Cache analysis results with metadata"""
        # Validate key against supported networks
        valid_keys = self._get_valid_cache_keys()
        if key not in valid_keys:
            logger.warning(f"Invalid cache key: {key}. Valid keys: {valid_keys}")
            return
        
        # Add metadata
        cache_entry = {
            'data': data,
            'timestamp': datetime.now().isoformat(),
            'environment': settings.environment,
            'config_hash': self._get_config_hash()
        }
        
        self.cache[key] = cache_entry
        self.cache['last_updated'] = datetime.now().isoformat()
        
        # Update metadata
        self.cache['cache_metadata'][key] = {
            'size_estimate': len(str(data)),
            'token_count': data.get('unique_tokens', 0),
            'network': self._extract_network_from_key(key),
            'analysis_type': self._extract_analysis_type_from_key(key)
        }
        
        logger.info(f"Cached data for {key}: {data.get('unique_tokens', 0)} tokens")
        
        # Auto-cleanup if enabled
        if self.cache_config['auto_cleanup']:
            self._cleanup_expired_cache()
        
        # Persist to file if enabled
        if self.cache_config['persist_to_file']:
            self._persist_cache_to_file()
    
    def get_cached_data(self, key: str) -> Optional[Dict]:
        """Get cached data by key with validation"""
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
        
        return cache_entry['data']
    
    def get_cache_status(self) -> Dict[str, Any]:
        """Get detailed status of all cached data"""
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
                    'timestamp': 'unknown'
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
                'metadata': self.cache['cache_metadata'].get(key, {})
            }
        
        # Add overall cache info
        status['_cache_info'] = {
            'last_updated': self.cache['last_updated'],
            'supported_networks': [net.value for net in settings.monitor.supported_networks],
            'environment': settings.environment,
            'auto_cleanup': self.cache_config['auto_cleanup'],
            'max_age_hours': self.cache_config['max_age_hours']
        }
        
        return status
    
    def get_last_updated(self) -> Optional[str]:
        """Get last update timestamp"""
        return self.cache['last_updated']
    
    def format_buy_response(self, results: Dict, network: str) -> Dict:
        """Format buy analysis results for API response with settings integration"""
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
                "environment": settings.environment
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
        """Format sell analysis results for API response with settings integration"""
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
                "environment": settings.environment
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
    
    def _get_valid_cache_keys(self) -> List[str]:
        """Get valid cache keys based on supported networks"""
        keys = []
        for network in settings.monitor.supported_networks:
            keys.extend([f'{network.value}_buy', f'{network.value}_sell'])
        return keys
    
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
            'alert_thresholds': monitor_config.alert_thresholds
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
    
    def _persist_cache_to_file(self) -> None:
        """Save cache to file (if enabled)"""
        try:
            os.makedirs(os.path.dirname(self.cache_config['cache_file']), exist_ok=True)
            
            # Prepare cache data for JSON serialization
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'environment': settings.environment,
                'cache': {}
            }
            
            for key, value in self.cache.items():
                if value is not None and key != 'cache_metadata':
                    cache_data['cache'][key] = value
            
            with open(self.cache_config['cache_file'], 'w') as f:
                json.dump(cache_data, f, indent=2)
                
            logger.debug(f"Cache persisted to {self.cache_config['cache_file']}")
            
        except Exception as e:
            logger.error(f"Failed to persist cache: {e}")
    
    def clear_cache(self, networks: Optional[List[str]] = None) -> Dict[str, Any]:
        """Clear cached data with optional network filtering"""
        if networks:
            # Clear specific networks
            cleared_keys = []
            for network in networks:
                for analysis_type in ['buy', 'sell']:
                    key = f"{network}_{analysis_type}"
                    if key in self.cache:
                        self.cache[key] = None
                        cleared_keys.append(key)
                        if key in self.cache['cache_metadata']:
                            del self.cache['cache_metadata'][key]
            
            logger.info(f"Cleared cache for networks: {networks}")
            return {'status': 'success', 'cleared_keys': cleared_keys}
        else:
            # Clear all
            valid_keys = self._get_valid_cache_keys()
            for key in valid_keys:
                self.cache[key] = None
            
            self.cache['cache_metadata'] = {}
            self.cache['last_updated'] = None
            
            logger.info("Cleared all cached data")
            return {'status': 'success', 'cleared_keys': valid_keys}
    
    def get_summary_stats(self) -> Dict:
        """Get summary statistics across all networks with settings info"""
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
                "alert_thresholds": monitor_config.alert_thresholds
            }
        }
        
        # Analyze each supported network
        for network in settings.monitor.supported_networks:
            network_name = network.value
            network_stats = {
                "buy_data": False,
                "sell_data": False,
                "tokens_tracked": 0,
                "activity_count": 0,
                "last_updated": None
            }
            
            # Check buy data
            buy_key = f"{network_name}_buy"
            buy_data = self.get_cached_data(buy_key)
            if buy_data and buy_data.get('status') == 'success':
                network_stats["buy_data"] = True
                network_stats["tokens_tracked"] += buy_data.get('unique_tokens', 0)
                network_stats["activity_count"] += buy_data.get('total_purchases', 0)
                network_stats["last_updated"] = buy_data.get('last_updated')
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
            
            stats["networks_summary"][network_name] = network_stats
            stats["total_tokens_tracked"] += network_stats["tokens_tracked"]
            stats["total_activity"] += network_stats["activity_count"]
            
            # Update overall last activity
            if network_stats["last_updated"]:
                if not stats["last_activity"] or network_stats["last_updated"] > stats["last_activity"]:
                    stats["last_activity"] = network_stats["last_updated"]
        
        return stats
    
    def get_cache_metrics(self) -> Dict:
        """Get detailed cache performance metrics"""
        metrics = {
            "cache_size": len([k for k, v in self.cache.items() if v is not None and k not in ['last_updated', 'cache_metadata']]),
            "memory_usage_estimate": sum(len(str(v)) for v in self.cache.values() if v is not None),
            "cache_hit_potential": {},
            "environment": settings.environment,
            "uptime": self._get_service_uptime()
        }
        
        # Calculate cache freshness for each network
        for network in settings.monitor.supported_networks:
            network_name = network.value
            for analysis_type in ['buy', 'sell']:
                key = f"{network_name}_{analysis_type}"
                cache_entry = self.cache.get(key)
                
                if cache_entry and isinstance(cache_entry, dict) and 'timestamp' in cache_entry:
                    try:
                        cache_time = datetime.fromisoformat(cache_entry['timestamp'])
                        age_minutes = (datetime.now() - cache_time).total_seconds() / 60
                        metrics["cache_hit_potential"][key] = {
                            "age_minutes": round(age_minutes, 1),
                            "is_fresh": age_minutes < (self.cache_config['max_age_hours'] * 60),
                            "config_current": not self._has_config_changed(cache_entry)
                        }
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