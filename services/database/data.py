import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class AnalysisService:
    """Simplified service for FastAPI compatibility"""
    
    def __init__(self):
        self.cache = {}
        self.cache_duration = 300  # 5 minutes
        logger.info("AnalysisService initialized for FastAPI")
    
    def get_cached_data(self, cache_key: str) -> Optional[Dict]:
        """Get cached analysis data if still valid"""
        if cache_key in self.cache:
            cached_item = self.cache[cache_key]
            if time.time() - cached_item['timestamp'] < self.cache_duration:
                logger.info(f"Returning cached data for {cache_key}")
                return cached_item['data']
            else:
                # Remove expired cache
                del self.cache[cache_key]
                logger.info(f"Expired cache removed for {cache_key}")
        return None
    
    def cache_data(self, cache_key: str, data: Dict) -> None:
        """Cache analysis data"""
        self.cache[cache_key] = {
            'data': data,
            'timestamp': time.time()
        }
        logger.info(f"Cached data for {cache_key}")
    
    def clear_cache(self) -> None:
        """Clear all cached data"""
        self.cache.clear()
        logger.info("Cache cleared")
    
    def format_buy_response(self, results: Dict, network: str) -> Dict:
        """Format buy analysis results for API response"""
        try:
            ranked_tokens = results.get('ranked_tokens', [])
            platform_summary = results.get('platform_summary', {})
            web3_analysis = results.get('web3_analysis', {})
            
            # Format top tokens - handle the tuple format (token, data, score)
            top_tokens = []
            for i, token_tuple in enumerate(ranked_tokens[:20]):  # Top 20
                try:
                    if isinstance(token_tuple, tuple) and len(token_tuple) >= 3:
                        token_name, token_data, alpha_score = token_tuple
                    else:
                        logger.warning(f"Unexpected token format: {token_tuple}")
                        continue
                    
                    purchases = token_data.get('purchases', [])
                    platforms = list(token_data.get('platforms', set()))
                    
                    # Get contract address from first purchase
                    contract_address = ""
                    if purchases and isinstance(purchases, list) and len(purchases) > 0:
                        contract_address = purchases[0].get('contract_address', '')
                    
                    # Calculate average wallet score
                    wallet_scores = token_data.get('wallet_scores', [])
                    avg_wallet_score = sum(wallet_scores) / len(wallet_scores) if wallet_scores else 0
                    
                    # Get sophistication score if available
                    sophistication_scores = token_data.get('sophistication_scores', [])
                    avg_sophistication = sum(sophistication_scores) / len(sophistication_scores) if sophistication_scores else None
                    
                    token_analysis = {
                        "rank": i + 1,
                        "token": token_name,
                        "alpha_score": round(float(alpha_score), 2),
                        "wallet_count": len(token_data.get('wallets', set())),
                        "total_eth_spent": round(float(token_data.get('total_eth_spent', 0)), 4),
                        "platforms": platforms,
                        "contract_address": contract_address,
                        "avg_wallet_score": round(float(avg_wallet_score), 2),
                        "sophistication_score": round(float(avg_sophistication), 2) if avg_sophistication else None,
                        "is_base_native": token_data.get('is_base_native', False) if network == 'base' else None
                    }
                    
                    top_tokens.append(token_analysis)
                    
                except Exception as e:
                    logger.error(f"Error formatting token {i}: {e}")
                    continue
            
            # Format Web3 enhanced data if available
            web3_enhanced_data = None
            web3_enhanced = bool(web3_analysis)
            
            if web3_enhanced:
                web3_enhanced_data = {
                    "total_transactions_analyzed": web3_analysis.get('total_transactions_analyzed', 0),
                    "sophisticated_transactions": web3_analysis.get('sophisticated_transactions', 0),
                    "method_distribution": web3_analysis.get('method_distribution', {}),
                    "avg_sophistication": web3_analysis.get('avg_sophistication', 0.0),
                    "gas_efficiency_avg": web3_analysis.get('gas_efficiency_avg', 0.0)
                }
            
            response = {
                "status": "success",
                "network": network,
                "analysis_type": "buy",
                "total_purchases": results.get('total_purchases', 0),
                "unique_tokens": results.get('unique_tokens', 0),
                "total_eth_spent": round(float(results.get('total_eth_spent', 0)), 4),
                "total_usd_spent": round(float(results.get('total_usd_spent', 0)), 0),
                "top_tokens": top_tokens,
                "platform_summary": platform_summary,
                "web3_analysis": web3_enhanced_data,
                "web3_enhanced": web3_enhanced,
                "orjson_enabled": True,
                "analysis_time_seconds": 0.0,  # Will be set by caller
                "last_updated": datetime.now()
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Error formatting buy response: {e}")
            return {
                "status": "error",
                "network": network,
                "analysis_type": "buy",
                "total_purchases": 0,
                "unique_tokens": 0,
                "total_eth_spent": 0.0,
                "total_usd_spent": 0.0,
                "top_tokens": [],
                "platform_summary": {},
                "web3_analysis": None,
                "web3_enhanced": False,
                "orjson_enabled": True,
                "analysis_time_seconds": 0.0,
                "last_updated": datetime.now(),
                "error": str(e)
            }
    
    def format_sell_response(self, results: Dict, network: str) -> Dict:
        """Format sell analysis results for API response"""
        try:
            ranked_tokens = results.get('ranked_tokens', [])
            method_summary = results.get('method_summary', {})
            web3_analysis = results.get('web3_analysis', {})
            
            # Format top tokens - handle the tuple format (token, data, score)
            top_tokens = []
            for i, token_tuple in enumerate(ranked_tokens[:20]):  # Top 20
                try:
                    if isinstance(token_tuple, tuple) and len(token_tuple) >= 3:
                        token_name, token_data, sell_score = token_tuple
                    else:
                        logger.warning(f"Unexpected token format: {token_tuple}")
                        continue
                    
                    sells = token_data.get('sells', [])
                    methods = list(token_data.get('methods', set()))
                    
                    # Get contract address from first sell
                    contract_address = ""
                    if sells and isinstance(sells, list) and len(sells) > 0:
                        contract_address = sells[0].get('contract_address', '')
                    
                    # Calculate average wallet score
                    wallet_scores = token_data.get('wallet_scores', [])
                    avg_wallet_score = sum(wallet_scores) / len(wallet_scores) if wallet_scores else 0
                    
                    # Get sophistication score if available
                    sophistication_scores = token_data.get('sophistication_scores', [])
                    avg_sophistication = sum(sophistication_scores) / len(sophistication_scores) if sophistication_scores else None
                    
                    token_analysis = {
                        "rank": i + 1,
                        "token": token_name,
                        "alpha_score": round(float(sell_score), 2),  # Using alpha_score field for consistency
                        "wallet_count": len(token_data.get('wallets', set())),
                        "total_eth_spent": round(float(token_data.get('total_estimated_eth', 0)), 4),
                        "platforms": methods,  # Using methods as platforms for sells
                        "contract_address": contract_address,
                        "avg_wallet_score": round(float(avg_wallet_score), 2),
                        "sophistication_score": round(float(avg_sophistication), 2) if avg_sophistication else None,
                        "is_base_native": token_data.get('is_base_native', False) if network == 'base' else None
                    }
                    
                    top_tokens.append(token_analysis)
                    
                except Exception as e:
                    logger.error(f"Error formatting sell token {i}: {e}")
                    continue
            
            # Format Web3 enhanced data if available
            web3_enhanced_data = None
            web3_enhanced = bool(web3_analysis)
            
            if web3_enhanced:
                web3_enhanced_data = {
                    "total_transactions_analyzed": web3_analysis.get('total_transactions_analyzed', 0),
                    "sophisticated_transactions": web3_analysis.get('sophisticated_sells', 0),
                    "method_distribution": web3_analysis.get('method_distribution', {}),
                    "avg_sophistication": web3_analysis.get('avg_sophistication', 0.0),
                    "gas_efficiency_avg": web3_analysis.get('avg_gas_efficiency', 0.0)
                }
            
            response = {
                "status": "success", 
                "network": network,
                "analysis_type": "sell",
                "total_sells": results.get('total_sells', 0),
                "unique_tokens": results.get('unique_tokens', 0),
                "total_estimated_eth": round(float(results.get('total_estimated_eth', 0)), 4),
                "top_tokens": top_tokens,
                "method_summary": method_summary,
                "web3_analysis": web3_enhanced_data,
                "web3_enhanced": web3_enhanced,
                "orjson_enabled": True,
                "analysis_time_seconds": 0.0,  # Will be set by caller
                "last_updated": datetime.now()
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Error formatting sell response: {e}")
            return {
                "status": "error",
                "network": network,
                "analysis_type": "sell",
                "total_sells": 0,
                "unique_tokens": 0,
                "total_estimated_eth": 0.0,
                "top_tokens": [],
                "method_summary": {},
                "web3_analysis": None,
                "web3_enhanced": False,
                "orjson_enabled": True,
                "analysis_time_seconds": 0.0,
                "last_updated": datetime.now(),
                "error": str(e)
            }
    
    def get_cache_status(self) -> Dict[str, Any]:
        """Get status of all cached data"""
        status = {}
        
        for key, cached_item in self.cache.items():
            if cached_item:
                age_seconds = time.time() - cached_item['timestamp']
                status[key] = {
                    "available": True,
                    "age_seconds": round(age_seconds, 1),
                    "is_fresh": age_seconds < self.cache_duration,
                    "timestamp": datetime.fromtimestamp(cached_item['timestamp']).isoformat()
                }
            else:
                status[key] = {
                    "available": False,
                    "status": "empty"
                }
        
        return status