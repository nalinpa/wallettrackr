import requests
import pymongo
from datetime import datetime, timedelta
import time
import json
import os
import math
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

# Configuration
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')
ALCHEMY_URL = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
MONGO_URI = 'mongodb://localhost:27017'
DB_NAME = 'crypto_tracker'
WALLETS_COLLECTION = 'smart_wallets'

# Minimum transaction value filter (in ETH)
MIN_ETH_VALUE = 0.05

# Tokens to exclude from analysis (DeFi tokens, stablecoins, etc.)
EXCLUDED_TOKENS = {
    # Stablecoins
    "USDC", "USDT", "DAI", "FRAX", "BUSD", "TUSD", "GUSD", "PYUSD", "FDUSD",
    "USDbC", "USDP", "sUSD", "LUSD", "MIM", "DOLA", "VUSD", "BEAN", "USDe",
    
    # Stablecoin derivatives
    "sUSDe", "sDAI", "sFRAX", "aUSDC", "aUSDT", "aDAI", "cUSDC", "cUSDT", "cDAI",
    
    # ETH and wrapped tokens
    "ETH", "WETH", "stETH", "wstETH", "rETH", "cbETH", "frxETH", "sfrxETH",
    "BETH", "ankrETH", "swETH", "osETH",
    
    # Major DeFi tokens (usually not alpha)
    "AAVE", "UNI", "SUSHI", "CRV", "CVX", "BAL", "YFI", "SNX", "MKR", "COMP",
    "PENDLE", "LDO", "FXS", "OHM", "TRIBE", "FEI", "ALCX", "SPELL", "ICE",
    
    # Liquid staking derivatives
    "LIDO", "RPL", "ANKR", "FIS", "SD", "LSD",
    
    # Common wrapped/bridged tokens
    "WBTC", "renBTC", "sBTC", "tBTC", "HBTC", "pBTC", "anyBTC",
    
    # Large cap tokens (not usually alpha)
    "LINK", "MATIC", "AVAX", "DOT", "ADA", "SOL", "ATOM", "NEAR", "FTM",
    "ALGO", "XTZ", "EGLD", "ONE", "LUNA", "UST", "USTC",
    
    # Index tokens and wrappers
    "DPI", "MVI", "BED", "DATA", "GMI", "INDEX", "cToken", "aToken", "yToken",
    
    # Gaming tokens that are often farmed
    "AXS", "SLP", "MANA", "SAND", "ENJ", "CHZ", "GALA", "IMX", "GODS",
    
    # Governance tokens
    "veYFI", "veCRV", "veBAL", "vlCVX", "xSUSHI", "veFXS", "veOGV",
}

# Convert to lowercase for case-insensitive matching
EXCLUDED_TOKENS_LOWER = {token.lower() for token in EXCLUDED_TOKENS}

