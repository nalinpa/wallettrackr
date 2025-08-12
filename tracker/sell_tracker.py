from .tracker_utils import BaseTracker, NetworkSpecificMixins
from typing import List, Dict
import math
import time
import logging

logger = logging.getLogger(__name__)

class ComprehensiveSellTracker(BaseTracker):
    """Universal sell pressure tracker using centralized utilities"""
    
    def __init__(self, network: str):
        super().__init__(network)
        self.min_tokens_for_unknown = 50 if network == "base" else 100
    
    def analyze_wallet_sells(self, wallet_address: str, days_back: int = 1) -> List[Dict]:
        """Analyze token sells for any network"""
        logger.info(f"Analyzing {self.network} sells for: {wallet_address}")
        
        start_block, end_block = self.get_recent_block_range(days_back)
        
        # Get outgoing token transfers
        outgoing_result = self.make_alchemy_request("alchemy_getAssetTransfers", [{
            "fromAddress": wallet_address,
            "fromBlock": start_block,
            "toBlock": end_block,
            "category": ["erc20"],
            "withMetadata": True,
            "excludeZeroValue": True,
            "maxCount": "0x64"
        }])
        
        outgoing_transfers = outgoing_result.get("result", {}).get("transfers", [])
        logger.debug(f"Found {len(outgoing_transfers)} outgoing token transfers")
        
        sells = []
        method_summary = {"DEX": 0, "CEX": 0, "TELEGRAM_BOT": 0, "MEV_BOT": 0, "P2P_OTC": 0, "UNKNOWN": 0}
        
        for transfer in outgoing_transfers:
            token_sold = transfer.get("asset")
            value = transfer.get("value", 0)
            
            # Safe value conversion
            try:
                amount_sold = float(value) if value is not None else 0.0
            except (ValueError, TypeError):
                amount_sold = 0.0
            
            # Use centralized token checking
            if not self.is_interesting_token(token_sold):
                continue
            
            # Skip dust
            if amount_sold < 1:
                continue
            
            to_address = transfer.get("to", "").lower()
            tx_hash = transfer.get("hash", "")
            block_number = int(transfer.get("blockNum", "0x0"), 16)
            
            # Use centralized contract detection
            contract_info = self.get_contract_info(to_address)
            sell_method, recipient_name, confidence = self._determine_sell_method(
                contract_info, to_address, amount_sold, token_sold
            )
            
            # Use centralized value estimation
            estimated_usd = self.estimate_usd_value(amount_sold, token_sold)
            estimated_eth = estimated_usd / 2000
            
            # Network-specific inclusion criteria
            if self._should_include_sell(confidence, estimated_eth, token_sold):
                # Check if Base native (only for Base network)
                is_base_native = False
                if self.network == "base" and hasattr(NetworkSpecificMixins.BaseMixin, 'is_base_native_token'):
                    is_base_native = NetworkSpecificMixins.BaseMixin.is_base_native_token(token_sold)
                
                sell = {
                    "transaction_hash": tx_hash,
                    "token_sold": token_sold,
                    "amount_sold": amount_sold,
                    "sell_method": sell_method,
                    "recipient": recipient_name,
                    "recipient_address": to_address,
                    "estimated_usd_value": estimated_usd,
                    "estimated_eth_value": estimated_eth,
                    "confidence": confidence,
                    "block_number": block_number,
                    "contract_address": transfer.get("rawContract", {}).get("address", ""),
                    "platform": contract_info["platform"],
                    "is_base_native": is_base_native
                }
                
                sells.append(sell)
                method_summary[sell_method] += 1
                
                # Logging
                method_emoji = {
                    "DEX": "🔄", "CEX": "🏦", "TELEGRAM_BOT": "🤖", 
                    "MEV_BOT": "⚡", "P2P_OTC": "🤝", "UNKNOWN": "❓"
                }
                confidence_emoji = {"HIGH": "✅", "MEDIUM": "⚠️", "LOW": "❓"}
                native_flag = "🔵" if is_base_native else ""
                
                logger.debug(f"{method_emoji.get(sell_method, '❓')}{confidence_emoji[confidence]} {native_flag}SOLD: {token_sold} ({amount_sold:.0f}) → {recipient_name} | ~${estimated_usd:.0f}")
        
        logger.info(f"Found {len(sells)} significant {self.network} token sells")
        return sells
    
    def _determine_sell_method(self, contract_info: Dict, to_address: str, amount: float, token: str) -> tuple:
        """Determine sell method using centralized contract detection"""
        if contract_info["type"] != "UNKNOWN":
            return contract_info["type"], contract_info["name"], "HIGH"
        
        # Enhanced heuristic detection
        if self._looks_like_trading_contract(to_address, amount, token):
            if amount >= self.min_tokens_for_unknown:
                return "TELEGRAM_BOT", f"Possible {self.network.title()} Bot (Large)", "MEDIUM"
            else:
                return "UNKNOWN", f"Unknown {self.network.title()} Contract", "LOW"
        
        return "UNKNOWN", "Unknown Address", "LOW"
    
    def _looks_like_trading_contract(self, address: str, amount: float, token: str) -> bool:
        """Enhanced heuristic to detect trading contracts"""
        patterns = [
            len(set(address[2:])) >= 12,  # High entropy
            address.startswith("0x1111"),  # Aggregator pattern
            address.startswith("0x3333"),  # Bot pattern
            address.startswith("0x7777"),  # Bot pattern
            amount >= 100,  # Significant amounts
            token in ["USDC", "USDT"] and amount >= 50,  # Stablecoin trading
            any(pattern in address for pattern in ["dead", "beef", "babe", "cafe"]),
        ]
        return any(patterns)
    
    def _should_include_sell(self, confidence: str, estimated_eth: float, token_sold: str) -> bool:
        """Network-specific inclusion criteria"""
        base_multiplier = 0.2 if self.network == "base" else 1.0
        
        if confidence == "HIGH":
            return True
        elif confidence == "MEDIUM" and estimated_eth >= (self.min_eth_value * base_multiplier):
            return True
        elif confidence == "LOW" and estimated_eth >= (self.min_eth_value * 2):
            return True
        
        # Special case for Base native tokens
        if self.network == "base" and hasattr(NetworkSpecificMixins.BaseMixin, 'is_base_native_token'):
            if NetworkSpecificMixins.BaseMixin.is_base_native_token(token_sold) and estimated_eth >= (self.min_eth_value * 0.1):
                return True
        
        return False
    
    def calculate_token_sell_score(self, token_data: Dict) -> float:
        """Calculate comprehensive sell pressure score"""
        wallet_scores = token_data["wallet_scores"]
        sells = token_data["sells"]
        total_estimated_eth = token_data["total_estimated_eth"]
        
        if not wallet_scores or total_estimated_eth == 0 or not sells:
            return 0.0
        
        max_possible_wallet_score = 300
        weighted_eth_score = 0.0
        
        for sell in sells:
            wallet_score = sell.get("wallet_score", max_possible_wallet_score)
            estimated_eth = sell.get("estimated_eth_value", 0)
            confidence = sell.get("confidence", "LOW")
            method = sell.get("sell_method", "UNKNOWN")
            is_base_native = sell.get("is_base_native", False)
            
            # Network-specific multipliers
            confidence_multipliers = {"HIGH": 1.0, "MEDIUM": 0.9, "LOW": 0.6}
            method_multipliers = {
                "CEX": 2.0, "TELEGRAM_BOT": 1.8, "MEV_BOT": 1.6,
                "DEX": 1.4, "P2P_OTC": 1.3, "UNKNOWN": 1.0
            }
            
            # Base native penalty
            native_multiplier = 1.5 if (self.network == "base" and is_base_native) else 1.0
            
            confidence_mult = confidence_multipliers.get(confidence, 0.5)
            method_mult = method_multipliers.get(method, 1.0)
            
            if estimated_eth > 0:
                wallet_quality_multiplier = (max_possible_wallet_score - wallet_score + 100) / 100
                eth_component = math.log(1 + estimated_eth * 1000) * 2
                weighted_eth_score += eth_component * wallet_quality_multiplier * confidence_mult * method_mult * native_multiplier
        
        # Use parent class consensus calculation
        score_components = self.calculate_score_components(wallet_scores, max_possible_wallet_score)
        weighted_consensus_score = score_components["weighted_consensus"]
        
        # Network bonus
        network_bonus = 1.2 if self.network == "base" else 1.0
        
        final_score = (weighted_eth_score * weighted_consensus_score * network_bonus) / 10
        return round(final_score, 2)
    
    def get_ranked_tokens(self, token_summary: Dict) -> List[tuple]:
        """Get tokens ranked by sell pressure score"""
        scored_tokens = []
        
        for token, data in token_summary.items():
            sell_score = self.calculate_token_sell_score(data)
            scored_tokens.append((token, data, sell_score))
        
        return sorted(scored_tokens, key=lambda x: x[2], reverse=True)
    
    def analyze_wallet_purchases(self, wallet_address: str, days_back: int) -> List[Dict]:
        """Not used for sell tracker, but required by abstract base"""
        return []
    
    def analyze_all_trading_methods(self, num_wallets: int = 174, days_back: int = 1) -> Dict:
        """Analyze all sell methods - main entry point"""
        return self.analyze_all_sell_methods(num_wallets, days_back)
    
    def analyze_all_sell_methods(self, num_wallets: int = 174, days_back: int = 1) -> Dict:
        """Analyze ALL sell methods on any network"""
        logger.info(f"Starting comprehensive {self.network} sell pressure analysis: {num_wallets} wallets, {days_back} days")
        
        top_wallets = self.get_top_wallets(num_wallets)
        
        if not top_wallets:
            logger.warning(f"No {self.network} wallets found in database!")
            return {}
        
        all_sells = []
        token_summary = {}
        method_summary = {"DEX": 0, "CEX": 0, "TELEGRAM_BOT": 0, "MEV_BOT": 0, "P2P_OTC": 0, "UNKNOWN": 0}
        
        # Network-specific summary
        network_summary = {}
        if self.network == "base":
            network_summary = {"native": 0, "bridged": 0}
        
        for i, wallet in enumerate(top_wallets, 1):
            wallet_address = wallet["address"]
            wallet_score = wallet["score"]
            
            logger.info(f"[{i}/{num_wallets}] {self.network.title()} Wallet: {wallet_address} (Score: {wallet_score})")
            
            try:
                sells = self.analyze_wallet_sells(wallet_address, days_back)
                
                # Add wallet score
                for sell in sells:
                    sell["wallet_score"] = wallet_score
                
                all_sells.extend(sells)
                
                # Aggregate data
                self._aggregate_sell_data(sells, token_summary, method_summary, network_summary, wallet_address)
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Error analyzing {self.network} wallet {wallet_address}: {e}")
                continue
        
        return self._generate_sell_analysis(all_sells, token_summary, method_summary, network_summary)
    
    def _aggregate_sell_data(self, sells, token_summary, method_summary, network_summary, wallet_address):
        """Aggregate sell data into summaries"""
        for sell in sells:
            token = sell["token_sold"]
            method = sell["sell_method"]
            estimated_eth = sell.get("estimated_eth_value", 0)
            is_base_native = sell.get("is_base_native", False)
            
            # Token summary
            if token not in token_summary:
                token_summary[token] = {
                    "count": 0, "wallets": set(), "total_estimated_eth": 0,
                    "wallet_scores": [], "sells": [], "methods": set(),
                    "platforms": set(), "confidence_levels": set(),
                    "is_base_native": is_base_native
                }
            
            token_summary[token]["count"] += 1
            token_summary[token]["wallets"].add(wallet_address)
            token_summary[token]["total_estimated_eth"] += estimated_eth
            token_summary[token]["wallet_scores"].append(sell.get("wallet_score", 300))
            token_summary[token]["sells"].append(sell)
            token_summary[token]["methods"].add(method)
            token_summary[token]["platforms"].add(sell.get("platform", "Unknown"))
            token_summary[token]["confidence_levels"].add(sell.get("confidence", "LOW"))
            
            # Method summary
            method_summary[method] += 1
            
            # Network-specific summary
            if self.network == "base" and isinstance(network_summary, dict):
                if is_base_native:
                    network_summary["native"] += 1
                else:
                    network_summary["bridged"] += 1
    
    def _generate_sell_analysis(self, all_sells, token_summary, method_summary, network_summary):
        """Generate comprehensive sell analysis results"""
        logger.info(f"Generating {self.network} sell analysis...")
        
        if not all_sells:
            logger.info(f"✅ No significant {self.network} sell pressure detected!")
            return {}
        
        total_estimated_eth = sum(sell.get("estimated_eth_value", 0) for sell in all_sells)
        total_estimated_usd = sum(sell.get("estimated_usd_value", 0) for sell in all_sells)
        
        ranked_tokens = self.get_ranked_tokens(token_summary)
        
        logger.info(f"{self.network.title()} sell analysis complete: {len(all_sells)} sells, {len(token_summary)} tokens, {total_estimated_eth:.4f} ETH")
        
        result = {
            "total_sells": len(all_sells),
            "unique_tokens": len(token_summary),
            "total_estimated_eth": total_estimated_eth,
            "total_estimated_usd": total_estimated_usd,
            "ranked_tokens": ranked_tokens,
            "method_summary": method_summary,
            "all_sells": all_sells
        }
        
        # Add network-specific data
        if self.network == "base" and network_summary:
            result["base_native_summary"] = network_summary
        
        return result

# Convenience classes for specific networks
class EthComprehensiveSellTracker(ComprehensiveSellTracker):
    def __init__(self):
        super().__init__("ethereum")

class BaseComprehensiveSellTracker(ComprehensiveSellTracker):
    def __init__(self):
        super().__init__("base")

def main():
    """Test the refactored sell tracker"""
    # Test both networks
    for network in ["ethereum", "base"]:
        logger.info(f"Testing {network} sell tracker...")
        tracker = ComprehensiveSellTracker(network)
        
        if tracker.test_connection():
            results = tracker.analyze_all_sell_methods(num_wallets=5, days_back=1)
            logger.info(f"{network.title()} results: {len(results.get('ranked_tokens', []))} tokens")
        else:
            logger.error(f"Failed to connect to {network}")

if __name__ == "__main__":
    main()