from base_shared_utils import BaseTracker, KNOWN_CONTRACTS, MIN_ETH_VALUE, EXCLUDED_TOKENS, print_header, print_insights, is_base_native_token
from typing import List, Dict
import math
import time

class BaseComprehensiveTracker(BaseTracker):
    """Enhanced Base tracker that captures ALL trading methods including bots"""
    
    def looks_like_trading_transaction(self, transfer: Dict) -> bool:
        """Heuristic to detect if this looks like a trading transaction"""
        to_address = transfer.get("to", "").lower()
        asset = transfer.get("asset", "")
        value = float(transfer.get("value", 0))
        
        # Patterns that suggest trading activity on Base
        trading_indicators = [
            # Contract address patterns (some bots use predictable patterns)
            to_address.startswith("0x1111"),  # Some aggregators use this pattern
            to_address.startswith("0x3333"),  # Some bots use this pattern
            to_address.startswith("0x7777"),  # Some MEV bots use this pattern
            
            # Transaction value patterns
            value >= 1000,  # Large token amounts suggest real trading
            asset == "USDC" and value >= 50,  # USDC trading
            asset == "ETH" and value >= 0.005,  # Meaningful ETH amounts
            
            # Address entropy (trading contracts often have more random addresses)
            len(set(to_address[2:])) >= 10,  # Address has good entropy
        ]
        
        # If any indicator is true, it might be trading
        return any(trading_indicators)
    
    def is_significant_purchase(self, outgoing_transfer: Dict) -> bool:
        """Check if purchase meets minimum ETH value threshold on Base"""
        asset = outgoing_transfer.get("asset", "")
        value = float(outgoing_transfer.get("value", 0))
        
        if asset == "ETH":
            # Direct ETH value
            return value >= MIN_ETH_VALUE
        else:
            # For ERC-20 tokens on Base, be more permissive due to lower gas costs
            # Estimate USD value and convert back to ETH equivalent
            estimated_usd = self.estimate_usd_value(value, asset)
            estimated_eth = estimated_usd / 2000  # Rough ETH price
            return estimated_eth >= MIN_ETH_VALUE * 0.5  # 50% of threshold for token swaps
    
    def analyze_wallet_purchases(self, wallet_address: str, days_back: int = 7) -> List[Dict]:
        """Analyze token purchases on Base network"""
        print(f"\n=== Analyzing Base purchases for: {wallet_address} ===")
        
        start_block, end_block = self.get_recent_block_range(days_back)
        
        # Get all transfers FROM this wallet
        outgoing_result = self.make_alchemy_request("alchemy_getAssetTransfers", [{
            "fromAddress": wallet_address,
            "fromBlock": start_block,
            "toBlock": end_block,
            "category": ["external", "erc20"],
            "withMetadata": True,
            "excludeZeroValue": True,
            "maxCount": "0x64"
        }])
        
        # Get all transfers TO this wallet
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
        
        print(f"Found {len(outgoing_transfers)} outgoing transfers, {len(incoming_transfers)} incoming transfers")
        
        # Group by transaction hash to match buys with receives
        tx_groups = {}
        filtered_count = 0
        
        # AGGRESSIVE: Accept ANY contract that could be trading-related
        for transfer in outgoing_transfers:
            tx_hash = transfer.get("hash")
            to_address = transfer.get("to", "").lower()
            asset = transfer.get("asset", "")
            value = transfer.get("value", 0)
            
            # Safe float conversion with error handling
            try:
                value_float = float(value) if value is not None else 0.0
            except (ValueError, TypeError):
                value_float = 0.0
            
            # Check if sent to known contracts OR any potential trading contract
            is_known_contract = to_address in [addr.lower() for addr in KNOWN_CONTRACTS.keys()]
            
            # EXPANDED: Also accept contracts that look like they could be trading bots
            # BasedBot, Sigma, and other bots might use contracts we don't know yet
            could_be_trading_contract = (
                len(to_address) == 42 and  # Valid contract address
                to_address != wallet_address.lower() and  # Not sending to self
                (
                    asset == "ETH" or  # ETH transactions more likely to be real trading
                    value_float >= 100 or  # Large token amounts suggest real trading
                    self.looks_like_trading_transaction({**transfer, "value": value_float})  # Heuristic check
                )
            )
            
            if is_known_contract or could_be_trading_contract:
                # Update transfer with safe float value
                safe_transfer = {**transfer, "value": value_float}
                
                if self.is_significant_purchase(safe_transfer):
                    if tx_hash not in tx_groups:
                        tx_groups[tx_hash] = {"outgoing": [], "incoming": []}
                    tx_groups[tx_hash]["outgoing"].append(safe_transfer)
                    
                    if not is_known_contract:
                        print(f"    🔍 Unknown trading contract: {to_address}")
                        print(f"       Asset: {asset}, Value: {value_float}")
                else:
                    filtered_count += 1
        
        if filtered_count > 0:
            print(f"  Filtered out {filtered_count} small purchases (< {MIN_ETH_VALUE} ETH equivalent)")
        
        for transfer in incoming_transfers:
            tx_hash = transfer.get("hash")
            if tx_hash not in tx_groups:
                tx_groups[tx_hash] = {"outgoing": [], "incoming": []}
            tx_groups[tx_hash]["incoming"].append(transfer)
        
        # Find purchases
        purchases = []
        filtered_boring_count = 0
        
        for tx_hash, transfers in tx_groups.items():
            if transfers["outgoing"] and transfers["incoming"]:
                outgoing = transfers["outgoing"][0]
                to_address = outgoing.get("to", "").lower()
                contract_info = self.get_contract_info(to_address)
                
                for incoming in transfers["incoming"]:
                    token_received = incoming.get("asset", "Unknown")
                    amount_received = float(incoming.get("value", 0))
                    
                    token_sent = outgoing.get("asset", "ETH")
                    if token_received != token_sent:
                        # Check if token is interesting
                        if not self.is_interesting_token(token_received):
                            filtered_boring_count += 1
                            continue
                        
                        eth_spent = float(outgoing.get("value", 0)) if outgoing.get("asset") == "ETH" else 0
                        
                        # Calculate estimated value in ETH for non-ETH purchases
                        if eth_spent == 0:
                            sent_usd = self.estimate_usd_value(float(outgoing.get("value", 0)), token_sent)
                            eth_spent = sent_usd / 2000  # Convert to ETH equivalent
                        
                        # Check if it's a Base native token for extra scoring
                        is_base_native = is_base_native_token(token_received)
                        
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
                        print(f"  🟢 {native_flag}BOUGHT: {token_received} ({amount_received:.2f}) via {contract_info['platform']}{eth_display}")
        
        if filtered_boring_count > 0:
            print(f"  Filtered out {filtered_boring_count} boring token purchases")
        
        print(f"Found {len(purchases)} significant & interesting token purchases on Base")
        return purchases
    
    def calculate_token_alpha_score(self, token_data: Dict) -> float:
        """Calculate alpha score for Base tokens with native token bonus"""
        wallet_scores = token_data["wallet_scores"]
        purchases = token_data["purchases"]
        total_eth_spent = token_data["total_eth_spent"]
        
        if not wallet_scores or total_eth_spent == 0 or not purchases:
            return 0.0
        
        max_possible_wallet_score = 300
        
        # Component 1: Weighted ETH Investment Score
        weighted_eth_score = 0.0
        base_native_bonus = 1.0
        
        for purchase in purchases:
            wallet_score = purchase.get("wallet_score", max_possible_wallet_score)
            eth_spent = purchase.get("eth_spent", 0)
            is_base_native = purchase.get("is_base_native", False)
            
            # Base native token bonus
            if is_base_native:
                base_native_bonus = 1.3  # 30% bonus for Base native tokens
            
            if eth_spent > 0:
                wallet_quality_multiplier = (max_possible_wallet_score - wallet_score + 100) / 100
                eth_component = math.log(1 + eth_spent) * 10
                weighted_eth_score += eth_component * wallet_quality_multiplier * base_native_bonus
        
        # Component 2: Weighted Consensus Score
        score_components = self.calculate_score_components(wallet_scores, max_possible_wallet_score)
        weighted_consensus_score = score_components["weighted_consensus"]
        
        # Base network bonus for early adoption
        base_network_bonus = 1.1  # 10% bonus for being early on Base
        
        final_score = (weighted_eth_score * weighted_consensus_score * base_network_bonus) / 10
        return round(final_score, 2)
    
    def get_ranked_tokens(self, token_summary: Dict) -> List[tuple]:
        """Get Base tokens ranked by alpha score"""
        scored_tokens = []
        
        for token, data in token_summary.items():
            alpha_score = self.calculate_token_alpha_score(data)
            scored_tokens.append((token, data, alpha_score))
        
        return sorted(scored_tokens, key=lambda x: x[2], reverse=True)
    
    def analyze_all_trading_methods(self, num_wallets: int = 174, days_back: int = 1):
        """Analyze ALL trading methods on Base"""
        print(f"\n🔵 COMPREHENSIVE BASE TRADING ANALYSIS")
        print(f"=" * 60)
        print(f"📊 Tracking ALL trading methods:")
        print(f"   ✅ Traditional DEXs (Uniswap, Aerodrome, BaseSwap)")
        print(f"   🤖 Telegram Bots (BasedBot, Sigma, Maestro, Banana Gun)")
        print(f"   🔍 Unknown Trading Contracts")
        print(f"   💰 Direct transfers with trading patterns")
        print(f"=" * 60)
        
        # Get wallets
        top_wallets = self.get_top_wallets(num_wallets)
        
        if not top_wallets:
            print("No Base wallets found in database!")
            return {}
        
        all_purchases = []
        token_summary = {}
        platform_summary = {}
        base_native_summary = {"native": 0, "bridged": 0}
        
        for i, wallet in enumerate(top_wallets, 1):
            wallet_address = wallet["address"]
            wallet_score = wallet["score"]
            
            print(f"\n[{i}/{num_wallets}] Base Wallet: {wallet_address} (Score: {wallet_score})")
            
            try:
                purchases = self.analyze_wallet_purchases(wallet_address, days_back)
                
                for purchase in purchases:
                    purchase["wallet_score"] = wallet_score
                
                all_purchases.extend(purchases)
                
                # Aggregate data
                for purchase in purchases:
                    token = purchase["token_bought"]
                    platform = purchase["platform"]
                    amount = purchase["amount_received"]
                    eth_spent = purchase.get("eth_spent", 0)
                    is_base_native = purchase.get("is_base_native", False)
                    
                    # Token summary
                    if token not in token_summary:
                        token_summary[token] = {
                            "count": 0,
                            "wallets": set(),
                            "total_amount": 0,
                            "platforms": set(),
                            "total_eth_spent": 0,
                            "wallet_scores": [],
                            "purchases": [],
                            "is_base_native": is_base_native,
                            "total_usd_value": 0
                        }
                    
                    token_summary[token]["count"] += 1
                    token_summary[token]["wallets"].add(wallet_address)
                    token_summary[token]["total_amount"] += amount
                    token_summary[token]["platforms"].add(platform)
                    token_summary[token]["total_eth_spent"] += eth_spent
                    token_summary[token]["wallet_scores"].append(wallet_score)
                    token_summary[token]["purchases"].append(purchase)
                    token_summary[token]["total_usd_value"] += purchase.get("estimated_usd_value", 0)
                    
                    # Platform summary
                    platform_summary[platform] = platform_summary.get(platform, 0) + 1
                    
                    # Base native vs bridged summary
                    if is_base_native:
                        base_native_summary["native"] += 1
                    else:
                        base_native_summary["bridged"] += 1
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                print(f"Error analyzing Base wallet {wallet_address}: {e}")
                continue
        
        return self.generate_comprehensive_analysis(all_purchases, token_summary, platform_summary, base_native_summary)
    
    def generate_comprehensive_analysis(self, all_purchases, token_summary, platform_summary, base_native_summary):
        """Generate comprehensive Base analysis"""
        print(f"\n" + "=" * 80)
        print(f"BASE NETWORK COMPREHENSIVE ALPHA TOKEN ANALYSIS")
        print(f"=" * 80)
        
        print(f"🔵 Total Base alpha token purchases: {len(all_purchases)}")
        print(f"🪙 Unique alpha tokens bought: {len(token_summary)}")
        
        total_eth_spent = sum(purchase.get("eth_spent", 0) for purchase in all_purchases)
        total_usd_spent = sum(purchase.get("estimated_usd_value", 0) for purchase in all_purchases)
        print(f"💰 Total value: {total_eth_spent:.4f} ETH (~${total_usd_spent:,.0f})")
        
        # Base native vs bridged breakdown
        native_count = base_native_summary["native"]
        bridged_count = base_native_summary["bridged"]
        total_txs = native_count + bridged_count
        
        if total_txs > 0:
            native_pct = (native_count / total_txs) * 100
            bridged_pct = (bridged_count / total_txs) * 100
            print(f"🔵 Base Native: {native_count} purchases ({native_pct:.1f}%)")
            print(f"🌉 Bridged/External: {bridged_count} purchases ({bridged_pct:.1f}%)")
        
        if len(all_purchases) == 0:
            print("\n❌ No Base alpha token purchases found")
            return {}
        
        # Categorize platforms
        dex_platforms = {}
        bot_platforms = {}
        unknown_platforms = {}
        
        for platform, count in platform_summary.items():
            if platform in ["Uniswap", "Aerodrome", "BaseSwap", "SushiSwap", "PancakeSwap", "1inch"]:
                dex_platforms[platform] = count
            elif any(bot_word in platform for bot_word in ["Bot", "Gun", "Maestro", "BasedBot", "Sigma"]):
                bot_platforms[platform] = count
            else:
                unknown_platforms[platform] = count
        
        # Show breakdown by trading method
        print(f"\n📊 BASE TRADING METHODS BREAKDOWN:")
        
        if dex_platforms:
            print(f"\n🔄 TRADITIONAL DEXs:")
            for platform, count in sorted(dex_platforms.items(), key=lambda x: x[1], reverse=True):
                pct = (count / len(all_purchases) * 100) if all_purchases else 0
                print(f"   {platform:>15}: {count:3d} purchases ({pct:5.1f}%)")
        
        if bot_platforms:
            print(f"\n🤖 TELEGRAM/MEV BOTS:")
            for platform, count in sorted(bot_platforms.items(), key=lambda x: x[1], reverse=True):
                pct = (count / len(all_purchases) * 100) if all_purchases else 0
                print(f"   {platform:>15}: {count:3d} purchases ({pct:5.1f}%)")
        
        if unknown_platforms:
            print(f"\n🔍 UNKNOWN/NEW TRADING METHODS:")
            for platform, count in sorted(unknown_platforms.items(), key=lambda x: x[1], reverse=True):
                pct = (count / len(all_purchases) * 100) if all_purchases else 0
                print(f"   {platform:>15}: {count:3d} purchases ({pct:5.1f}%)")
        
        # Get ranked tokens
        ranked_tokens = self.get_ranked_tokens(token_summary)
        
        # Show top tokens
        print(f"\n🏆 TOP 10 BASE ALPHA TOKENS:")
        for i, (token, data, alpha_score) in enumerate(ranked_tokens[:10], 1):
            wallet_count = len(data["wallets"])
            eth_spent = data["total_eth_spent"]
            platforms = ", ".join(list(data["platforms"])[:2])
            is_base_native = data.get("is_base_native", False)
            native_flag = "🔵" if is_base_native else "🌉"
            
            print(f"   {i:2d}. {native_flag} {token}: α={alpha_score:.1f} | {wallet_count}W | {eth_spent:.4f}Ξ | {platforms}")
        
        # Contract addresses
        print(f"\n📋 TOP 10 BASE ALPHA TOKEN CONTRACT ADDRESSES:")
        for i, (token, data, alpha_score) in enumerate(ranked_tokens[:10], 1):
            contract_addresses = set()
            for purchase in data["purchases"]:
                ca = purchase.get("contract_address", "")
                if ca:
                    contract_addresses.add(ca)
            
            main_ca = list(contract_addresses)[0] if contract_addresses else "N/A"
            eth_spent = data["total_eth_spent"]
            wallet_count = len(data["wallets"])
            is_base_native = data.get("is_base_native", False)
            native_flag = "🔵" if is_base_native else "🌉"
            
            print(f"  {i:2d}. {native_flag}{token:>12} (α={alpha_score:.1f}): {main_ca}")
            print(f"      💰 {eth_spent:.4f} ETH | 👥 {wallet_count} wallets")
        
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