# Known DEX and MEV bot contracts - ENHANCED
KNOWN_CONTRACTS = {
    # Uniswap
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": {"name": "Uniswap V2 Router", "type": "DEX", "platform": "Uniswap"},
    "0xe592427a0aece92de3edee1f18e0157c05861564": {"name": "Uniswap V3 Router", "type": "DEX", "platform": "Uniswap"},
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": {"name": "Uniswap V3 Router 2", "type": "DEX", "platform": "Uniswap"},
    "0xef1c6e67703c7bd7107eed8303fbe6ec2554bf6b": {"name": "Uniswap Universal Router", "type": "DEX", "platform": "Uniswap"},
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": {"name": "Uniswap Universal Router 2", "type": "DEX", "platform": "Uniswap"},
    
    # 1inch
    "0x1111111254eeb25477b68fb85ed929f73a960582": {"name": "1inch V5 Router", "type": "DEX", "platform": "1inch"},
    "0x1111111254fb6c44bac0bed2854e76f90643097d": {"name": "1inch V4 Router", "type": "DEX", "platform": "1inch"},
    "0x11111112542d85b3ef69ae05771c2dccff2faa26": {"name": "1inch Limit Order Protocol", "type": "DEX", "platform": "1inch"},
    
    # CoW Protocol
    "0x9008d19f58aabd9ed0d60971565aa8510560ab41": {"name": "CoW Protocol Settlement", "type": "DEX", "platform": "CoW Protocol"},
    
    # MAINNET TELEGRAM BOTS - ENHANCED DETECTION
    "0x3328f7f4a1d1c57c35df56bbf0c9dcafca309c49": {"name": "Banana Gun Router", "type": "TELEGRAM_BOT", "platform": "Banana Gun"},
    "0x37238dc7835c77449e5a2a96eb5f4ad0d5b0c8f9": {"name": "Banana Gun Bot", "type": "TELEGRAM_BOT", "platform": "Banana Gun"},
    "0x80a64c6d7f12c47b7c66c5b4e20e72bc1fcd5d9e": {"name": "Maestro Bot", "type": "TELEGRAM_BOT", "platform": "Maestro Bot"},
    "0x000000000022d473030f116ddee9f6b43ac78ba3": {"name": "Permit2", "type": "UTILITY", "platform": "Permit2"},
    "0x881d40237659c251811cec9c364ef91dc08d300c": {"name": "Metamask Swap Router", "type": "DEX", "platform": "Metamask"},
    
    # UNIBOT and other popular Telegram bots
    "0x13f4ea83d0bd40e75c8222255bc855a974568dd4": {"name": "UniBot Router", "type": "TELEGRAM_BOT", "platform": "UniBot"},
    "0xe3120d2c4b59dce32d0b7e4b34fe6a93e9ad6a5c": {"name": "UniBot Router V2", "type": "TELEGRAM_BOT", "platform": "UniBot"},
    
    # BONKBOT
    "0x1234567890123456789012345678901234567890": {"name": "BonkBot Router", "type": "TELEGRAM_BOT", "platform": "BonkBot"},
    
    # TROJAN BOT (update with real addresses)
    "0x2234567890123456789012345678901234567890": {"name": "Trojan Bot Router", "type": "TELEGRAM_BOT", "platform": "Trojan Bot"},
    
    # Other popular DEX aggregators
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff": {"name": "0x Protocol", "type": "DEX", "platform": "0x Protocol"},
    "0x6131b5fae19ea4f9d964eac0408e4408b66337b5": {"name": "Kyber Network", "type": "DEX", "platform": "Kyber Network"},
    "0xa5e0829caced8ffdd4de3c43696c57f7d7a678ff": {"name": "QuickSwap Router", "type": "DEX", "platform": "QuickSwap"},
    
    # MEV Bots (add as discovered)
    "0x7777777777777777777777777777777777777777": {"name": "MEV Bot", "type": "MEV_BOT", "platform": "MEV Bot"},
    "0x5555555555555555555555555555555555555555": {"name": "Sandwich Bot", "type": "MEV_BOT", "platform": "Sandwich Bot"},
        "0xef4fb24ad0916217251f553c0596f8edc630eb66": {"name": "Unknown Telegram Bot", "type": "TELEGRAM_BOT", "platform": "Unknown Telegram Bot"},
    "0x5c7bcd6e7de5423a257d81b442095a1a6ced35c5": {"name": "Unknown Telegram Bot", "type": "TELEGRAM_BOT", "platform": "Unknown Telegram Bot"},
    "0x111111125421ca6dc452d289314280a0f8842a65": {"name": "Unknown Telegram Bot", "type": "TELEGRAM_BOT", "platform": "Unknown Telegram Bot"},
    "0x66a9893cc07d91d95644aedd05d03f95e1dba8af": {"name": "Popular Bot (UniBot/BonkBot candidate)", "type": "TELEGRAM_BOT", "platform": "Popular Bot (UniBot/BonkBot candidate)"},
    "0x663dc15d3c1ac63ff12e45ab68fea3f0a883c251": {"name": "Unknown Telegram Bot", "type": "TELEGRAM_BOT", "platform": "Unknown Telegram Bot"},
    "0x3154cf16ccdb4c6d922629664174b904d80f2c35": {"name": "Unknown Trading Contract", "type": "UNKNOWN_TRADING", "platform": "Unknown Trading Contract"},
    "0x1231deb6f5749ef6ce6943a275a1d3e7486f4eae": {"name": "Unknown Telegram Bot", "type": "TELEGRAM_BOT", "platform": "Unknown Telegram Bot"},
    "0x6e4141d33021b52c91c28608403db4a0ffb50ec6": {"name": "Unknown Telegram Bot", "type": "TELEGRAM_BOT", "platform": "Unknown Telegram Bot"},
    "0x5141b82f5ffda4c6fe1e372978f1c5427640a190": {"name": "Unknown Telegram Bot", "type": "TELEGRAM_BOT", "platform": "Unknown Telegram Bot"},
    "0xdf31a70a21a1931e02033dbba7deace6c45cfd0f": {"name": "Unknown Telegram Bot", "type": "TELEGRAM_BOT", "platform": "Unknown Telegram Bot"},
    "0xb0999731f7c2581844658a9d2ced1be0077b7397": {"name": "Unknown Telegram Bot", "type": "TELEGRAM_BOT", "platform": "Unknown Telegram Bot"},
    "0x74de5d4fcbf63e00296fd95d33236b9794016631": {"name": "Unknown Telegram Bot", "type": "TELEGRAM_BOT", "platform": "Unknown Telegram Bot"},
    "0x0000000000001ff3684f28c67538d4d072c22734": {"name": "MEV Bot", "type": "MEV_BOT", "platform": "MEV Bot"},
    "0x000000000004444c5dc75cb358380d2e3de08a90": {"name": "MEV Bot", "type": "MEV_BOT", "platform": "MEV Bot"},
    "0x6a000f20005980200259b80c5102003040001068": {"name": "Unknown Trading Contract", "type": "UNKNOWN_TRADING", "platform": "Unknown Trading Contract"},
}

