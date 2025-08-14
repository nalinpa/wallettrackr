import requests
import pymongo
from datetime import datetime, timedelta
import time
import json
import os
import math
import logging
from typing import List, Dict, Optional, Tuple
from abc import ABC, abstractmethod

# Import settings
from config.settings import settings, alchemy_config, analysis_config

logger = logging.getLogger(__name__)

class NetworkConfig:
    """Network configuration helper"""
    
    @staticmethod
    def get_config(network: str) -> Dict:
        """Get configuration for a specific network"""
        return settings.get_network_config(network)
    
    @staticmethod
    def get_alchemy_url(network: str) -> str:
        """Get Alchemy URL for network"""
        config = NetworkConfig.get_config(network)
        return config['alchemy_url']
    
    @staticmethod
    def get_min_eth_value(network: str) -> float:
        """Get minimum ETH value for network"""
        config = NetworkConfig.get_config(network)
        return config['min_eth_value']

class TokenUtils:
    """Centralized token utilities"""
    
    @staticmethod
    def is_valid_token_symbol(token_symbol: Optional[str]) -> bool:
        """Check if token symbol is valid (not None/empty)"""
        return bool(token_symbol and isinstance(token_symbol, str) and token_symbol.strip())
    
    @staticmethod
    def should_exclude_token(token_symbol: Optional[str]) -> bool:
        """Check if token should be excluded based on settings"""
        if not TokenUtils.is_valid_token_symbol(token_symbol):
            return True  # Exclude invalid tokens
        
        return token_symbol.upper() in [t.upper() for t in analysis_config.excluded_tokens]
    
    @staticmethod
    def is_interesting_token(token_symbol: Optional[str]) -> bool:
        """Check if token is interesting for alpha discovery"""
        if not TokenUtils.is_valid_token_symbol(token_symbol):
            return False
        
        # Check if excluded
        if TokenUtils.should_exclude_token(token_symbol):
            return False
        
        token_lower = token_symbol.lower()
        
        # Skip LP tokens
        lp_patterns = ["-lp", "lp-", "slp", "uni-v2", "uni-lp", "aero-lp", "cake-lp"]
        if any(pattern in token_lower for pattern in lp_patterns):
            return False
        
        # Skip DeFi derivative tokens
        if len(token_lower) > 4:
            for prefix in ["a", "c", "y", "v", "s"]:
                if token_lower.startswith(prefix):
                    base_token = token_lower[1:] if prefix != "cb" else token_lower[2:]
                    if base_token in [t.lower() for t in analysis_config.excluded_tokens]:
                        return False
        
        return True
    
    @staticmethod
    def estimate_usd_value(amount: float, token: Optional[str], network: str = "ethereum") -> float:
        """Estimate USD value for any token on any network"""
        if not TokenUtils.is_valid_token_symbol(token) or amount <= 0:
            return 0.0
        
        # Network-agnostic price mapping
        prices = {
            # ETH variants
            "ETH": 2000, "WETH": 2000, "cbETH": 2000, "wstETH": 2200, "rETH": 2000,
            "stETH": 2000, "frxETH": 2000, "sfrxETH": 2000,
            
            # BTC variants
            "WBTC": 35000, "BTC": 35000, "cbBTC": 35000, "tBTC": 35000,
            
            # Stablecoins
            "USDC": 1, "USDT": 1, "DAI": 1, "USDbC": 1, "FRAX": 1, "BUSD": 1,
            
            # Base-specific tokens
            "AERO": 1.50, "BALD": 0.05, "TOSHI": 0.0001, "BRETT": 0.15,
            "DEGEN": 0.02, "HIGHER": 0.03,
            
            # Other major tokens
            "UNI": 8, "LINK": 15, "AAVE": 100, "CRV": 0.5, "SNX": 3,
        }
        
        price = prices.get(token.upper(), 0.001)  # Default to $0.001 for unknown
        return amount * price

