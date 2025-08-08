import pymongo
from datetime import datetime, timedelta
import time
import requests
import json
import os
import math
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

# Configuration for Base Network
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')
ALCHEMY_URL = f"https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
MONGO_URI = 'mongodb://localhost:27017'
DB_NAME = 'crypto_tracker'
WALLETS_COLLECTION = 'smart_wallets'

# Minimum transaction value filter (in ETH/Base ETH)  
MIN_ETH_VALUE = 0.01  # Much lower threshold for Base due to cheaper gas

# Tokens to exclude from analysis - Base specific
EXCLUDED_TOKENS = {
    # Stablecoins on Base
    "USDC", "USDbC", "USDT", "DAI", "DOLA", "axlUSDC", "crvUSD",
    
    # Wrapped tokens on Base
    "ETH", "WETH", "cbETH", "wstETH", "rETH",
    
    # Major bridged tokens (usually not alpha on Base)
    "WBTC", "tBTC", "cbBTC",
    
    # Major DeFi tokens on Base
    "AAVE", "UNI", "SUSHI", "CRV", "CVX", "BAL", "COMP", "SNX",
    "PENDLE", "LDO", "FXS", "MKR",
    
    # Base ecosystem tokens (established)
    "BALD", "TOSHI", "BRETT", "NORMIE", "DEGEN", "HIGHER", "MOCHI",
    "PRIME", "SEAM", "SPEC", "WELL", "AERO", "EXTRA",
    
    # LP and derivative tokens
    "AERO-LP", "UNI-LP", "SUSHI-LP", "CAKE-LP", "SPICE-LP",
    "aUSDC", "cUSDC", "yUSDC", "sUSDC",
    
    # Gaming/NFT tokens (often farmed)
    "MANA", "SAND", "ENJ", "AXS", "CHZ", "GALA", "IMX",
    
    # Governance tokens
    "veCRV", "veBAL", "vlCVX", "xSUSHI", "veFXS",
}

# Convert to lowercase for case-insensitive matching
EXCLUDED_TOKENS_LOWER = {token.lower() for token in EXCLUDED_TOKENS}

