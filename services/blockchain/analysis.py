import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ContractInfo:
    """Contract information data class"""
    name: str
    platform: str
    contract_type: str
    confidence: str  # HIGH, MEDIUM, LOW

@dataclass
class TokenInfo:
    """Token information data class"""
    symbol: str
    is_interesting: bool
    is_base_native: bool
    estimated_price_usd: float
    exclusion_reason: Optional[str] = None

class AnalysisService:
    """Service for token validation, contract detection, pricing, and purchase validation"""
    
    def __init__(self, network: str = "base"):
        self.network = network
        self._setup_data()
        logger.info(f"✅ AnalysisService initialized for {network}")
    
    def _setup_data(self):
        """Initialize all the data mappings"""
        
        # Known contract addresses and their info
        self.known_contracts = {
            # Ethereum contracts
            "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": ContractInfo("Uniswap V2 Router", "Uniswap", "DEX", "HIGH"),
            "0xe592427a0aece92de3edee1f18e0157c05861564": ContractInfo("Uniswap V3 Router", "Uniswap", "DEX", "HIGH"),
            "0x1111111254eeb25477b68fb85ed929f73a960582": ContractInfo("1inch V5 Router", "1inch", "DEX", "HIGH"),
            "0x3328f7f4a1d1c57c35df56bbf0c9dcafca309c49": ContractInfo("Banana Gun Router", "Banana Gun", "TELEGRAM_BOT", "HIGH"),
            
            # Base contracts
            "0x2626664c2603336e57b271c5c0b26f421741e481": ContractInfo("Uniswap V3 SwapRouter", "Uniswap", "DEX", "HIGH"),
            "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43": ContractInfo("Aerodrome Router", "Aerodrome", "DEX", "HIGH"),
            "0x327df1e6de05895d2ab08513aadd9313fe505d86": ContractInfo("BaseSwap Router", "BaseSwap", "DEX", "HIGH"),
            "0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24": ContractInfo("BaseSwap Factory", "BaseSwap", "DEX", "HIGH"),
        }
        
        # Contract detection patterns
        self.contract_patterns = {
            # Address patterns that indicate specific platforms
            "1111111254": ("1inch", "DEX"),
            "7a250d": ("Uniswap", "DEX"),
            "e59242": ("Uniswap", "DEX"),
            "2626664c": ("Uniswap", "DEX"),
            "cf77a3ba": ("Aerodrome", "DEX"),
            "327df1e6": ("BaseSwap", "DEX"),
            "3328f7f4": ("Banana Gun", "TELEGRAM_BOT"),
            "80a64c3c": ("Maestro Bot", "TELEGRAM_BOT"),
        }
        
        # Excluded tokens
        self.excluded_tokens = {
            "ETH", "WETH", "USDC", "USDT", "DAI", "WBTC", "BUSD", "FRAX",
            "stETH", "wstETH", "rETH", "cbETH", "frxETH", "sfrxETH",
            "MATIC", "BNB", "AVAX", "SOL", "ADA", "DOT"
        }
        
        # LP token patterns
        self.lp_patterns = {
            "-lp", "lp-", "slp", "uni-v2", "uni-lp", "aero-lp", 
            "cake-lp", "sushi-lp", "curve-lp", "bal-lp"
        }
        
        # Base native tokens
        self.base_native_tokens = {
            "AERO", "BALD", "TOSHI", "BRETT", "DEGEN", "HIGHER", 
            "MOCHI", "NORMIE", "SPEC", "WELL", "EXTRA", "SEAM",
            "BASED", "BLUE", "MIGGLES", "KEYCAT", "DOGINME"
        }
        
        # Simple price mapping (USD)
        self.token_prices = {
            # Major tokens
            "ETH": 2000.0, "WETH": 2000.0, "cbETH": 2000.0, "wstETH": 2200.0, "rETH": 2000.0,
            "stETH": 2000.0, "frxETH": 2000.0, "sfrxETH": 2000.0,
            
            # BTC variants
            "WBTC": 35000.0, "BTC": 35000.0, "cbBTC": 35000.0, "tBTC": 35000.0,
            
            # Stablecoins
            "USDC": 1.0, "USDT": 1.0, "DAI": 1.0, "USDbC": 1.0, "FRAX": 1.0, "BUSD": 1.0,
            
            # Base ecosystem tokens
            "AERO": 1.50, "BALD": 0.05, "TOSHI": 0.0001, "BRETT": 0.15,
            "DEGEN": 0.02, "HIGHER": 0.03, "MOCHI": 0.001, "NORMIE": 0.008,
            "SPEC": 0.12, "WELL": 0.003, "EXTRA": 0.0005,
            
            # Other major tokens
            "UNI": 8.0, "LINK": 15.0, "AAVE": 100.0, "CRV": 0.5, "SNX": 3.0,
            "COMP": 50.0, "MKR": 1500.0, "YFI": 8000.0, "SUSHI": 1.2, "BAL": 3.5,
        }
        
        # Minimum thresholds by network
        self.min_thresholds = {
            "ethereum": {"eth": 0.01, "usd": 20.0},
            "base": {"eth": 0.005, "usd": 10.0}
        }
    
    # TOKEN VALIDATION METHODS
    
    async def is_interesting_token(self, token_symbol: str) -> bool:
        """Check if token is interesting for analysis"""
        if not token_symbol or not isinstance(token_symbol, str):
            return False
        
        token_upper = token_symbol.upper().strip()
        
        # Check if excluded
        if token_upper in self.excluded_tokens:
            return False
        
        # Check for LP tokens
        token_lower = token_symbol.lower()
        if any(pattern in token_lower for pattern in self.lp_patterns):
            return False
        
        # Check for derivative tokens (aToken, cToken, etc.)
        if len(token_lower) > 4:
            for prefix in ["a", "c", "y", "v", "s"]:
                if token_lower.startswith(prefix):
                    base_token = token_lower[1:] if prefix != "cb" else token_lower[2:]
                    if base_token.upper() in self.excluded_tokens:
                        return False
        
        return True
    
    async def get_token_info(self, token_symbol: str) -> TokenInfo:
        """Get comprehensive token information"""
        if not token_symbol:
            return TokenInfo("", False, False, 0.0, "Empty symbol")
        
        token_upper = token_symbol.upper().strip()
        
        # Check if interesting
        is_interesting = await self.is_interesting_token(token_symbol)
        exclusion_reason = None
        
        if not is_interesting:
            if token_upper in self.excluded_tokens:
                exclusion_reason = "Excluded token"
            elif any(pattern in token_symbol.lower() for pattern in self.lp_patterns):
                exclusion_reason = "LP token"
            else:
                exclusion_reason = "Derivative token"
        
        # Check if Base native
        is_base_native = token_upper in self.base_native_tokens
        
        # Get price
        estimated_price = self.token_prices.get(token_upper, 0.001)  # Default $0.001
        
        return TokenInfo(
            symbol=token_symbol,
            is_interesting=is_interesting,
            is_base_native=is_base_native,
            estimated_price_usd=estimated_price,
            exclusion_reason=exclusion_reason
        )
    
    async def is_base_native_token(self, token_symbol: str) -> bool:
        """Check if token is native to Base ecosystem"""
        if not token_symbol:
            return False
        return token_symbol.upper().strip() in self.base_native_tokens
    
    # CONTRACT DETECTION METHODS
    
    async def get_contract_info(self, address: str) -> ContractInfo:
        """Get contract information from address"""
        if not address:
            return ContractInfo("Unknown", "Unknown", "UNKNOWN", "LOW")
        
        address_lower = address.lower()
        
        # Check known contracts first
        if address_lower in self.known_contracts:
            return self.known_contracts[address_lower]
        
        # Check patterns
        for pattern, (platform, contract_type) in self.contract_patterns.items():
            if pattern in address_lower:
                return ContractInfo(f"{platform} Contract", platform, contract_type, "MEDIUM")
        
        # Heuristic detection
        platform, contract_type, confidence = self._detect_contract_heuristic(address_lower)
        return ContractInfo(f"{platform} Contract", platform, contract_type, confidence)
    
    def _detect_contract_heuristic(self, address: str) -> tuple:
        """Detect contract type using heuristics"""
        # Remove 0x prefix
        addr = address[2:] if address.startswith("0x") else address
        
        # High entropy = likely contract
        unique_chars = len(set(addr))
        if unique_chars >= 12:
            # Bot patterns
            if addr.startswith("1337") or addr.startswith("7777"):
                return "Trading Bot", "TELEGRAM_BOT", "MEDIUM"
            elif addr.startswith("3333") or addr.startswith("beef"):
                return "MEV Bot", "MEV_BOT", "MEDIUM"
            else:
                return "Unknown Contract", "DEX", "LOW"
        
        return "Unknown", "UNKNOWN", "LOW"
    
    async def is_known_trading_contract(self, address: str) -> bool:
        """Check if address is a known trading contract"""
        if not address:
            return False
        
        contract_info = await self.get_contract_info(address)
        return contract_info.contract_type in ["DEX", "TELEGRAM_BOT", "MEV_BOT"]
    
    # PRICING METHODS
    
    async def estimate_usd_value(self, amount: float, token_symbol: str) -> float:
        """Estimate USD value of token amount"""
        if not token_symbol or amount <= 0:
            return 0.0
        
        price = self.token_prices.get(token_symbol.upper(), 0.001)
        return amount * price
    
    async def estimate_eth_value(self, amount: float, token_symbol: str) -> float:
        """Estimate ETH value of token amount"""
        usd_value = await self.estimate_usd_value(amount, token_symbol)
        eth_price = self.token_prices.get("ETH", 2000.0)
        return usd_value / eth_price
    
    async def calculate_eth_spent(self, amount_sold: float, token_sent: str) -> float:
        """Calculate ETH spent in a transaction"""
        if token_sent.upper() == "ETH":
            return amount_sold
        else:
            # Convert other token to ETH equivalent
            return await self.estimate_eth_value(amount_sold, token_sent)
    
    async def get_token_price(self, token_symbol: str) -> float:
        """Get token price in USD"""
        if not token_symbol:
            return 0.0
        return self.token_prices.get(token_symbol.upper(), 0.001)
    
    # PURCHASE VALIDATION METHODS
    
    async def is_potential_purchase(self, transfer: Dict) -> bool:
        """Check if transfer looks like a token purchase"""
        asset = transfer.get("asset", "")
        value = transfer.get("value", 0)
        to_address = transfer.get("to", "").lower()
        
        # Validate basic fields
        if not asset or not value or not to_address:
            return False
        
        try:
            amount = float(value)
        except (ValueError, TypeError):
            return False
        
        # Check minimum value thresholds
        if not await self._meets_minimum_threshold(amount, asset):
            return False
        
        # Check if going to a trading contract
        if await self.is_known_trading_contract(to_address):
            return True
        
        # Heuristic checks
        return self._looks_like_trading_transaction(transfer)
    
    async def _meets_minimum_threshold(self, amount: float, asset: str) -> bool:
        """Check if amount meets minimum threshold for the network"""
        thresholds = self.min_thresholds.get(self.network, self.min_thresholds["base"])
        
        if asset.upper() == "ETH":
            return amount >= thresholds["eth"]
        else:
            # Convert to USD and check
            usd_value = await self.estimate_usd_value(amount, asset)
            return usd_value >= thresholds["usd"]
    
    def _looks_like_trading_transaction(self, transfer: Dict) -> bool:
        """Heuristic detection of trading transactions"""
        to_address = transfer.get("to", "").lower()
        asset = transfer.get("asset", "")
        
        try:
            value = float(transfer.get("value", 0))
        except:
            return False
        
        # High entropy address (likely contract)
        if len(set(to_address[2:])) >= 10:
            return True
        
        # Known patterns
        trading_patterns = [
            to_address.startswith("0x1111"),  # 1inch pattern
            to_address.startswith("0x3333"),  # Bot pattern
            to_address.startswith("0x7777"),  # Bot pattern
            value >= 1000,  # Large transaction
            asset.upper() in ["USDC", "USDT"] and value >= 50,  # Stablecoin trading
        ]
        
        return any(trading_patterns)
    
    async def validate_purchase_transaction(self, outgoing: Dict, incoming: Dict) -> Dict:
        """Validate and score a purchase transaction"""
        result = {
            "is_valid": False,
            "confidence": "LOW",
            "reasons": [],
            "score": 0
        }
        
        # Basic validation
        token_received = incoming.get("asset")
        token_sent = outgoing.get("asset", "ETH")
        
        if not token_received or token_received == token_sent:
            result["reasons"].append("Same token or no token received")
            return result
        
        # Check if token is interesting
        if not await self.is_interesting_token(token_received):
            result["reasons"].append("Token not interesting for analysis")
            return result
        
        # Check amounts
        try:
            amount_received = float(incoming.get("value", 0))
            amount_sold = float(outgoing.get("value", 0))
        except:
            result["reasons"].append("Invalid amount values")
            return result
        
        if amount_received <= 0:
            result["reasons"].append("No tokens received")
            return result
        
        # Check if meets thresholds
        if not await self._meets_minimum_threshold(amount_sold, token_sent):
            result["reasons"].append("Below minimum threshold")
            return result
        
        # Calculate score
        score = 0
        
        # Amount score
        eth_spent = await self.calculate_eth_spent(amount_sold, token_sent)
        if eth_spent >= 0.1:
            score += 30
        elif eth_spent >= 0.01:
            score += 20
        elif eth_spent >= 0.001:
            score += 10
        
        # Contract score
        to_address = outgoing.get("to", "")
        contract_info = await self.get_contract_info(to_address)
        if contract_info.confidence == "HIGH":
            score += 40
        elif contract_info.confidence == "MEDIUM":
            score += 25
        elif contract_info.confidence == "LOW":
            score += 10
        
        # Token score
        token_info = await self.get_token_info(token_received)
        if token_info.is_base_native and self.network == "base":
            score += 20
        if token_info.estimated_price_usd > 0.01:
            score += 10
        
        # Determine final validation
        result["score"] = score
        result["is_valid"] = score >= 30
        
        if score >= 70:
            result["confidence"] = "HIGH"
        elif score >= 40:
            result["confidence"] = "MEDIUM"
        else:
            result["confidence"] = "LOW"
        
        result["reasons"].append(f"Score: {score}/100")
        return result
    
    # UTILITY METHODS
    
    async def get_analysis_summary(self) -> Dict:
        """Get summary of service capabilities"""
        return {
            "network": self.network,
            "known_contracts": len(self.known_contracts),
            "contract_patterns": len(self.contract_patterns),
            "excluded_tokens": len(self.excluded_tokens),
            "base_native_tokens": len(self.base_native_tokens),
            "token_prices": len(self.token_prices),
            "supported_methods": [
                "is_interesting_token",
                "get_token_info", 
                "is_base_native_token",
                "get_contract_info",
                "is_known_trading_contract",
                "estimate_usd_value",
                "estimate_eth_value",
                "calculate_eth_spent",
                "is_potential_purchase",
                "validate_purchase_transaction"
            ]
        }
    
    def update_token_price(self, token_symbol: str, price_usd: float):
        """Update token price (for dynamic pricing)"""
        if token_symbol and price_usd > 0:
            self.token_prices[token_symbol.upper()] = price_usd
            logger.info(f"Updated {token_symbol} price to ${price_usd}")
    
    def add_known_contract(self, address: str, name: str, platform: str, contract_type: str):
        """Add a new known contract"""
        if address:
            self.known_contracts[address.lower()] = ContractInfo(name, platform, contract_type, "HIGH")
            logger.info(f"Added known contract: {name} at {address}")