class ContractUtils:
    """Contract identification utilities"""
    
    # Consolidated known contracts for all networks
    KNOWN_CONTRACTS = {
        # Ethereum contracts
        "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": {"name": "Uniswap V2 Router", "type": "DEX", "platform": "Uniswap"},
        "0xe592427a0aece92de3edee1f18e0157c05861564": {"name": "Uniswap V3 Router", "type": "DEX", "platform": "Uniswap"},
        "0x1111111254eeb25477b68fb85ed929f73a960582": {"name": "1inch V5 Router", "type": "DEX", "platform": "1inch"},
        "0x3328f7f4a1d1c57c35df56bbf0c9dcafca309c49": {"name": "Banana Gun Router", "type": "TELEGRAM_BOT", "platform": "Banana Gun"},
        
        # Base contracts
        "0x2626664c2603336e57b271c5c0b26f421741e481": {"name": "Uniswap V3 SwapRouter", "type": "DEX", "platform": "Uniswap V3"},
        "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43": {"name": "Aerodrome Router", "type": "DEX", "platform": "Aerodrome"},
        "0x327df1e6de05895d2ab08513aadd9313fe505d86": {"name": "BaseSwap Router", "type": "DEX", "platform": "BaseSwap"},
    }
    
    @staticmethod
    def get_contract_info(address: str) -> Dict[str, str]:
        """Get contract information for any address"""
        if not address:
            return {"name": "Unknown", "type": "UNKNOWN", "platform": "Unknown"}
        
        address_lower = address.lower()
        
        # Check known contracts
        if address_lower in ContractUtils.KNOWN_CONTRACTS:
            return ContractUtils.KNOWN_CONTRACTS[address_lower]
        
        # Heuristic detection
        platform = ContractUtils._identify_platform_heuristic(address_lower)
        contract_type = ContractUtils._determine_contract_type(platform)
        
        return {
            "name": f"{platform} Contract",
            "type": contract_type,
            "platform": platform
        }
    
    @staticmethod
    def _identify_platform_heuristic(address: str) -> str:
        """Identify platform using address patterns"""
        # Uniswap patterns
        if any(addr in address for addr in ["7a250d", "e59242", "68b346", "ef1c6e", "3fc91a", "262664"]):
            return "Uniswap"
        
        # 1inch patterns
        if "1111111254" in address:
            return "1inch"
        
        # Base DEX patterns
        if "cf77a3ba" in address:
            return "Aerodrome"
        if "327df1e6" in address:
            return "BaseSwap"
        
        # Bot patterns
        if address.startswith("0x3328") or address.startswith("0x3723"):
            return "Banana Gun (Possible)"
        if address.startswith("0x80a6"):
            return "Maestro Bot (Possible)"
        if address.startswith("0x1337") or address.startswith("0x7777"):
            return "Unknown Trading Bot"
        
        # High entropy = likely contract
        if len(set(address[2:])) >= 12:
            return "Unknown Trading Contract"
        
        return "Unknown Contract"
    
    @staticmethod
    def _determine_contract_type(platform: str) -> str:
        """Determine contract type from platform name"""
        if any(word in platform.lower() for word in ["bot", "gun", "maestro"]):
            return "TELEGRAM_BOT"
        elif any(word in platform.lower() for word in ["aggregator", "dex", "swap"]):
            return "DEX"
        else:
            return "UNKNOWN"