# Known DEX and contract addresses on Base - INCLUDING TELEGRAM BOTS
KNOWN_CONTRACTS = {
    # Uniswap V3 on Base (verified addresses)
    "0x2626664c2603336e57b271c5c0b26f421741e481": {"name": "Uniswap V3 SwapRouter", "type": "DEX", "platform": "Uniswap V3"},
    "0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24": {"name": "Uniswap Universal Router", "type": "DEX", "platform": "Uniswap"},
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": {"name": "Uniswap Universal Router", "type": "DEX", "platform": "Uniswap"},
    
    # Aerodrome (Base's main DEX) - let's add more addresses
    "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43": {"name": "Aerodrome Router", "type": "DEX", "platform": "Aerodrome"},
    "0x06374f57991c6ae827db5b8c5a8316c6e207e5db": {"name": "Aerodrome Factory", "type": "DEX", "platform": "Aerodrome"},
    "0x827922686190790b37229fd06084350e74485b72": {"name": "Aerodrome Router V2", "type": "DEX", "platform": "Aerodrome"},
    
    # BaseSwap
    "0x327df1e6de05895d2ab08513aadd9313fe505d86": {"name": "BaseSwap Router", "type": "DEX", "platform": "BaseSwap"},
    "0x8909dc15e40173ff4699343b6eb8132c65e18ec6": {"name": "BaseSwap Factory", "type": "DEX", "platform": "BaseSwap"},
    
    # SushiSwap on Base  
    "0x6bded42c906e69b412ca037f01db3fa68b2de1a4": {"name": "SushiSwap Router", "type": "DEX", "platform": "SushiSwap"},
    "0x71524b4f93c58fcbf659783284e38825f0622859": {"name": "SushiSwap V2 Router", "type": "DEX", "platform": "SushiSwap"},
    
    # PancakeSwap on Base
    "0x678aa4bf4e210cf2166753e054d5b7c31cc7fa86": {"name": "PancakeSwap Router", "type": "DEX", "platform": "PancakeSwap"},
    "0x1b81d678ffb9c0263b24a97847620c99d213eb14": {"name": "PancakeSwap Smart Router", "type": "DEX", "platform": "PancakeSwap"},
    
    # 1inch on Base
    "0x1111111254eeb25477b68fb85ed929f73a960582": {"name": "1inch V5 Router", "type": "DEX", "platform": "1inch"},
    "0x1111111254fb6c44bac0bed2854e76f90643097d": {"name": "1inch V4 Router", "type": "DEX", "platform": "1inch"},
    
    # More DEX Aggregators and popular contracts
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff": {"name": "0x Protocol", "type": "DEX", "platform": "0x Protocol"},
    "0x881d40237659c251811cec9c364ef91dc08d300c": {"name": "Metamask Swap Router", "type": "DEX", "platform": "Metamask"},
    
    # BASE TELEGRAM TRADING BOTS (Updated addresses for Base)
    "0x3328f7f4a1d1c57c35df56bbf0c9dcafca309c49": {"name": "Banana Gun Router", "type": "TELEGRAM_BOT", "platform": "Banana Gun"},
    "0x37238dc7835c77449e5a2a96eb5f4ad0d5b0c8f9": {"name": "Banana Gun Bot", "type": "TELEGRAM_BOT", "platform": "Banana Gun"},
    "0x80a64c6d7f12c47b7c66c5b4e20e72bc1fcd5d9e": {"name": "Maestro Bot", "type": "TELEGRAM_BOT", "platform": "Maestro Bot"},
    
    # BASEDBOT - need to find actual contract addresses (these are placeholders)
    "0x0000000000000000000000000000000000000000": {"name": "BasedBot Router", "type": "TELEGRAM_BOT", "platform": "BasedBot"},
    
    # SIGMA BOT - need to find actual contract addresses (these are placeholders)
    "0x0000000000000000000000000000000000000001": {"name": "Sigma Bot Router", "type": "TELEGRAM_BOT", "platform": "Sigma Bot"},
    
    # Other Base trading bots (add as we discover them)
    "0x58d65748bf38b4b2b4d31bac2ba07a7b4a6ad9b9": {"name": "Base Trading Bot", "type": "TELEGRAM_BOT", "platform": "Unknown Bot"},
    "0x7122db0ebe4eb9b434a9f2ffe6760bc03bfbd0e0": {"name": "Base MEV Bot", "type": "TELEGRAM_BOT", "platform": "MEV Bot"},
    
    # Permit2 (common utility)
    "0x000000000022d473030f116ddee9f6b43ac78ba3": {"name": "Permit2", "type": "UTILITY", "platform": "Permit2"},
    
    # Base Bridge contracts
    "0x4200000000000000000000000000000000000010": {"name": "Base L2 Standard Bridge", "type": "BRIDGE", "platform": "Base Bridge"},
    "0x3154cf16ccdb4c6d922629664174b904d80f2c35": {"name": "Base Portal", "type": "BRIDGE", "platform": "Base Bridge"},
    
    # Other Base DeFi protocols
    "0x4621b7a9c75199271f773ebd9a499dbd165c3191": {"name": "Compound Router", "type": "LENDING", "platform": "Compound"},
    "0x46e6b214b524310239732d51387075e0e70970bf": {"name": "Seamless Protocol", "type": "LENDING", "platform": "Seamless"},
    
    # Base-specific copy trading platforms
    "0x0000000000000000000000000000000000000002": {"name": "Copy Trading Platform", "type": "COPY_TRADING", "platform": "Base Copy"},
    
    # Allow any contract that looks like a router/swap (more permissive for Base bots)
    # We'll discover actual addresses by monitoring transactions
}