def main():
    """Run comprehensive Base trading analysis"""
    tracker = BaseComprehensiveTracker()
    
    print("🔵 BASE NETWORK COMPREHENSIVE TRADING TRACKER")
    print("=" * 50)
    print("Tracking ALL Base trading methods including BasedBot/Sigma")
    
    if not tracker.test_connection():
        print("❌ Connection failed")
        return
    
    try:
        results = tracker.analyze_all_trading_methods(num_wallets=174, days_back=1)
        
        if results and results.get("ranked_tokens"):
            print(f"\n✅ SUCCESS: Found Base alpha trading activity!")
            print(f"💰 Total: {results.get('total_eth_spent', 0):.4f} ETH")
            print(f"🪙 Tokens: {results.get('unique_tokens', 0)} unique alpha tokens")
            
            native_count = results["base_native_summary"]["native"]
            bridged_count = results["base_native_summary"]["bridged"]
            
            print(f"🔵 Base Native purchases: {native_count}")
            print(f"🌉 Bridged/External purchases: {bridged_count}")
            
        else:
            print(f"\n⚠️ Limited Base activity found - try:")
            print(f"   • Increasing days_back to 21-30 days")
            print(f"   • Lowering MIN_ETH_VALUE threshold")
            print(f"   • Running base_contract_discovery.py first")
        
    except Exception as e:
        print(f"❌ Base analysis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()