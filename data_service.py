from datetime import datetime
from typing import Dict, List, Any, Optional

class AnalysisService:
    """Service for data processing and caching"""
    
    def __init__(self):
        self.cache = {
            'eth_buy': None,
            'eth_sell': None,
            'base_buy': None,
            'base_sell': None,
            'last_updated': None
        }
    
    def cache_data(self, key: str, data: Dict) -> None:
        """Cache analysis results"""
        self.cache[key] = data
        self.cache['last_updated'] = datetime.now().isoformat()
    
    def get_cached_data(self, key: str) -> Optional[Dict]:
        """Get cached data by key"""
        return self.cache.get(key)
    
    def get_cache_status(self) -> Dict[str, bool]:
        """Get status of all cached data"""
        return {
            "eth_buy": self.cache['eth_buy'] is not None,
            "eth_sell": self.cache['eth_sell'] is not None,
            "base_buy": self.cache['base_buy'] is not None,
            "base_sell": self.cache['base_sell'] is not None,
        }
    
    def get_last_updated(self) -> Optional[str]:
        """Get last update timestamp"""
        return self.cache['last_updated']
    
    def format_buy_response(self, results: Dict, network: str) -> Dict:
        """Format buy analysis results for API response"""
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
            "last_updated": datetime.now().isoformat()
        }
        
        # Add network-specific data
        if network == "base":
            response_data["base_native_summary"] = results.get("base_native_summary", {})
        
        # Format top tokens
        response_data["top_tokens"] = self._format_buy_tokens(results.get("ranked_tokens", []))
        
        return response_data
    
    def format_sell_response(self, results: Dict, network: str) -> Dict:
        """Format sell analysis results for API response"""
        response_data = {
            "status": "success",
            "network": network,
            "analysis_type": "sell",
            "total_sells": results.get("total_sells", 0),
            "unique_tokens": results.get("unique_tokens", 0),
            "total_estimated_eth": round(results.get("total_estimated_eth", 0), 4),
            "top_tokens": [],
            "method_summary": results.get("method_summary", {}),
            "last_updated": datetime.now().isoformat()
        }
        
        # Add network-specific data
        if network == "base":
            response_data["base_native_summary"] = results.get("base_native_summary", {})
        
        # Format top tokens
        response_data["top_tokens"] = self._format_sell_tokens(results.get("ranked_tokens", []))
        
        return response_data
    
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
                "avg_wallet_score": self._calculate_avg_wallet_score(data.get("wallet_scores", []))
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
                "avg_wallet_score": self._calculate_avg_wallet_score(data.get("wallet_scores", []))
            }
            
            # Add Base-specific fields
            if "is_base_native" in data:
                token_data["is_base_native"] = data.get("is_base_native", False)
            
            formatted_tokens.append(token_data)
        
        return formatted_tokens
    
    def _calculate_avg_wallet_score(self, wallet_scores: List[float]) -> float:
        """Calculate average wallet score"""
        if not wallet_scores:
            return 0.0
        return round(sum(wallet_scores) / len(wallet_scores), 1)
    
    def clear_cache(self) -> None:
        """Clear all cached data"""
        for key in self.cache:
            self.cache[key] = None
    
    def get_summary_stats(self) -> Dict:
        """Get summary statistics across all networks"""
        stats = {
            "total_tokens_tracked": 0,
            "total_activity": 0,
            "networks_active": 0,
            "last_activity": None
        }
        
        for key in ['eth_buy', 'eth_sell', 'base_buy', 'base_sell']:
            data = self.cache.get(key)
            if data and data.get('status') == 'success':
                stats["networks_active"] += 1
                
                if 'total_purchases' in data:
                    stats["total_activity"] += data['total_purchases']
                elif 'total_sells' in data:
                    stats["total_activity"] += data['total_sells']
                
                stats["total_tokens_tracked"] += data.get('unique_tokens', 0)
                
                if data.get('last_updated'):
                    if not stats["last_activity"] or data['last_updated'] > stats["last_activity"]:
                        stats["last_activity"] = data['last_updated']
        
        return stats