class BaseTracker:
    """Base class with shared functionality for Base network trackers"""
    
    def __init__(self):
        self.mongo_client = pymongo.MongoClient(MONGO_URI)
        self.db = self.mongo_client[DB_NAME]
        self.wallets_collection = self.db[WALLETS_COLLECTION]
        
    def make_alchemy_request(self, method: str, params: List) -> Dict:
        """Make request to Alchemy API for Base network"""
        payload = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        try:
            response = requests.post(ALCHEMY_URL, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Alchemy API error: {e}")
            return {}
        
    def identify_platform(self, contract_address: str) -> str:
        """Identify platform from contract address on Base - with better unknown handling"""
        contract_address = contract_address.lower()
        
        if contract_address in KNOWN_CONTRACTS:
            return KNOWN_CONTRACTS[contract_address]["platform"]
        
        # Enhanced pattern matching for Base
        if any(addr in contract_address for addr in [
            "2626664c2603336e57b271c5c0b26f421741e481",  # Uniswap V3
            "4752ba5dbc23f44d87826276bf6fd6b1c372ad24"   # Uniswap Universal
        ]):
            return "Uniswap"
        elif "cf77a3ba9a5ca399b7c97c74d54e5b1beb874e43" in contract_address:
            return "Aerodrome"
        elif "327df1e6de05895d2ab08513aadd9313fe505d86" in contract_address:
            return "BaseSwap"
        elif "6bded42c906e69b412ca037f01db3fa68b2de1a4" in contract_address:
            return "SushiSwap"
        elif "678aa4bf4e210cf2166753e054d5b7c31cc7fa86" in contract_address:
            return "PancakeSwap"
        elif "1111111254" in contract_address:
            return "1inch"
        
    
    def get_recent_block_range(self, days_back: float = 7) -> tuple:
        """Get block range for recent days on Base (2 second block times)
        Now handles float days_back for partial days
        """
        try:
            current_block_result = self.make_alchemy_request("eth_blockNumber", [])
            if not current_block_result.get("result"):
                return "0x0", "0x0"
                
            current_block = int(current_block_result["result"], 16)
            
            # Base has ~2 second block times, so ~43200 blocks per day
            # Convert float days to blocks
            blocks_per_day = 43200
            blocks_back = int(days_back * blocks_per_day)  # Convert to int here
            
            start_block = max(0, current_block - blocks_back)
            
            print(f"   Block range: {start_block} to {current_block} ({blocks_back} blocks = {days_back:.2f} days)")
            
            return hex(start_block), hex(current_block)
        except Exception as e:
            print(f"Error calculating block range: {e}")
            return "0x0", "0x0" 
        
    def is_interesting_token(self, token_symbol: str) -> bool:
        """Check if token is interesting for alpha discovery on Base"""
        if not token_symbol:
            return False
        
        token_lower = token_symbol.lower()
        
        # Check against excluded tokens
        if token_lower in EXCLUDED_TOKENS_LOWER:
            return False
        
        # Skip tokens that look like LP tokens
        if any(pattern in token_lower for pattern in ["-lp", "lp-", "slp", "uni-v2", "uni-lp", "aero-lp", "cake-lp"]):
            return False
        
        # Skip Base-specific derivative patterns
        if len(token_lower) > 4 and any(token_lower.startswith(prefix) for prefix in ["a", "c", "y", "v", "s", "cb"]):
            # Only skip if it's a DeFi derivative pattern
            base_token = token_lower[1:] if not token_lower.startswith("cb") else token_lower[2:]
            if base_token in EXCLUDED_TOKENS_LOWER:
                return False
        
        return True
    
    def identify_platform(self, contract_address: str) -> str:
        """Identify platform from contract address on Base - with better unknown handling"""
        contract_address = contract_address.lower()
        
        if contract_address in KNOWN_CONTRACTS:
            return KNOWN_CONTRACTS[contract_address]["platform"]
        
        # Enhanced pattern matching for Base
        if any(addr in contract_address for addr in [
            "2626664c2603336e57b271c5c0b26f421741e481",  # Uniswap V3
            "4752ba5dbc23f44d87826276bf6fd6b1c372ad24"   # Uniswap Universal
        ]):
            return "Uniswap"
        elif "cf77a3ba9a5ca399b7c97c74d54e5b1beb874e43" in contract_address:
            return "Aerodrome"
        elif "327df1e6de05895d2ab08513aadd9313fe505d86" in contract_address:
            return "BaseSwap"
        elif "6bded42c906e69b412ca037f01db3fa68b2de1a4" in contract_address:
            return "SushiSwap"
        elif "678aa4bf4e210cf2166753e054d5b7c31cc7fa86" in contract_address:
            return "PancakeSwap"
        elif "1111111254" in contract_address:
            return "1inch"
        
        # Heuristic detection for potential Base trading bots
        elif contract_address.startswith("0x3328") or contract_address.startswith("0x3723"):
            return "Banana Gun (Possible)"
        elif contract_address.startswith("0x80a6"):
            return "Maestro Bot (Possible)"
        elif contract_address.startswith("0x1111") and len(contract_address) == 42:
            return "Unknown Aggregator"
        elif contract_address.startswith("0x7777") or contract_address.startswith("0x3333"):
            return "Unknown Trading Bot"
        elif any(pattern in contract_address for pattern in ["dead", "beef", "babe", "cafe"]):
            return "Possible MEV Bot"
        else:
            # Try to categorize based on address patterns
            if len(set(contract_address[2:])) >= 12:  # High entropy
                return "Unknown Trading Contract"
            else:
                return "Unknown Contract"
    
    def get_contract_info(self, contract_address: str) -> Dict:
        """Get contract information for Base network - enhanced for unknowns"""
        contract_address = contract_address.lower()
        
        if contract_address in KNOWN_CONTRACTS:
            return KNOWN_CONTRACTS[contract_address]
        
        # Enhanced detection for unknown contracts
        platform = self.identify_platform(contract_address)
        
        # Determine contract type based on platform
        if "Bot" in platform or "MEV" in platform:
            contract_type = "TELEGRAM_BOT"
        elif "Aggregator" in platform:
            contract_type = "DEX"
        else:
            contract_type = "UNKNOWN"
        
        return {
            "name": f"{platform} Contract",
            "type": contract_type,
            "platform": platform
        }
    
    def estimate_usd_value(self, amount: float, token: str) -> float:
        """Rough USD estimation for Base tokens"""
        # Base network token prices (approximate)
        rough_prices = {
            "ETH": 2000, "WETH": 2000,
            "cbETH": 2000, "wstETH": 2200,
            "WBTC": 35000, "cbBTC": 35000, "tBTC": 35000,
            "USDC": 1, "USDbC": 1, "USDT": 1, "DAI": 1,
            "AERO": 1.50,  # Aerodrome token
            "BALD": 0.05,  # Example Base meme token
            "TOSHI": 0.0001,
            "BRETT": 0.15,
            "DEGEN": 0.02,
            "HIGHER": 0.03,
        }
        
        price = rough_prices.get(token.upper(), 0.0001)  # Default to very low for unknown
        return amount * price
    
    def calculate_score_components(self, wallet_scores: List[float], max_possible_wallet_score: float = 300) -> Dict:
        """Calculate weighted consensus components"""
        if not wallet_scores:
            return {"weighted_consensus": 0.0, "wallet_count": 0}
        
        # Weighted consensus score
        weighted_consensus_score = 0.0
        
        for wallet_score in wallet_scores:
            # Convert wallet score to quality weight
            wallet_quality_weight = (max_possible_wallet_score - wallet_score + 100) / 100
            weighted_consensus_score += wallet_quality_weight
        
        # Add bonus for multiple wallets
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
    
    def get_top_wallets(self, num_wallets: int = 5) -> List[Dict]:
        """Get top wallets from Base database"""
        return list(self.wallets_collection.find().sort("score", -1).limit(num_wallets))
    
    def test_connection(self):
        """Test Alchemy API connection to Base"""
        print("=== Testing Alchemy Connection to Base Network ===")
        
        try:
            result = self.make_alchemy_request("eth_blockNumber", [])
            if result.get("result"):
                current_block = int(result["result"], 16)
                print(f"✅ Connected to Base Network - Current block: {current_block}")
                return True
            else:
                print("❌ Failed to connect to Base Network")
                return False
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False

def print_header(title: str, min_eth_value: float, excluded_count: int):
    """Print a formatted header for Base analysis"""
    print(f"\n{title}")
    print("=" * len(title))
    print(f"🔵 Base Network Analysis")
    print(f"💰 Minimum purchase threshold: {min_eth_value} ETH")
    print(f"🚫 Excluding {excluded_count} boring tokens")
    print("=" * len(title))

def print_insights(ranked_items: List[tuple], item_type: str = "tokens", max_items: int = 5):
    """Print key insights from Base ranked analysis"""
    if ranked_items:
        print(f"\n" + "🔵" * 30)
        print(f"KEY BASE {item_type.upper()} INSIGHTS:")
        print(f"🔵" * 30)
        
        for item, data, score in ranked_items[:max_items]:
            wallet_count = len(data["wallets"])
            total_value = data.get("total_eth_spent", data.get("total_estimated_eth", 0))
            avg_wallet_score = sum(data["wallet_scores"]) / len(data["wallet_scores"])
            platforms = ", ".join(data.get("platforms", data.get("methods", [])))
            print(f"🚀 {item}: score={score} | {wallet_count} wallets | {total_value:.3f}Ξ | avg_score={avg_wallet_score:.0f} | {platforms}")

# Base-specific utility functions
def get_base_gas_estimate(tx_type: str = "swap") -> float:
    """Get estimated gas costs for Base transactions"""
    base_gas_estimates = {
        "swap": 0.0005,      # ~$0.001 for swaps
        "transfer": 0.0001,   # ~$0.0002 for transfers
        "bridge": 0.002,      # ~$0.004 for bridging
    }
    return base_gas_estimates.get(tx_type, 0.001)

def is_base_native_token(token_symbol: str) -> bool:
    """Check if token is native to Base ecosystem"""
    base_native_tokens = {
        "AERO", "BALD", "TOSHI", "BRETT", "NORMIE", "DEGEN", 
        "HIGHER", "MOCHI", "SEAM", "SPEC", "WELL", "EXTRA"
    }
    return token_symbol.upper() in base_native_tokens