class BaseTracker(ABC):
    """Centralized base tracker with all common functionality"""
    
    def __init__(self, network: str):
        self.network = network
        self.network_config = NetworkConfig.get_config(network)
        self.alchemy_url = self.network_config['alchemy_url']
        self.min_eth_value = self.network_config['min_eth_value']
        
        # Database connection
        self.mongo_client = pymongo.MongoClient(settings.database.mongo_uri)
        self.db = self.mongo_client[settings.database.db_name]
        self.wallets_collection = self.db[settings.database.wallets_collection]
        
        logger.info(f"Initialized {network} tracker with min ETH: {self.min_eth_value}")
    
    def safe_float_conversion(self, value, default=0.0):
        """Safely convert value to float, handling None and invalid values"""
        if value is None:
            return default
        
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"Could not convert value to float: {value} (type: {type(value)})")
            return default

    def make_alchemy_request(self, method: str, params: List) -> Dict:
        """Make request to Alchemy API"""
        payload = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        try:
            response = requests.post(
                self.alchemy_url, 
                json=payload, 
                timeout=alchemy_config.timeout_seconds
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Alchemy API error for {self.network}: {e}")
            return {}
    
    def get_recent_block_range(self, days_back: float = 1) -> Tuple[str, str]:
        """Get block range for recent days"""
        try:
            current_block_result = self.make_alchemy_request("eth_blockNumber", [])
            
            if not current_block_result.get("result"):
                logger.warning(f"Could not get current block for {self.network}")
                return "0x0", "0x0"
                
            current_block = int(current_block_result["result"], 16)
            
            # Network-specific block times
            if self.network == "base":
                blocks_per_day = 43200  # ~2 second blocks
            else:
                blocks_per_day = 7200   # ~12 second blocks
            
            blocks_back = int(days_back * blocks_per_day)
            start_block = max(0, current_block - blocks_back)
            
            logger.debug(f"{self.network} block range: {start_block} to {current_block} ({blocks_back} blocks)")
            return hex(start_block), hex(current_block)
            
        except Exception as e:
            logger.error(f"Error calculating {self.network} block range: {e}")
            return "0x0", "0x0"
        
    def is_significant_purchase(self, transfer: Dict) -> bool:
        """Check if purchase meets minimum value threshold"""
        asset = transfer.get("asset", "")
        value = transfer.get("value", 0)
        
        try:
            value_float = float(value) if value is not None else 0.0
        except (ValueError, TypeError):
            return False
        
        if asset == "ETH":
            return value_float >= self.min_eth_value
        else:
            # Estimate value for other tokens
            estimated_usd = TokenUtils.estimate_usd_value(value_float, asset, self.network)
            estimated_eth = estimated_usd / 2000
            threshold_multiplier = 0.5 if self.network == "base" else 1.0
            return estimated_eth >= (self.min_eth_value * threshold_multiplier)
    
    def is_interesting_token(self, token_symbol: str) -> bool:
        """Check if token is interesting - uses centralized logic"""
        return TokenUtils.is_interesting_token(token_symbol)
    
    def should_exclude_token(self, token_symbol: str) -> bool:
        """Check if token should be excluded - uses centralized logic"""
        return TokenUtils.should_exclude_token(token_symbol)
    
    def estimate_usd_value(self, amount: float, token: str) -> float:
        """Estimate USD value - uses centralized logic"""
        return TokenUtils.estimate_usd_value(amount, token, self.network)
    
    def get_contract_info(self, address: str) -> Dict[str, str]:
        """Get contract info - uses centralized logic"""
        return ContractUtils.get_contract_info(address)
    
    def get_top_wallets(self, num_wallets: int = 173) -> List[Dict]:
        """Get top wallets from database"""   
        smart_wallets_count = self.wallets_collection.count_documents({})
        print(f"Total smart wallets: {smart_wallets_count}") 
        print(f"Wallet collection: {self.db[settings.database.wallets_collection]}")     
        return list(self.wallets_collection.find().sort('score', 1).limit(num_wallets).max_time_ms(30000))
    
    def test_connection(self) -> bool:
        """Test connection to network"""
        logger.info(f"Testing {self.network} connection...")
        
        try:
            result = self.make_alchemy_request("eth_blockNumber", [])
            if result.get("result"):
                current_block = int(result["result"], 16)
                logger.info(f"✅ Connected to {self.network} - Current block: {current_block}")
                return True
            else:
                logger.error(f"❌ Failed to connect to {self.network}")
                return False
        except Exception as e:
            logger.error(f"❌ {self.network} connection error: {e}")
            return False
    
    def calculate_score_components(self, wallet_scores: List[float], max_possible_score: float = 300) -> Dict:
        """Calculate weighted consensus components"""
        if not wallet_scores:
            return {"weighted_consensus": 0.0, "wallet_count": 0}
        
        weighted_consensus_score = 0.0
        
        for wallet_score in wallet_scores:
            wallet_quality_weight = (max_possible_score - wallet_score + 100) / 100
            weighted_consensus_score += wallet_quality_weight
        
        # Bonus for multiple wallets
        wallet_count = len(wallet_scores)
        if wallet_count > 1:
            consensus_bonus = math.log(wallet_count) * 0.5
            weighted_consensus_score = weighted_consensus_score + (weighted_consensus_score * consensus_bonus)
        
        return {
            "weighted_consensus": weighted_consensus_score,
            "wallet_count": wallet_count,
            "best_wallet_score": min(wallet_scores),
            "avg_wallet_score": sum(wallet_scores) / len(wallet_scores)
        }
    
    # Abstract methods that specific trackers must implement
    @abstractmethod
    def analyze_wallet_purchases(self, wallet_address: str, days_back: int) -> List[Dict]:
        """Analyze purchases for a single wallet"""
        pass
    
    @abstractmethod
    def analyze_all_trading_methods(self, num_wallets: int, days_back: int) -> Dict:
        """Analyze all trading methods"""
        pass

class NetworkSpecificMixins:
    """Network-specific functionality"""
    
    class BaseMixin:
        """Base network specific methods"""
        
        @staticmethod
        def is_base_native_token(token_symbol: str) -> bool:
            """Check if token is native to Base ecosystem"""
            if not TokenUtils.is_valid_token_symbol(token_symbol):
                return False
            
            base_native_tokens = {
                "AERO", "BALD", "TOSHI", "BRETT", "NORMIE", "DEGEN", 
                "HIGHER", "MOCHI", "SEAM", "SPEC", "WELL", "EXTRA"
            }
            return token_symbol.upper() in base_native_tokens
    
    class EthereumMixin:
        """Ethereum network specific methods"""
        
        @staticmethod
        def is_major_defi_token(token_symbol: str) -> bool:
            """Check if token is a major DeFi token"""
            if not TokenUtils.is_valid_token_symbol(token_symbol):
                return False
            
            major_defi = {
                "AAVE", "UNI", "SUSHI", "CRV", "CVX", "BAL", "YFI", 
                "SNX", "MKR", "COMP", "PENDLE", "LDO", "FXS"
            }
            return token_symbol.upper() in major_defi