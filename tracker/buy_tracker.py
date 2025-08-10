from tracker.shared_utils import BaseTracker, KNOWN_CONTRACTS, MIN_ETH_VALUE, EXCLUDED_TOKENS, print_header, print_insights
from typing import List, Dict
import math
import time

class EthComprehensiveTracker(BaseTracker):
    """Enhanced ETH mainnet tracker that captures ALL trading methods including bots"""
    
    def analyze_wallet_purchases(self, wallet_address: str, days_back: int = 1) -> List[Dict]:
        """Analyze token purchases for a single wallet on ETH mainnet"""
        print(f"\n=== Analyzing ETH purchases for: {wallet_address} ===")
        
        start_block, end_block = self.get_recent_block_range(days_back)
        
        # Get all transfers FROM this wallet (ETH and ERC20)
        outgoing_result = self.make_alchemy_request("alchemy_getAssetTransfers", [{
            "fromAddress": wallet_address,
            "fromBlock": start_block,
            "toBlock": end_block,
            "category": ["external", "erc20"],
            "withMetadata": True,
            "excludeZeroValue": True,
            "maxCount": "0x64"
        }])
        
        # Get all transfers TO this wallet (ERC20 tokens received)
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
        
        for transfer in outgoing_transfers:
            tx_hash = transfer.get("hash")
            to_address = transfer.get("to", "").lower()
            
            # Check if sent to known contracts or potential trading contracts
            contract_info = self.get_contract_info(to_address)
            
            # Accept known contracts and potential trading contracts
            if contract_info["type"] != "UNKNOWN" or self.looks_like_trading_transaction(transfer):
                # Check if meets minimum value threshold
                if self.is_significant_purchase(transfer):
                    if tx_hash not in tx_groups:
                        tx_groups[tx_hash] = {"outgoing": [], "incoming": []}
                    tx_groups[tx_hash]["outgoing"].append(transfer)
                else:
                    filtered_count += 1
        
        if filtered_count > 0:
            print(f"  Filtered out {filtered_count} small purchases (< {MIN_ETH_VALUE} ETH)")
        
        # Add incoming transfers to their transactions
        for transfer in incoming_transfers:
            tx_hash = transfer.get("hash")
            if tx_hash in tx_groups:
                tx_groups[tx_hash]["incoming"].append(transfer)
        
        # Find purchases (where we sent ETH/tokens and received different tokens)
        purchases = []
        filtered_boring = 0
        
        for tx_hash, transfers in tx_groups.items():
            if transfers["outgoing"] and transfers["incoming"]:
                outgoing = transfers["outgoing"][0]
                to_address = outgoing.get("to", "").lower()
                contract_info = self.get_contract_info(to_address)
                
                for incoming in transfers["incoming"]:
                    token_received = incoming.get("asset", "Unknown")
                    amount_received = float(incoming.get("value", 0))
                    
                    # Check if token is interesting
                    if not self.is_interesting_token(token_received):
                        filtered_boring += 1
                        continue
                    
                    token_sent = outgoing.get("asset", "ETH")
                    
                    # Only record if different tokens (not same token transfers)
                    if token_received != token_sent:
                        eth_spent = float(outgoing.get("value", 0)) if outgoing.get("asset") == "ETH" else 0
                        
                        # Calculate estimated ETH value for non-ETH purchases
                        if eth_spent == 0:
                            sent_usd = self.estimate_usd_value(float(outgoing.get("value", 0)), token_sent)
                            eth_spent = sent_usd / 2000  # Convert to ETH equivalent
                        
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
                            "to_address": to_address,
                            "estimated_usd_value": self.estimate_usd_value(amount_received, token_received)
                        }
                        
                        purchases.append(purchase)
                        
                        platform_emoji = {
                            "Uniswap": "🦄",
                            "1inch": "🔄",
                            "Banana Gun": "🍌",
                            "UniBot": "🤖",
                            "Maestro Bot": "🎭"
                        }.get(contract_info["platform"], "📈")
                        
                        eth_display = f" (spent {eth_spent:.4f} ETH)" if eth_spent > 0 else ""
                        print(f"  {platform_emoji} BOUGHT: {token_received} ({amount_received:.2f}) via {contract_info['platform']}{eth_display}")
        
        if filtered_boring > 0:
            print(f"  Filtered out {filtered_boring} boring token purchases")
        
        print(f"Found {len(purchases)} significant & interesting token purchases")
        return purchases
    
    def looks_like_trading_transaction(self, transfer: Dict) -> bool:
        """Heuristic to detect if this looks like a trading transaction"""
        to_address = transfer.get("to", "").lower()
        asset = transfer.get("asset", "")
        value = float(transfer.get("value", 0))
        
        # Patterns that suggest trading activity
        trading_indicators = [
            # High entropy addresses (likely contracts)
            len(set(to_address[2:])) >= 12,
            
            # Common bot/aggregator patterns
            to_address.startswith("0x1111"),
            to_address.startswith("0x3333"),
            to_address.startswith("0x7777"),
            
            # Transaction value patterns
            value >= 0.01 and asset == "ETH",  # Non-dust ETH amounts
            asset in ["USDC", "USDT", "DAI"] and value >= 50,  # Stablecoin trades
        ]
        
        return any(trading_indicators)
    
    def is_significant_purchase(self, transfer: Dict) -> bool:
        """Check if purchase meets minimum value threshold"""
        asset = transfer.get("asset", "")
        value = float(transfer.get("value", 0))
        
        if asset == "ETH":
            return value >= MIN_ETH_VALUE
        else:
            # For ERC20, estimate USD value and check
            estimated_usd = self.estimate_usd_value(value, asset)
            estimated_eth = estimated_usd / 2000
            return estimated_eth >= MIN_ETH_VALUE
    
    def calculate_token_alpha_score(self, token_data: Dict) -> float:
        """Calculate alpha score for tokens"""
        wallet_scores = token_data["wallet_scores"]
        purchases = token_data["purchases"]
        total_eth_spent = token_data["total_eth_spent"]
        
        if not wallet_scores or total_eth_spent == 0 or not purchases:
            return 0.0
        
        max_possible_wallet_score = 300
        
        # Component 1: Weighted ETH Investment Score
        weighted_eth_score = 0.0
        
        for purchase in purchases:
            wallet_score = purchase.get("wallet_score", max_possible_wallet_score)
            eth_spent = purchase.get("eth_spent", 0)
            
            if eth_spent > 0:
                wallet_quality_multiplier = (max_possible_wallet_score - wallet_score + 100) / 100
                eth_component = math.log(1 + eth_spent) * 10
                weighted_eth_score += eth_component * wallet_quality_multiplier
        
        # Component 2: Weighted Consensus Score
        score_components = self.calculate_score_components(wallet_scores, max_possible_wallet_score)
        weighted_consensus_score = score_components["weighted_consensus"]
        
        # Bonus for bot activity (shows sophisticated traders)
        bot_platforms = ["Banana Gun", "UniBot", "Maestro Bot", "BonkBot", "Trojan Bot"]
        bot_bonus = 1.0
        for purchase in purchases:
            if any(bot in purchase.get("platform", "") for bot in bot_platforms):
                bot_bonus = 1.2  # 20% bonus for bot usage
                break
        
        final_score = (weighted_eth_score * weighted_consensus_score * bot_bonus) / 10
        return round(final_score, 2)
    
    def get_ranked_tokens(self, token_summary: Dict) -> List[tuple]:
        """Get tokens ranked by alpha score"""
        scored_tokens = []
        
        for token, data in token_summary.items():
            alpha_score = self.calculate_token_alpha_score(data)
            scored_tokens.append((token, data, alpha_score))
        
        return sorted(scored_tokens, key=lambda x: x[2], reverse=True)
    
    def analyze_top_wallets(self, num_wallets: int = 174, days_back: int = 1) -> Dict:
        """Analyze top wallets for buying activity"""
        print_header("ETH MAINNET ALPHA TOKEN BUY ANALYSIS", MIN_ETH_VALUE, len(EXCLUDED_TOKENS))
        
        # Get top wallets from database
        top_wallets = self.get_top_wallets(num_wallets)
        
        if not top_wallets:
            print("No wallets found in database!")
            return {}
        
        all_purchases = []
        token_summary = {}
        platform_summary = {}
        
        for i, wallet in enumerate(top_wallets, 1):
            wallet_address = wallet["address"]
            wallet_score = wallet["score"]
            
            print(f"\n[{i}/{num_wallets}] Wallet: {wallet_address} (Score: {wallet_score})")
            
            try:
                purchases = self.analyze_wallet_purchases(wallet_address, days_back)
                
                # Add wallet score to each purchase
                for purchase in purchases:
                    purchase["wallet_score"] = wallet_score
                
                all_purchases.extend(purchases)
                
                # Aggregate data
                for purchase in purchases:
                    token = purchase["token_bought"]
                    platform = purchase["platform"]
                    amount = purchase["amount_received"]
                    eth_spent = purchase.get("eth_spent", 0)
                    
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
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                print(f"Error analyzing wallet {wallet_address}: {e}")
                continue
        
        # Generate analysis summary
        print(f"\n" + "=" * 80)
        print(f"ETH MAINNET ALPHA TOKEN ANALYSIS COMPLETE")
        print(f"=" * 80)
        
        print(f"📊 Total alpha token purchases: {len(all_purchases)}")
        print(f"🪙 Unique alpha tokens bought: {len(token_summary)}")
        
        total_eth_spent = sum(purchase.get("eth_spent", 0) for purchase in all_purchases)
        total_usd_spent = sum(purchase.get("estimated_usd_value", 0) for purchase in all_purchases)
        print(f"💰 Total value: {total_eth_spent:.4f} ETH (~${total_usd_spent:,.0f})")
        
        if len(all_purchases) == 0:
            print("\n❌ No alpha token purchases found")
            return {}
        
        # Platform breakdown
        print(f"\n📈 PLATFORM BREAKDOWN:")
        for platform, count in sorted(platform_summary.items(), key=lambda x: x[1], reverse=True)[:10]:
            percentage = (count / len(all_purchases)) * 100
            print(f"   {platform:>20}: {count:3d} purchases ({percentage:5.1f}%)")
        
        # Get ranked tokens
        ranked_tokens = self.get_ranked_tokens(token_summary)
        
        # Top tokens
        print(f"\n🏆 TOP 10 ALPHA TOKENS:")
        for i, (token, data, alpha_score) in enumerate(ranked_tokens[:10], 1):
            wallet_count = len(data["wallets"])
            eth_spent = data["total_eth_spent"]
            platforms = ", ".join(list(data["platforms"])[:3])
            
            print(f"   {i:2d}. {token}: α={alpha_score:.1f} | {wallet_count}W | {eth_spent:.4f}Ξ | {platforms}")
        
        # Key insights
        print_insights(ranked_tokens, "tokens", 5)
        
        return {
            "total_purchases": len(all_purchases),
            "unique_tokens": len(token_summary),
            "total_eth_spent": total_eth_spent,
            "total_usd_spent": total_usd_spent,
            "ranked_tokens": ranked_tokens,
            "platform_summary": platform_summary,
            "all_purchases": all_purchases
        }
    
    def analyze_all_trading_methods(self, num_wallets: int = 174, days_back: int = 1) -> Dict:
        """Analyze ALL trading methods on ETH mainnet - wrapper for compatibility"""
        print(f"\n⚡ COMPREHENSIVE ETH MAINNET TRADING ANALYSIS")
        print(f"=" * 60)
        print(f"📊 Tracking ALL trading methods:")
        print(f"   ✅ Traditional DEXs (Uniswap, 1inch, CoW Protocol)")
        print(f"   🤖 Telegram Bots (UniBot, Banana Gun, Maestro, BonkBot)")
        print(f"   🔍 Unknown Trading Contracts & MEV Bots")
        print(f"   💰 Direct transfers with trading patterns")
        print(f"=" * 60)
        
        results = self.analyze_top_wallets(num_wallets, days_back)
        
        if results.get("ranked_tokens"):
            self.generate_comprehensive_report(results)
        
        return results
    
    def generate_comprehensive_report(self, results: Dict):
        """Generate detailed report showing ALL trading methods"""
        ranked_tokens = results.get("ranked_tokens", [])
        platform_summary = results.get("platform_summary", {})
        all_purchases = results.get("all_purchases", [])
        
        if not all_purchases:
            return
        
        print(f"\n🎯 COMPREHENSIVE ETH TRADING INSIGHTS:")
        print(f"=" * 60)
        
        # Categorize platforms
        dex_platforms = {}
        bot_platforms = {}
        unknown_platforms = {}
        
        for platform, count in platform_summary.items():
            if platform in ["Uniswap", "1inch", "CoW Protocol", "0x Protocol", "Kyber Network", "Metamask"]:
                dex_platforms[platform] = count
            elif any(bot_word in platform for bot_word in ["Bot", "Gun", "Maestro", "UniBot", "BonkBot"]):
                bot_platforms[platform] = count
            else:
                unknown_platforms[platform] = count
        
        # Show breakdown
        if dex_platforms:
            print(f"\n🔄 TRADITIONAL DEXs:")
            for platform, count in sorted(dex_platforms.items(), key=lambda x: x[1], reverse=True):
                pct = (count / len(all_purchases) * 100)
                print(f"   {platform:>20}: {count:3d} ({pct:5.1f}%)")
        
        if bot_platforms:
            print(f"\n🤖 TELEGRAM/MEV BOTS:")
            for platform, count in sorted(bot_platforms.items(), key=lambda x: x[1], reverse=True):
                pct = (count / len(all_purchases) * 100)
                print(f"   {platform:>20}: {count:3d} ({pct:5.1f}%)")
        
        if unknown_platforms:
            print(f"\n🔍 UNKNOWN/NEW METHODS:")
            for platform, count in list(sorted(unknown_platforms.items(), key=lambda x: x[1], reverse=True))[:5]:
                pct = (count / len(all_purchases) * 100)
                print(f"   {platform:>20}: {count:3d} ({pct:5.1f}%)")

def main():
    """Main function for testing"""
    tracker = EthComprehensiveTracker()
    
    print("⚡ ETH MAINNET BUY TRACKER")
    print("=" * 50)
    
    if not tracker.test_connection():
        print("❌ Connection failed")
        return
    
    try:
        results = tracker.analyze_all_trading_methods(num_wallets=174, days_back=1)
        
        if results and results.get("ranked_tokens"):
            print(f"\n✅ SUCCESS!")
            print(f"Found {results['unique_tokens']} unique alpha tokens")
            print(f"Total spent: {results['total_eth_spent']:.4f} ETH")
        else:
            print("\n⚠️ No alpha activity found")
            
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()