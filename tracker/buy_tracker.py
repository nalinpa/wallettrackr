from .tracker_utils import EnhancedBaseTracker, NetworkSpecificMixins
from typing import List, Dict
import math
import time
import logging

logger = logging.getLogger(__name__)

class Web3EnhancedBuyTracker(EnhancedBaseTracker, NetworkSpecificMixins.BaseMixin):
    """Enhanced buy tracker with Web3 analysis capabilities"""
    
    def __init__(self, network="base"):
        super().__init__(network)
        self.purchase_cache = {}  # Cache for Web3-enhanced purchases
    
    def analyze_wallet_purchases(self, wallet_address: str, days_back: int = 1) -> List[Dict]:
        """Analyze token purchases with Web3 enhancement"""
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
        
        # Extract purchases with Web3 enhancement
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
                        
                        # Create basic purchase
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
                            "estimated_usd_value": self.estimate_usd_value(amount_received, token_received) if token_received else 0,
                            "wallet_address": wallet_address
                        }
                        
                        # 🚀 NEW: Enhance with Web3 data
                        if self.web3_enabled:
                            enhanced_purchase = self.enhance_purchase_with_web3(purchase, tx_hash)
                            purchases.append(enhanced_purchase)
                            
                            # Enhanced logging with Web3 data
                            web3_data = enhanced_purchase.get('web3_analysis', {})
                            sophistication = enhanced_purchase.get('sophistication_score', 0)
                            method_used = web3_data.get('method_used', 'unknown')
                            
                            platform_emoji = {
                                "Uniswap": "🦄", "PancakeSwap": "🥞", "SushiSwap": "🍣",
                                "1inch": "🔄", "0x": "⚡", "Telegram Bot": "🤖",
                                "Aerodrome": "🚀", "BaseSwap": "🔵", "Unknown": "❓"
                            }
                            native_flag = "🔵" if is_base_native else ""
                            sophistication_flag = "🧠" if sophistication > 70 else "🔰" if sophistication > 40 else ""
                            
                            logger.debug(f"{platform_emoji.get(platform, '🔄')} {native_flag}{sophistication_flag}BOUGHT: {token_received} ({amount_received:.0f}) via {platform} [{method_used}] | ~${self.estimate_usd_value(amount_received, token_received):.0f} | Sophistication: {sophistication:.0f}")
                        else:
                            purchases.append(purchase)
                            
                            # Original logging
                            platform_emoji = {
                                "Uniswap": "🦄", "PancakeSwap": "🥞", "SushiSwap": "🍣",
                                "1inch": "🔄", "0x": "⚡", "Telegram Bot": "🤖",
                                "Unknown": "❓"
                            }
                            native_flag = "🔵" if is_base_native else ""
                            
                            logger.debug(f"{platform_emoji.get(platform, '🔄')} {native_flag}BOUGHT: {token_received} ({amount_received:.0f}) via {platform} | ~${self.estimate_usd_value(amount_received, token_received):.0f}")
        
        # Enhanced summary logging
        if purchases:
            total_eth = sum(p.get("eth_spent", 0) for p in purchases)
            total_usd = sum(p.get("estimated_usd_value", 0) for p in purchases)
            unique_tokens = len(set(p.get("token_bought") for p in purchases))
            
            # Web3 enhanced stats
            if self.web3_enabled and purchases:
                avg_sophistication = sum(p.get('sophistication_score', 0) for p in purchases) / len(purchases)
                high_sophistication_count = len([p for p in purchases if p.get('sophistication_score', 0) > 70])
                sophisticated_methods = set()
                for p in purchases:
                    web3_data = p.get('web3_analysis', {})
                    method = web3_data.get('method_used', 'unknown')
                    if method != 'unknown':
                        sophisticated_methods.add(method)
                
                print(f"💰 Found {len(purchases)} purchases: {unique_tokens} tokens, {total_eth:.4f} ETH (~${total_usd:.0f})")
                print(f"🧠 Avg Sophistication: {avg_sophistication:.1f} | High Sophistication: {high_sophistication_count}")
                if sophisticated_methods:
                    print(f"⚙️  Methods Used: {', '.join(list(sophisticated_methods)[:3])}")
            else:
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
        """Enhanced alpha score calculation with Web3 data"""
        wallet_scores = token_data.get("wallet_scores", [])
        purchases = token_data.get("purchases", [])
        total_eth_spent = self.safe_float_conversion(token_data.get("total_eth_spent"))
        
        if not wallet_scores or total_eth_spent <= 0 or not purchases:
            return 0.0
        
        max_possible_wallet_score = 300
        weighted_eth_score = 0.0
        base_native_bonus = 1.0
        sophistication_bonus = 1.0
        
        # 🚀 NEW: Include Web3 sophistication data
        sophistication_scores = []
        method_diversity = set()
        
        for purchase in purchases:
            wallet_score = self.safe_float_conversion(purchase.get("wallet_score"), max_possible_wallet_score)
            eth_spent = self.safe_float_conversion(purchase.get("eth_spent"))
            is_base_native = purchase.get("is_base_native", False)
            
            # Web3 enhancements
            sophistication = purchase.get("sophistication_score", 0)
            if sophistication > 0:
                sophistication_scores.append(sophistication)
            
            web3_data = purchase.get("web3_analysis", {})
            method_used = web3_data.get("method_used", "unknown")
            if method_used != "unknown":
                method_diversity.add(method_used)
            
            if is_base_native:
                base_native_bonus = 1.3
            
            if eth_spent > 0:
                wallet_quality_multiplier = (max_possible_wallet_score - wallet_score + 100) / 100
                eth_component = math.log(1 + eth_spent) * 10
                
                # 🚀 NEW: Sophistication multiplier
                if sophistication > 0:
                    sophistication_multiplier = 1.0 + (sophistication / 200)  # Up to 1.5x for 100 sophistication
                else:
                    sophistication_multiplier = 1.0
                
                weighted_eth_score += eth_component * wallet_quality_multiplier * base_native_bonus * sophistication_multiplier
        
        # 🚀 NEW: Calculate sophistication bonus
        if sophistication_scores:
            avg_sophistication = sum(sophistication_scores) / len(sophistication_scores)
            sophistication_bonus = 1.0 + (avg_sophistication / 500)  # Up to 1.2x for high sophistication
            
            # Method diversity bonus
            if len(method_diversity) > 1:
                sophistication_bonus *= 1.1  # 10% bonus for method diversity
        
        valid_scores = [self.safe_float_conversion(score) for score in wallet_scores if score is not None]
        if not valid_scores:
            return 0.0
            
        score_components = self.calculate_score_components(valid_scores, max_possible_wallet_score)
        weighted_consensus_score = score_components["weighted_consensus"]
        
        base_network_bonus = 1.1 if self.network == "base" else 1.0
        
        if weighted_consensus_score > 0:
            final_score = (weighted_eth_score * weighted_consensus_score * base_network_bonus * sophistication_bonus) / 10
            return round(final_score, 2)
        
        return 0.0
    
    def get_ranked_tokens(self, token_summary: Dict) -> List[tuple]:
        """Get tokens ranked by enhanced alpha score"""
        scored_tokens = []
        
        for token, data in token_summary.items():
            if not token or not isinstance(data, dict):
                continue
                
            alpha_score = self.calculate_token_alpha_score(data)
            scored_tokens.append((token, data, alpha_score))
        
        return sorted(scored_tokens, key=lambda x: x[2], reverse=True)
    
    def analyze_all_trading_methods(self, num_wallets: int = 173, max_wallets_for_sse: bool = False, days_back: int = 1) -> Dict:
        """Main entry point with Web3 enhancements"""
        logger.info(f"Starting comprehensive {self.network} buy analysis: {num_wallets} wallets, {days_back} days")
        
        # Limit wallets for SSE to prevent hanging
        if max_wallets_for_sse:
            num_wallets = min(num_wallets, 25) 
            logger.info(f"SSE mode: limiting to {num_wallets} wallets")
        
        print(f"🚀 Starting {self.network.title()} Buy Analysis")
        print(f"📊 Target: {num_wallets} wallets, {days_back} days back")
        print(f"🌐 Network: {self.network.title()}")
        if self.web3_enabled:
            print(f"⚡ Web3 Enhanced Analysis Enabled")
        print("="*60)
        
        top_wallets = self.get_top_wallets(num_wallets)
        
        if not top_wallets:
            logger.warning(f"No {self.network} wallets found in database!")
            print(f"❌ No {self.network} wallets found in database!")
            return {}
        
        print(f"✅ Retrieved {len(top_wallets)} top {self.network} wallets")
        
        # Enhanced with Web3 wallet analysis
        if self.web3_enabled and len(top_wallets) > 0:
            enhanced_wallets = [w for w in top_wallets if w.get('web3_analysis')]
            if enhanced_wallets:
                avg_sophistication = sum(w['web3_analysis'].get('sophistication_score', 0) for w in enhanced_wallets) / len(enhanced_wallets)
                print(f"🧠 Average wallet sophistication: {avg_sophistication:.1f}")
        
        all_purchases = []
        token_summary = {}
        platform_summary = {}
        base_native_summary = {"native": 0, "bridged": 0}
        
        # Web3 enhanced tracking
        web3_analysis_summary = {
            "total_transactions_analyzed": 0,
            "sophisticated_transactions": 0,
            "method_distribution": {},
            "avg_sophistication": 0,
            "gas_efficiency_avg": 0
        }
        
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
            
            # Progress logging with Web3 awareness
            if i % 5 == 1 or i <= 3:
                sophistication_info = ""
                if self.web3_enabled and wallet.get('web3_analysis'):
                    wallet_sophistication = wallet['web3_analysis'].get('sophistication_score', 0)
                    sophistication_info = f" (Sophistication: {wallet_sophistication:.0f})"
                
                print(f"🔄 Processing wallet {i}/{len(top_wallets)}: {wallet_address[:10]}...{sophistication_info}")
                logger.info(f"Progress: {i}/{len(top_wallets)} wallets processed")
            
            # Progress updates every wallet
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
                
                # 🚀 NEW: Update Web3 analysis summary
                if self.web3_enabled:
                    for purchase in purchases:
                        web3_data = purchase.get('web3_analysis', {})
                        if web3_data:
                            web3_analysis_summary["total_transactions_analyzed"] += 1
                            
                            sophistication = purchase.get('sophistication_score', 0)
                            if sophistication > 70:
                                web3_analysis_summary["sophisticated_transactions"] += 1
                            
                            method = web3_data.get('method_used', 'unknown')
                            if method != 'unknown':
                                web3_analysis_summary["method_distribution"][method] = web3_analysis_summary["method_distribution"].get(method, 0) + 1
                            
                            gas_efficiency = web3_data.get('gas_efficiency', 0)
                            if gas_efficiency > 0:
                                current_avg = web3_analysis_summary["gas_efficiency_avg"]
                                count = web3_analysis_summary["total_transactions_analyzed"]
                                web3_analysis_summary["gas_efficiency_avg"] = ((current_avg * (count - 1)) + gas_efficiency) / count
                
                # Aggregate data
                self._aggregate_token_data(purchases, token_summary, platform_summary, base_native_summary, wallet_address)
                
                # Enhanced progress summary every 10 wallets
                if i % 10 == 0:
                    avg_purchases = total_purchases / processed_wallets if processed_wallets > 0 else 0
                    progress_msg = f"📈 Progress Update: {processed_wallets} wallets, {total_purchases} purchases, {total_eth_spent:.2f} ETH (avg: {avg_purchases:.1f} purchases/wallet)"
                    
                    if self.web3_enabled and web3_analysis_summary["total_transactions_analyzed"] > 0:
                        sophisticated_pct = (web3_analysis_summary["sophisticated_transactions"] / web3_analysis_summary["total_transactions_analyzed"]) * 100
                        progress_msg += f" | 🧠 {sophisticated_pct:.1f}% sophisticated"
                    
                    print(progress_msg)
                
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
        
        return self._generate_comprehensive_analysis(all_purchases, token_summary, platform_summary, base_native_summary, web3_analysis_summary)
    
    def _aggregate_token_data(self, purchases, token_summary, platform_summary, base_native_summary, wallet_address):
        """Enhanced aggregation with Web3 data"""
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
                    "purchases": [], "is_base_native": is_base_native, "total_usd_value": 0,
                    # 🚀 NEW: Web3 enhanced fields
                    "web3_enhanced": self.web3_enabled,
                    "sophistication_scores": [],
                    "methods_used": set(),
                    "avg_gas_efficiency": 0,
                    "high_sophistication_count": 0
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
            
            # 🚀 NEW: Web3 enhanced aggregation
            if self.web3_enabled:
                sophistication = purchase.get("sophistication_score", 0)
                if sophistication > 0:
                    token_summary[token]["sophistication_scores"].append(sophistication)
                    if sophistication > 70:
                        token_summary[token]["high_sophistication_count"] += 1
                
                web3_data = purchase.get("web3_analysis", {})
                method = web3_data.get("method_used", "unknown")
                if method != "unknown":
                    token_summary[token]["methods_used"].add(method)
                
                gas_efficiency = web3_data.get("gas_efficiency", 0)
                if gas_efficiency > 0:
                    current_avg = token_summary[token]["avg_gas_efficiency"]
                    count = len(token_summary[token]["sophistication_scores"])
                    if count > 0:
                        token_summary[token]["avg_gas_efficiency"] = ((current_avg * (count - 1)) + gas_efficiency) / count
            
            platform_summary[platform] = platform_summary.get(platform, 0) + 1
            
            # Network-specific tracking
            if is_base_native:
                base_native_summary["native"] += 1
            else:
                base_native_summary["bridged"] += 1
    
    def _generate_comprehensive_analysis(self, all_purchases, token_summary, platform_summary, base_native_summary, web3_analysis_summary=None):
        """Generate enhanced analysis results with Web3 insights"""
        logger.info(f"Generating {self.network} comprehensive analysis...")
        print(f"📊 Generating {self.network.title()} Analysis Results...")
        
        if not all_purchases:
            logger.warning(f"No {self.network} token purchases found")
            print(f"❌ No significant {self.network} token purchases found!")
            return {}
        
        total_eth_spent = sum(self.safe_float_conversion(purchase.get("eth_spent")) for purchase in all_purchases)
        total_usd_spent = sum(self.safe_float_conversion(purchase.get("estimated_usd_value")) for purchase in all_purchases)
        
        ranked_tokens = self.get_ranked_tokens(token_summary)
        
        # Enhanced summary output with Web3 data
        unique_wallets = len(set(p.get("wallet_score") for p in all_purchases))
        avg_eth_per_purchase = total_eth_spent / len(all_purchases) if all_purchases else 0
        
        print("="*60)
        print(f"🎉 {self.network.title()} Buy Analysis Complete!")
        print(f"📊 Total Purchases: {len(all_purchases)}")
        print(f"🪙 Unique Tokens: {len(token_summary)}")
        print(f"💰 Total ETH Spent: {total_eth_spent:.4f} ETH")
        print(f"💵 Total USD Value: ${total_usd_spent:.0f}")
        print(f"📈 Average per Purchase: {avg_eth_per_purchase:.4f} ETH")
        
        # 🚀 NEW: Web3 enhanced summary
        if self.web3_enabled and web3_analysis_summary and web3_analysis_summary["total_transactions_analyzed"] > 0:
            total_analyzed = web3_analysis_summary["total_transactions_analyzed"]
            sophisticated_count = web3_analysis_summary["sophisticated_transactions"]
            sophisticated_pct = (sophisticated_count / total_analyzed) * 100
            avg_gas_efficiency = web3_analysis_summary["gas_efficiency_avg"]
            
            print(f"🧠 Web3 Enhanced Analysis:")
            print(f"   ⚡ Transactions Analyzed: {total_analyzed}")
            print(f"   🎯 Sophisticated Trades: {sophisticated_count} ({sophisticated_pct:.1f}%)")
            print(f"   ⛽ Avg Gas Efficiency: {avg_gas_efficiency:.1f}%")
            
            if web3_analysis_summary["method_distribution"]:
                top_methods = sorted(web3_analysis_summary["method_distribution"].items(), key=lambda x: x[1], reverse=True)[:3]
                methods_str = ", ".join([f"{method}({count})" for method, count in top_methods])
                print(f"   🔧 Top Methods: {methods_str}")
        
        if ranked_tokens:
            top_token = ranked_tokens[0]
            alpha_score = top_token[2]
            print(f"🏆 Top Token: {top_token[0]} (Alpha Score: {alpha_score})")
            
            # Show Web3 insights for top token
            if self.web3_enabled and top_token[1].get("sophistication_scores"):
                avg_sophistication = sum(top_token[1]["sophistication_scores"]) / len(top_token[1]["sophistication_scores"])
                high_soph_count = top_token[1]["high_sophistication_count"]
                methods_used = len(top_token[1]["methods_used"])
                print(f"   🧠 Avg Sophistication: {avg_sophistication:.1f} | High-Soph Trades: {high_soph_count} | Methods: {methods_used}")
        
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
        
        # 🚀 NEW: Add Web3 analysis summary
        if self.web3_enabled and web3_analysis_summary:
            result["web3_analysis"] = web3_analysis_summary
        
        return result

# Backwards compatibility - update the original class name
ComprehensiveBuyTracker = Web3EnhancedBuyTracker

# Convenience class for Ethereum
class EthComprehensiveTracker(Web3EnhancedBuyTracker):
    def __init__(self):
        super().__init__("ethereum")