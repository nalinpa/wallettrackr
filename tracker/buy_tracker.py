from .tracker_utils import BaseTracker, NetworkSpecificMixins
from typing import List, Dict
import math
import time
import logging

logger = logging.getLogger(__name__)

class ComprehensiveBuyTracker(BaseTracker, NetworkSpecificMixins.BaseMixin):
    """Universal buy tracker with enhanced logging and progress tracking"""
    
    def __init__(self, network="base"):
        super().__init__(network)
    
    def safe_float_conversion(self, value, default=0.0):
        """Safely convert value to float, handling None and invalid values"""
        if value is None:
            return default
        
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"Could not convert value to float: {value} (type: {type(value)})")
            return default
    
    def analyze_wallet_purchases(self, wallet_address: str, days_back: int = 1) -> List[Dict]:
        """Analyze token purchases with proper error handling and detailed logging"""
        logger.info(f"Analyzing {self.network} purchases for: {wallet_address}")

        start_block, end_block = self.get_recent_block_range(days_back)
        
        # Get transfers with progress indication
        print(f"🔍 Fetching {self.network} transfers for {wallet_address[:10]}...")
        
        outgoing_result = self.make_alchemy_request("alchemy_getAssetTransfers", [{
            "fromAddress": wallet_address,
            "fromBlock": start_block,
            "toBlock": end_block,
            "category": ["external", "erc20"],
            "withMetadata": True,
            "excludeZeroValue": True,
            "maxCount": "0x20"
        }])
        
        incoming_result = self.make_alchemy_request("alchemy_getAssetTransfers", [{
            "toAddress": wallet_address,
            "fromBlock": start_block,
            "toBlock": end_block,
            "category": ["erc20"],
            "withMetadata": True,
            "excludeZeroValue": True,
            "maxCount": "0x20"
        }])
        
        outgoing_transfers = outgoing_result.get("result", {}).get("transfers", [])
        incoming_transfers = incoming_result.get("result", {}).get("transfers", [])
        
        logger.debug(f"Found {len(outgoing_transfers)} outgoing, {len(incoming_transfers)} incoming transfers")
        print(f"📊 Found {len(outgoing_transfers)} outgoing, {len(incoming_transfers)} incoming transfers")
        
        # Process transfers
        tx_groups = {}
        potential_purchases = 0
        
        print(f"🔄 Processing outgoing transfers...")
        for transfer in outgoing_transfers:
            tx_hash = transfer.get("hash")
            to_address = transfer.get("to", "").lower()
            
            if not tx_hash or not to_address:
                continue
            
            contract_info = self.get_contract_info(to_address)
            
            if (contract_info["type"] != "UNKNOWN" or self._looks_like_trading_transaction(transfer)) and \
               self.is_significant_purchase_safe(transfer):
                if tx_hash not in tx_groups:
                    tx_groups[tx_hash] = {"outgoing": [], "incoming": []}
                tx_groups[tx_hash]["outgoing"].append(transfer)
                potential_purchases += 1
        
        print(f"🎯 Found {potential_purchases} potential purchase transactions")
        
        # Add incoming transfers
        print(f"🔄 Matching incoming transfers...")
        for transfer in incoming_transfers:
            tx_hash = transfer.get("hash")
            if tx_hash and tx_hash in tx_groups:
                tx_groups[tx_hash]["incoming"].append(transfer)
        
        matched_transactions = len([tx for tx in tx_groups.values() if tx["incoming"]])
        print(f"✅ Matched {matched_transactions} complete purchase transactions")
        
        # Extract purchases
        purchases = []
        platform_counts = {}
        
        print(f"🔍 Extracting purchase details...")
        for tx_hash, transfers in tx_groups.items():
            if transfers["outgoing"] and transfers["incoming"]:
                outgoing = transfers["outgoing"][0]
                to_address = outgoing.get("to", "").lower()
                contract_info = self.get_contract_info(to_address)
                
                for incoming in transfers["incoming"]:
                    token_received = incoming.get("asset")
                    
                    if not self.is_interesting_token(token_received):
                        continue
                    
                    # Safe value conversions
                    amount_received = self.safe_float_conversion(incoming.get("value"))
                    token_sent = outgoing.get("asset", "ETH")
                    amount_sold = self.safe_float_conversion(outgoing.get("value"))
                    
                    if token_received != token_sent and amount_received > 0:
                        eth_spent = amount_sold if outgoing.get("asset") == "ETH" else 0
                        
                        if eth_spent == 0 and amount_sold > 0:
                            sent_usd = self.estimate_usd_value(amount_sold, token_sent)
                            eth_spent = sent_usd / 2000 if sent_usd > 0 else 0
                        
                        is_base_native = self.is_base_native_token(token_received) if token_received else False
                        
                        # Safe block number conversion
                        block_num_str = incoming.get("blockNum", "0x0")
                        try:
                            block_number = int(block_num_str, 16) if block_num_str else 0
                        except (ValueError, TypeError):
                            block_number = 0
                        
                        # Safe contract address extraction
                        contract_address = ""
                        raw_contract = incoming.get("rawContract", {})
                        if isinstance(raw_contract, dict):
                            contract_address = raw_contract.get("address", "")
                        
                        platform = contract_info["platform"]
                        platform_counts[platform] = platform_counts.get(platform, 0) + 1
                        
                        purchase = {
                            "transaction_hash": tx_hash,
                            "platform": platform,
                            "contract_name": contract_info["name"],
                            "contract_type": contract_info["type"],
                            "token_bought": token_received or "UNKNOWN",
                            "amount_received": amount_received,
                            "token_sold": token_sent,
                            "amount_sold": amount_sold,
                            "eth_spent": eth_spent,
                            "block_number": block_number,
                            "contract_address": contract_address,
                            "is_base_native": is_base_native,
                            "estimated_usd_value": self.estimate_usd_value(amount_received, token_received) if token_received else 0
                        }
                        
                        purchases.append(purchase)
                        
                        # Detailed logging like sell tracker
                        platform_emoji = {
                            "Uniswap": "🦄", "PancakeSwap": "🥞", "SushiSwap": "🍣",
                            "1inch": "🔄", "0x": "⚡", "Telegram Bot": "🤖",
                            "Unknown": "❓"
                        }
                        native_flag = "🔵" if is_base_native else ""
                        
                        logger.debug(f"{platform_emoji.get(platform, '🔄')} {native_flag}BOUGHT: {token_received} ({amount_received:.0f}) via {platform} | ~${self.estimate_usd_value(amount_received, token_received):.0f}")
        
        # Summary logging
        if purchases:
            total_eth = sum(p.get("eth_spent", 0) for p in purchases)
            total_usd = sum(p.get("estimated_usd_value", 0) for p in purchases)
            unique_tokens = len(set(p.get("token_bought") for p in purchases))
            
            print(f"💰 Found {len(purchases)} purchases: {unique_tokens} tokens, {total_eth:.4f} ETH (~${total_usd:.0f})")
            
            if platform_counts:
                platform_summary = ", ".join([f"{platform}({count})" for platform, count in platform_counts.items()])
                print(f"🏪 Platforms: {platform_summary}")
        
        logger.info(f"Found {len(purchases)} significant {self.network} token purchases")
        return purchases
    
    def is_significant_purchase_safe(self, transfer: Dict) -> bool:
        """Safe version of is_significant_purchase"""
        asset = transfer.get("asset", "")
        value = transfer.get("value")
        
        value_float = self.safe_float_conversion(value)
        
        if value_float <= 0:
            return False
        
        if asset == "ETH":
            return value_float >= self.min_eth_value
        else:
            estimated_usd = self.estimate_usd_value(value_float, asset)
            estimated_eth = estimated_usd / 2000 if estimated_usd > 0 else 0
            threshold_multiplier = 0.5 if self.network == "base" else 1.0
            return estimated_eth >= (self.min_eth_value * threshold_multiplier)
    
    def _looks_like_trading_transaction(self, transfer: Dict) -> bool:
        """Trading transaction detection with null safety"""
        to_address = transfer.get("to", "").lower()
        asset = transfer.get("asset", "")
        value = self.safe_float_conversion(transfer.get("value"))
        
        if not to_address or value <= 0:
            return False
        
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
        """Calculate alpha score with null safety"""
        wallet_scores = token_data.get("wallet_scores", [])
        purchases = token_data.get("purchases", [])
        total_eth_spent = self.safe_float_conversion(token_data.get("total_eth_spent"))
        
        if not wallet_scores or total_eth_spent <= 0 or not purchases:
            return 0.0
        
        max_possible_wallet_score = 300
        weighted_eth_score = 0.0
        base_native_bonus = 1.0
        
        for purchase in purchases:
            wallet_score = self.safe_float_conversion(purchase.get("wallet_score"), max_possible_wallet_score)
            eth_spent = self.safe_float_conversion(purchase.get("eth_spent"))
            is_base_native = purchase.get("is_base_native", False)
            
            if is_base_native:
                base_native_bonus = 1.3
            
            if eth_spent > 0:
                wallet_quality_multiplier = (max_possible_wallet_score - wallet_score + 100) / 100
                eth_component = math.log(1 + eth_spent) * 10
                weighted_eth_score += eth_component * wallet_quality_multiplier * base_native_bonus
        
        valid_scores = [self.safe_float_conversion(score) for score in wallet_scores if score is not None]
        if not valid_scores:
            return 0.0
            
        score_components = self.calculate_score_components(valid_scores, max_possible_wallet_score)
        weighted_consensus_score = score_components["weighted_consensus"]
        
        base_network_bonus = 1.1
        
        if weighted_consensus_score > 0:
            final_score = (weighted_eth_score * weighted_consensus_score * base_network_bonus) / 10
            return round(final_score, 2)
        
        return 0.0
    
    def get_ranked_tokens(self, token_summary: Dict) -> List[tuple]:
        """Get tokens ranked by alpha score"""
        scored_tokens = []
        
        for token, data in token_summary.items():
            if not token or not isinstance(data, dict):
                continue
                
            alpha_score = self.calculate_token_alpha_score(data)
            scored_tokens.append((token, data, alpha_score))
        
        return sorted(scored_tokens, key=lambda x: x[2], reverse=True)
    
    def analyze_all_trading_methods(self, num_wallets: int = 173, max_wallets_for_sse: bool = False, days_back: int = 1) -> Dict:
        """Main entry point with enhanced logging like sell tracker"""
        logger.info(f"Starting comprehensive {self.network} buy analysis: {num_wallets} wallets, {days_back} days")
        
        # Limit wallets for SSE to prevent hanging
        if max_wallets_for_sse:
            num_wallets = min(num_wallets, 25) 
            logger.info(f"SSE mode: limiting to {num_wallets} wallets")
        
        print(f"🚀 Starting {self.network.title()} Buy Analysis")
        print(f"📊 Target: {num_wallets} wallets, {days_back} days back")
        print(f"🌐 Network: {self.network.title()}")
        print("="*60)
        
        top_wallets = self.get_top_wallets(num_wallets)
        
        if not top_wallets:
            logger.warning(f"No {self.network} wallets found in database!")
            print(f"❌ No {self.network} wallets found in database!")
            return {}
        
        print(f"✅ Retrieved {len(top_wallets)} top {self.network} wallets")
        
        all_purchases = []
        token_summary = {}
        platform_summary = {}
        base_native_summary = {"native": 0, "bridged": 0}
        
        # Progress tracking
        total_purchases = 0
        total_eth_spent = 0
        processed_wallets = 0
        
        for i, wallet in enumerate(top_wallets, 1):
            wallet_address = wallet.get("address", "")
            wallet_score = self.safe_float_conversion(wallet.get("score"), 300)
            
            if not wallet_address:
                logger.warning(f"Wallet {i} has no address, skipping")
                continue
            
            # Progress logging every 5 wallets or first 3
            if i % 5 == 1 or i <= 3:
                print(f"🔄 Processing wallet {i}/{len(top_wallets)}: {wallet_address[:10]}...")
                logger.info(f"Progress: {i}/{len(top_wallets)} wallets processed")
            
            # Progress updates every wallet (matches sell tracker)
            print(f"🔄 [{i}/{len(top_wallets)}] Processing wallet {wallet_address[:8]}... (Score: {wallet_score})")
            
            # Send progress via logger (which gets captured by SSE)
            if i % 5 == 1 or i <= 3:
                logger.info(f"Progress: {i}/{len(top_wallets)} wallets processed")
                logger.info(f"[{i}/{num_wallets}] {self.network.title()} Wallet: {wallet_address} (Score: {wallet_score})")
            
            try:
                purchases = self.analyze_wallet_purchases(wallet_address, days_back)
                
                # Add wallet score to each purchase
                for purchase in purchases:
                    purchase["wallet_score"] = wallet_score
                
                all_purchases.extend(purchases)
                processed_wallets += 1
                
                # Update running totals
                wallet_purchases = len(purchases)
                wallet_eth = sum(self.safe_float_conversion(p.get("eth_spent")) for p in purchases)
                total_purchases += wallet_purchases
                total_eth_spent += wallet_eth
                
                # Aggregate data
                self._aggregate_token_data(purchases, token_summary, platform_summary, base_native_summary, wallet_address)
                
                # Progress summary every 10 wallets
                if i % 10 == 0:
                    avg_purchases = total_purchases / processed_wallets if processed_wallets > 0 else 0
                    print(f"📈 Progress Update: {processed_wallets} wallets, {total_purchases} purchases, {total_eth_spent:.2f} ETH (avg: {avg_purchases:.1f} purchases/wallet)")
                
                time.sleep(0.5)  # Rate limiting
                
                # Memory cleanup every 10 wallets
                if i % 10 == 0:
                    import gc
                    gc.collect()
                    logger.debug(f"Memory cleanup at wallet {i}")
                
            except Exception as e:
                logger.error(f"Error analyzing {self.network} wallet {wallet_address}: {e}")
                print(f"❌ Error analyzing wallet {wallet_address[:10]}: {str(e)[:50]}...")
                continue
        
        return self._generate_comprehensive_analysis(all_purchases, token_summary, platform_summary, base_native_summary)
    
    def _aggregate_token_data(self, purchases, token_summary, platform_summary, base_native_summary, wallet_address):
        """Aggregate purchase data with enhanced tracking"""
        for purchase in purchases:
            token = purchase.get("token_bought")
            platform = purchase.get("platform", "Unknown")
            amount = self.safe_float_conversion(purchase.get("amount_received"))
            eth_spent = self.safe_float_conversion(purchase.get("eth_spent"))
            is_base_native = purchase.get("is_base_native", False)
            
            if not token:
                continue
            
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
            
            wallet_score = purchase.get("wallet_score")
            if wallet_score is not None:
                token_summary[token]["wallet_scores"].append(wallet_score)
            
            token_summary[token]["purchases"].append(purchase)
            token_summary[token]["total_usd_value"] += self.safe_float_conversion(purchase.get("estimated_usd_value"))
            
            platform_summary[platform] = platform_summary.get(platform, 0) + 1
            
            # Network-specific tracking
            if is_base_native:
                base_native_summary["native"] += 1
            else:
                base_native_summary["bridged"] += 1
    
    def _generate_comprehensive_analysis(self, all_purchases, token_summary, platform_summary, base_native_summary):
        """Generate analysis results with detailed summary"""
        logger.info(f"Generating {self.network} comprehensive analysis...")
        print(f"📊 Generating {self.network.title()} Analysis Results...")
        
        if not all_purchases:
            logger.warning(f"No {self.network} token purchases found")
            print(f"❌ No significant {self.network} token purchases found!")
            return {}
        
        total_eth_spent = sum(self.safe_float_conversion(purchase.get("eth_spent")) for purchase in all_purchases)
        total_usd_spent = sum(self.safe_float_conversion(purchase.get("estimated_usd_value")) for purchase in all_purchases)
        
        ranked_tokens = self.get_ranked_tokens(token_summary)
        
        # Enhanced summary output
        unique_wallets = len(set(p.get("wallet_score") for p in all_purchases))
        avg_eth_per_purchase = total_eth_spent / len(all_purchases) if all_purchases else 0
        
        print("="*60)
        print(f"🎉 {self.network.title()} Buy Analysis Complete!")
        print(f"📊 Total Purchases: {len(all_purchases)}")
        print(f"🪙 Unique Tokens: {len(token_summary)}")
        print(f"💰 Total ETH Spent: {total_eth_spent:.4f} ETH")
        print(f"💵 Total USD Value: ${total_usd_spent:.0f}")
        print(f"📈 Average per Purchase: {avg_eth_per_purchase:.4f} ETH")
        
        if ranked_tokens:
            print(f"🏆 Top Token: {ranked_tokens[0][0]} (Score: {ranked_tokens[0][2]})")
        
        # Platform breakdown
        if platform_summary:
            print("🏪 Platform Breakdown:")
            for platform, count in sorted(platform_summary.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / len(all_purchases)) * 100
                print(f"   {platform}: {count} ({percentage:.1f}%)")
        
        # Base native breakdown (if applicable)
        if self.network == "base" and base_native_summary:
            native_count = base_native_summary["native"]
            bridged_count = base_native_summary["bridged"]
            total_count = native_count + bridged_count
            if total_count > 0:
                native_pct = (native_count / total_count) * 100
                print(f"🔵 Base Native: {native_count} ({native_pct:.1f}%), Bridged: {bridged_count} ({100-native_pct:.1f}%)")
        
        print("="*60)
        
        logger.info(f"{self.network.title()} analysis complete: {len(all_purchases)} purchases, {len(token_summary)} tokens, {total_eth_spent:.4f} ETH")
        
        result = {
            "total_purchases": len(all_purchases),
            "unique_tokens": len(token_summary),
            "total_eth_spent": total_eth_spent,
            "total_usd_spent": total_usd_spent,
            "ranked_tokens": ranked_tokens,
            "platform_summary": platform_summary,
            "all_purchases": all_purchases
        }
        
        # Add network-specific data
        if self.network == "base" and base_native_summary:
            result["base_native_summary"] = base_native_summary
        
        return result

# Convenience class for Ethereum
class EthComprehensiveTracker(ComprehensiveBuyTracker):
    def __init__(self):
        super().__init__("ethereum")