class BaseTracker:
    """Base class with shared functionality for buy and sell trackers"""
    
    def __init__(self):
        self.mongo_client = pymongo.MongoClient(MONGO_URI)
        self.db = self.mongo_client[DB_NAME]
        self.wallets_collection = self.db[WALLETS_COLLECTION]
        
    def make_alchemy_request(self, method: str, params: List) -> Dict:
        """Make request to Alchemy API"""
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

    def get_recent_block_range(self, days_back: float = 7) -> tuple:
        """Get block range for recent days"""
        try:
            current_block_result = self.make_alchemy_request("eth_blockNumber", [])
            if not current_block_result.get("result"):
                return "0x0", "0x0"
                
            current_block = int(current_block_result["result"], 16)
            
            # ~7200 blocks per day on Ethereum (12 second blocks)
            blocks_per_day = 7200
            blocks_back = int(days_back * blocks_per_day)  
            
            start_block = max(0, current_block - blocks_back)
            
            return hex(start_block), hex(current_block)
        except Exception as e:
            print(f"Error calculating block range: {e}")
            return "0x0", "0x0"                
    
    def is_interesting_token(self, token_symbol: str) -> bool:
        """Check if token is interesting for alpha discovery (not excluded)"""
        if not token_symbol:
            return False
        
        token_lower = token_symbol.lower()
        
        # Check against excluded tokens
        if token_lower in EXCLUDED_TOKENS_LOWER:
            return False
        
        # Additional filters for common patterns
        # Skip tokens that look like LP tokens
        if any(pattern in token_lower for pattern in ["-lp", "lp-", "slp", "uni-v2", "uni-lp"]):
            return False
        
        # Skip tokens with common DeFi prefixes/suffixes
        if len(token_lower) > 4 and any(token_lower.startswith(prefix) for prefix in ["a", "c", "y", "v", "s"]):
            # Only skip if it's a DeFi derivative pattern (like aUSDC, cETH, yDAI)
            base_token = token_lower[1:]
            if base_token in EXCLUDED_TOKENS_LOWER:
                return False
        
        return True
    
    def identify_platform(self, contract_address: str) -> str:
        """Identify platform from contract address - ENHANCED"""
        contract_address = contract_address.lower()
        
        if contract_address in KNOWN_CONTRACTS:
            return KNOWN_CONTRACTS[contract_address]["platform"]
        
        # Enhanced pattern matching for mainnet
        if any(addr in contract_address for addr in [
            "7a250d5630b4cf539739df2c5dacb4c659f2488d",
            "e592427a0aece92de3edee1f18e0157c05861564", 
            "68b3465833fb72a70ecdf485e0e4c7bd8665fc45",
            "ef1c6e67703c7bd7107eed8303fbe6ec2554bf6b",
            "3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad"
        ]):
            return "Uniswap"
        elif "1111111254" in contract_address:
            return "1inch"
        elif contract_address == "0x9008d19f58aabd9ed0d60971565aa8510560ab41":
            return "CoW Protocol"
        elif contract_address in ["0x3328f7f4a1d1c57c35df56bbf0c9dcafca309c49", "0x37238dc7835c77449e5a2a96eb5f4ad0d5b0c8f9"]:
            return "Banana Gun"
        elif contract_address == "0x80a64c6d7f12c47b7c66c5b4e20e72bc1fcd5d9e":
            return "Maestro Bot"
        elif contract_address == "0xdef1c0ded9bec7f1a1670819833240f027b25eff":
            return "0x Protocol"
        
        # ENHANCED: Heuristic detection for unknown bots/platforms
        elif contract_address.startswith("0x1111") and len(contract_address) == 42:
            return "Unknown Aggregator"
        elif contract_address.startswith("0x3328") or contract_address.startswith("0x3723"):
            return "Banana Gun (Possible)"
        elif contract_address.startswith("0x80a6"):
            return "Maestro Bot (Possible)"
        elif contract_address.startswith("0x1337") or contract_address.startswith("0x7777"):
            return "Unknown Trading Bot"
        elif any(pattern in contract_address for pattern in ["dead", "beef", "babe", "cafe"]):
            return "Possible MEV Bot"
        elif contract_address.startswith("0x13f4") or contract_address.startswith("0xe312"):
            return "UniBot (Possible)"
        else:
            # Enhanced categorization
            if len(set(contract_address[2:])) >= 12:  # High entropy = likely contract
                return "Unknown Trading Contract"
            else:
                return "Unknown Contract"
    
    def get_contract_info(self, contract_address: str) -> Dict:
        """Get contract information - ENHANCED"""
        contract_address = contract_address.lower()
        
        if contract_address in KNOWN_CONTRACTS:
            return KNOWN_CONTRACTS[contract_address]
        
        # Enhanced detection for unknown contracts
        platform = self.identify_platform(contract_address)
        
        # Determine contract type based on platform/patterns
        if "Bot" in platform or "MEV" in platform or "Gun" in platform or "Maestro" in platform:
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
        """Rough USD estimation for tokens"""
        rough_prices = {
            "ETH": 2000, "WETH": 2000,
            "WBTC": 35000, "BTC": 35000,
            "USDC": 1, "USDT": 1, "DAI": 1,
        }
        
        price = rough_prices.get(token.upper(), 0.001)  # Default to $0.001 for unknown tokens
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
        
        # Add bonus for multiple wallets (logarithmic to prevent spam)
        wallet_count = len(wallet_scores)
        if wallet_count > 1:
            consensus_bonus = math.log(wallet_count) * 0.5  # Logarithmic bonus for more wallets
            weighted_consensus_score = weighted_consensus_score + (weighted_consensus_score * consensus_bonus)
        
        return {
            "weighted_consensus": weighted_consensus_score,
            "wallet_count": wallet_count,
            "best_wallet_score": min(wallet_scores),
            "avg_wallet_score": sum(wallet_scores) / len(wallet_scores)
        }
    
    def get_top_wallets(self, num_wallets: int = 5) -> List[Dict]:
        """Get top wallets from database"""
        return list(self.wallets_collection.find().sort("score", 1).limit(num_wallets))
    
    def test_connection(self):
        """Test Alchemy API connection"""
        print("=== Testing Alchemy Connection ===")
        
        try:
            result = self.make_alchemy_request("eth_blockNumber", [])
            if result.get("result"):
                current_block = int(result["result"], 16)
                print(f"✅ Connected to Alchemy - Current block: {current_block}")
                return True
            else:
                print("❌ Failed to connect to Alchemy")
                return False
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False

def print_header(title: str, min_eth_value: float, excluded_count: int):
    """Print a formatted header for analysis"""
    print(f"\n{title}")
    print("=" * len(title))
    print(f"💰 Minimum purchase threshold: {min_eth_value} ETH")
    print(f"🚫 Excluding {excluded_count} boring tokens")
    print("=" * len(title))

def print_insights(ranked_items: List[tuple], item_type: str = "tokens", max_items: int = 5):
    """Print key insights from ranked analysis"""
    if ranked_items:
        print(f"\n" + "🎯" * 30)
        print(f"KEY {item_type.upper()} INSIGHTS:")
        print(f"🎯" * 30)
        
        for item, data, score in ranked_items[:max_items]:
            wallet_count = len(data["wallets"])
            total_value = data.get("total_eth_spent", data.get("total_estimated_eth", 0))
            avg_wallet_score = sum(data["wallet_scores"]) / len(data["wallet_scores"])
            platforms = ", ".join(data.get("platforms", data.get("methods", [])))
            print(f"🚀 {item}: score={score} | {wallet_count} wallets | {total_value:.3f}Ξ | avg_score={avg_wallet_score:.0f} | {platforms}")