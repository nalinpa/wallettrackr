from .tracker_utils import BaseTracker, NetworkSpecificMixins
from typing import List, Dict
import math
import time
import logging

logger = logging.getLogger(__name__)

class ComprehensiveBuyTracker(BaseTracker, NetworkSpecificMixins.BaseMixin):
    """Base network buy tracker using centralized utilities"""
    
    def __init__(self):
        super().__init__("base")
    
    def analyze_wallet_purchases(self, wallet_address: str, days_back: int = 1) -> List[Dict]:
        """Analyze token purchases on Base network"""
        logger.info(f"Analyzing Base purchases for: {wallet_address}")
        
        start_block, end_block = self.get_recent_block_range(days_back)
        
        # Get transfers using parent class method
        outgoing_result = self.make_alchemy_request("alchemy_getAssetTransfers", [{
            "fromAddress": wallet_address,
            "fromBlock": start_block,
            "toBlock": end_block,
            "category": ["external", "erc20"],
            "withMetadata": True,
            "excludeZeroValue": True,
            "maxCount": "0x64"
        }])
        
        incoming_result = self.make_alchemy_request("alchemy_getAssetTransfers", [{
            "toAddress": wallet_address,
            "fromBlock": start_block,
            "toBlock": end_block,
            "category": ["erc20"],
            "withMetadata": True,
            "excludeZeroValue": True,
            "maxCount": "0x64"
        }])
        
        outgoing_transfers = outgoing_result.get("result", {}).get("transfers", [])
        incoming_transfers = incoming_result.get("result", {}).get("transfers", [])
        
        logger.debug(f"Found {len(outgoing_transfers)} outgoing, {len(incoming_transfers)} incoming transfers")
        
        # Process transfers using centralized logic
        tx_groups = {}
        
        for transfer in outgoing_transfers:
            tx_hash = transfer.get("hash")
            to_address = transfer.get("to", "").lower()
            
            # Use centralized contract info
            contract_info = self.get_contract_info(to_address)
            
            # Check if significant using parent method
            if (contract_info["type"] != "UNKNOWN" or self._looks_like_trading_transaction(transfer)) and \
               self.is_significant_purchase(transfer):
                if tx_hash not in tx_groups:
                    tx_groups[tx_hash] = {"outgoing": [], "incoming": []}
                tx_groups[tx_hash]["outgoing"].append(transfer)
        
        # Add incoming transfers
        for transfer in incoming_transfers:
            tx_hash = transfer.get("hash")
            if tx_hash in tx_groups:
                tx_groups[tx_hash]["incoming"].append(transfer)
        
        # Extract purchases
        purchases = []
        
        for tx_hash, transfers in tx_groups.items():
            if transfers["outgoing"] and transfers["incoming"]:
                outgoing = transfers["outgoing"][0]
                to_address = outgoing.get("to", "").lower()
                contract_info = self.get_contract_info(to_address)
                
                for incoming in transfers["incoming"]:
                    token_received = incoming.get("asset")
                    
                    # Use centralized token checking
                    if not self.is_interesting_token(token_received):
                        continue
                    
                    amount_received = float(incoming.get("value", 0))
                    token_sent = outgoing.get("asset", "ETH")
                    
                    if token_received != token_sent:
                        eth_spent = float(outgoing.get("value", 0)) if outgoing.get("asset") == "ETH" else 0
                        
                        if eth_spent == 0:
                            # Use centralized USD estimation
                            sent_usd = self.estimate_usd_value(float(outgoing.get("value", 0)), token_sent)
                            eth_spent = sent_usd / 2000
                        
                        # Check if Base native using mixin
                        is_base_native = self.is_base_native_token(token_received)
                        
                        purchase = {
                            "transaction_hash": tx_hash,
                            "platform": contract_info["platform"],
                            "contract_name": contract_info["name"],
                            "contract_type": contract_info["type"],
                            "token_bought": token_received,
                            "amount_received": amount_received,
                            "token_sold": token_sent,
                            "amount_sold": float(outgoing.get("value", 0)),
                            "eth_spent": eth_spent,
                            "block_number": int(incoming.get("blockNum", "0x0"), 16),
                            "contract_address": incoming.get("rawContract", {}).get("address", ""),
                            "is_base_native": is_base_native,
                            "estimated_usd_value": self.estimate_usd_value(amount_received, token_received)
                        }
                        
                        purchases.append(purchase)
                        
                        native_flag = "🔵" if is_base_native else ""
                        eth_display = f" (spent {eth_spent:.4f} ETH)" if eth_spent > 0 else ""
                        logger.debug(f"BOUGHT: {native_flag}{token_received} ({amount_received:.2f}) via {contract_info['platform']}{eth_display}")
        
        logger.info(f"Found {len(purchases)} significant Base token purchases")
        return purchases
    
    def _looks_like_trading_transaction(self, transfer: Dict) -> bool:
        """Base-specific trading transaction detection"""
        to_address = transfer.get("to", "").lower()
        asset = transfer.get("asset", "")
        value = float(transfer.get("value", 0))
        
        trading_indicators = [
            len(set(to_address[2:])) >= 10,
            to_address.startswith("0x1111"),
            to_address.startswith("0x3333"),
            to_address.startswith("0x7777"),
            value >= 1000,
            asset == "USDC" and value >= 50,
            asset == "ETH" and value >= 0.005,
        ]
        
        return any(trading_indicators)
    
    def calculate_token_alpha_score(self, token_data: Dict) -> float:
        """Calculate alpha score with Base-specific bonuses"""
        wallet_scores = token_data["wallet_scores"]
        purchases = token_data["purchases"]
        total_eth_spent = token_data["total_eth_spent"]
        
        if not wallet_scores or total_eth_spent == 0 or not purchases:
            return 0.0
        
        max_possible_wallet_score = 300
        weighted_eth_score = 0.0
        base_native_bonus = 1.0
        
        for purchase in purchases:
            wallet_score = purchase.get("wallet_score", max_possible_wallet_score)
            eth_spent = purchase.get("eth_spent", 0)
            is_base_native = purchase.get("is_base_native", False)
            
            if is_base_native:
                base_native_bonus = 1.3  # 30% bonus for Base native tokens
            
            if eth_spent > 0:
                wallet_quality_multiplier = (max_possible_wallet_score - wallet_score + 100) / 100
                eth_component = math.log(1 + eth_spent) * 10
                weighted_eth_score += eth_component * wallet_quality_multiplier * base_native_bonus
        
        # Use parent class score calculation
        score_components = self.calculate_score_components(wallet_scores, max_possible_wallet_score)
        weighted_consensus_score = score_components["weighted_consensus"]
        
        # Base network early adoption bonus
        base_network_bonus = 1.1
        
        final_score = (weighted_eth_score * weighted_consensus_score * base_network_bonus) / 10
        return round(final_score, 2)
    
    def get_ranked_tokens(self, token_summary: Dict) -> List[tuple]:
        """Get tokens ranked by alpha score"""
        scored_tokens = []
        
        for token, data in token_summary.items():
            alpha_score = self.calculate_token_alpha_score(data)
            scored_tokens.append((token, data, alpha_score))
        
        return sorted(scored_tokens, key=lambda x: x[2], reverse=True)
    
    def analyze_all_trading_methods(self, num_wallets: int = 174, days_back: int = 1) -> Dict:
        """Analyze ALL trading methods on Base - main entry point"""
        logger.info(f"Starting comprehensive Base trading analysis: {num_wallets} wallets, {days_back} days")
        
        top_wallets = self.get_top_wallets(num_wallets)
        
        if not top_wallets:
            logger.warning("No Base wallets found in database!")
            return {}
        
        all_purchases = []
        token_summary = {}
        platform_summary = {}
        base_native_summary = {"native": 0, "bridged": 0}
        
        for i, wallet in enumerate(top_wallets, 1):
            wallet_address = wallet["address"]
            wallet_score = wallet["score"]
            
            logger.info(f"[{i}/{num_wallets}] Base Wallet: {wallet_address} (Score: {wallet_score})")
            
            try:
                purchases = self.analyze_wallet_purchases(wallet_address, days_back)
                
                # Add wallet score to each purchase
                for purchase in purchases:
                    purchase["wallet_score"] = wallet_score
                
                all_purchases.extend(purchases)
                
                # Aggregate using centralized logic
                self._aggregate_token_data(purchases, token_summary, platform_summary, base_native_summary, wallet_address)
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Error analyzing Base wallet {wallet_address}: {e}")
                continue
        
        return self._generate_comprehensive_analysis(all_purchases, token_summary, platform_summary, base_native_summary)
    
    def _aggregate_token_data(self, purchases, token_summary, platform_summary, base_native_summary, wallet_address):
        """Aggregate purchase data into summaries"""
        for purchase in purchases:
            token = purchase["token_bought"]
            platform = purchase["platform"]
            amount = purchase["amount_received"]
            eth_spent = purchase.get("eth_spent", 0)
            is_base_native = purchase.get("is_base_native", False)
            
            # Token summary
            if token not in token_summary:
                token_summary[token] = {
                    "count": 0, "wallets": set(), "total_amount": 0,
                    "platforms": set(), "total_eth_spent": 0, "wallet_scores": [],
                    "purchases": [], "is_base_native": is_base_native, "total_usd_value": 0
                }
            
            token_summary[token]["count"] += 1
            token_summary[token]["wallets"].add(wallet_address)
            token_summary[token]["total_amount"] += amount
            token_summary[token]["platforms"].add(platform)
            token_summary[token]["total_eth_spent"] += eth_spent
            token_summary[token]["wallet_scores"].append(purchase.get("wallet_score", 300))
            token_summary[token]["purchases"].append(purchase)
            token_summary[token]["total_usd_value"] += purchase.get("estimated_usd_value", 0)
            
            # Platform summary
            platform_summary[platform] = platform_summary.get(platform, 0) + 1
            
            # Base native summary
            if is_base_native:
                base_native_summary["native"] += 1
            else:
                base_native_summary["bridged"] += 1
    
    def _generate_comprehensive_analysis(self, all_purchases, token_summary, platform_summary, base_native_summary):
        """Generate comprehensive analysis results"""
        logger.info("Generating Base comprehensive analysis...")
        
        if not all_purchases:
            logger.warning("No Base alpha token purchases found")
            return {}
        
        total_eth_spent = sum(purchase.get("eth_spent", 0) for purchase in all_purchases)
        total_usd_spent = sum(purchase.get("estimated_usd_value", 0) for purchase in all_purchases)
        
        # Get ranked tokens
        ranked_tokens = self.get_ranked_tokens(token_summary)
        
        logger.info(f"Base analysis complete: {len(all_purchases)} purchases, {len(token_summary)} tokens, {total_eth_spent:.4f} ETH")
        
        return {
            "total_purchases": len(all_purchases),
            "unique_tokens": len(token_summary),
            "total_eth_spent": total_eth_spent,
            "total_usd_spent": total_usd_spent,
            "ranked_tokens": ranked_tokens,
            "platform_summary": platform_summary,
            "base_native_summary": base_native_summary,
            "all_purchases": all_purchases
        }

# Entry point
def main():
    """Test the refactored tracker"""
    tracker = BaseComprehensiveTracker()
    
    logger.info("🔵 BASE NETWORK COMPREHENSIVE TRADING TRACKER")
    logger.info("=" * 50)
    logger.info("Using centralized utilities - no code duplication!")
    
    if not tracker.test_connection():
        logger.error("❌ Connection failed")
        return
    
    try:
        results = tracker.analyze_all_trading_methods(num_wallets=10, days_back=1)
        
        if results and results.get("ranked_tokens"):
            logger.info(f"✅ SUCCESS: Found Base alpha trading activity!")
            logger.info(f"💰 Total: {results.get('total_eth_spent', 0):.4f} ETH")
            logger.info(f"🪙 Tokens: {results.get('unique_tokens', 0)} unique alpha tokens")
            
            native_count = results["base_native_summary"]["native"]
            bridged_count = results["base_native_summary"]["bridged"]
            
            logger.info(f"🔵 Base Native purchases: {native_count}")
            logger.info(f"🌉 Bridged/External purchases: {bridged_count}")
            
        else:
            logger.warning("⚠️ No Base activity found")
        
    except Exception as e:
        logger.error(f"❌ Base analysis failed: {e}")

if __name__ == "__main__":
    main()