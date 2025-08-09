from base_shared_utils import BaseTracker, KNOWN_CONTRACTS, MIN_ETH_VALUE, EXCLUDED_TOKENS
from typing import List, Dict
import math
import time

# Base sell-specific configuration
MIN_TOKENS_FOR_UNKNOWN = 50  # Lower threshold for Base due to smaller ecosystem

class BaseComprehensiveSellTracker(BaseTracker):
    """Comprehensive Base sell pressure tracker for all trading methods"""
    
    def analyze_wallet_sells(self, wallet_address: str, days_back: int = 7) -> List[Dict]:
        """Analyze token sells on Base including all methods"""
        print(f"\n=== Analyzing Base sells for: {wallet_address} ===")
        
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
        print(f"Found {len(outgoing_transfers)} outgoing token transfers")
        
        sells = []
        sell_methods = {"DEX": 0, "CEX": 0, "TELEGRAM_BOT": 0, "MEV_BOT": 0, "P2P_OTC": 0, "UNKNOWN": 0}
        filtered_boring = 0
        filtered_small = 0
        
        for transfer in outgoing_transfers:
            token_sold = transfer.get("asset", "Unknown")
            value = transfer.get("value", 0)
            
            # Safe float conversion
            try:
                amount_sold = float(value) if value is not None else 0.0
            except (ValueError, TypeError):
                amount_sold = 0.0
                
            to_address = transfer.get("to", "").lower()
            tx_hash = transfer.get("hash", "")
            block_number = int(transfer.get("blockNum", "0x0"), 16)
            
            # Skip if token is not interesting
            if not self.is_interesting_token(token_sold):
                filtered_boring += 1
                continue
            
            # Skip very small amounts (lower threshold for Base)
            if amount_sold < 0.1:
                filtered_small += 1
                continue
            
            # Determine sell method using Base-specific detection
            sell_method = "UNKNOWN"
            recipient_name = "Unknown Address"
            confidence = "LOW"
            
            # Check known Base contracts first
            contract_info = self.get_contract_info(to_address)
            if contract_info["type"] != "UNKNOWN":
                sell_method = contract_info["type"]
                recipient_name = contract_info["name"]
                confidence = "HIGH"
            else:
                # Base-specific heuristic detection
                if self.looks_like_base_trading_contract(to_address, amount_sold, token_sold):
                    if amount_sold >= MIN_TOKENS_FOR_UNKNOWN:
                        sell_method = "TELEGRAM_BOT"  # Likely BasedBot/Sigma
                        recipient_name = f"Possible BasedBot/Sigma (Large)"
                        confidence = "MEDIUM"
                    else:
                        sell_method = "UNKNOWN"
                        recipient_name = "Unknown Base Contract"
                        confidence = "LOW"
                else:
                    sell_method = "UNKNOWN"
                    recipient_name = "Unknown Address"
                    confidence = "LOW"
            
            # Estimate value (Base-specific pricing)
            estimated_usd = self.estimate_usd_value(amount_sold, token_sold)
            estimated_eth = estimated_usd / 2000
            
            # Check if it's a Base native token (affects scoring)
            is_base_native = BaseTracker.is_base_native_token(token_sold)
            
            # More permissive inclusion criteria for Base
            include_transfer = False
            
            if confidence == "HIGH":  # Known platforms
                include_transfer = True
            elif confidence == "MEDIUM" and estimated_eth >= MIN_ETH_VALUE * 0.2:  # Very low threshold for potential bots
                include_transfer = True
            elif confidence == "LOW" and estimated_eth >= MIN_ETH_VALUE:  # Standard threshold for unknown
                include_transfer = True
            elif is_base_native and estimated_eth >= MIN_ETH_VALUE * 0.1:  # Very low threshold for Base native
                include_transfer = True
            
            if include_transfer:
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
                sell_methods[sell_method] += 1
                
                method_emoji = {
                    "DEX": "🔄", "CEX": "🏦", "TELEGRAM_BOT": "🤖", 
                    "MEV_BOT": "⚡", "P2P_OTC": "🤝", "UNKNOWN": "❓"
                }
                confidence_emoji = {"HIGH": "✅", "MEDIUM": "⚠️", "LOW": "❓"}
                native_flag = "🔵" if is_base_native else ""
                
                print(f"  {method_emoji.get(sell_method, '❓')}{confidence_emoji[confidence]} {native_flag}SOLD: {token_sold} ({amount_sold:.2f}) → {recipient_name} | ~${estimated_usd:.0f}")
        
        if filtered_boring > 0:
            print(f"  Filtered out {filtered_boring} boring token sales")
        if filtered_small > 0:
            print(f"  Filtered out {filtered_small} dust transfers")
        
        print(f"Found {len(sells)} significant token sales on Base")
        print(f"Methods: DEX={sell_methods['DEX']}, Bots={sell_methods['TELEGRAM_BOT'] + sell_methods['MEV_BOT']}, Unknown={sell_methods['UNKNOWN']}")
        
        return sells
    
    def looks_like_base_trading_contract(self, address: str, amount: float, token: str) -> bool:
        """Base-specific heuristic to detect trading contracts"""
        patterns = [
            # Base-specific patterns
            len(set(address[2:])) >= 12,  # High entropy
            address.startswith("0x1111"),  # Aggregator pattern
            address.startswith("0x3333"),  # Base bot pattern
            address.startswith("0x7777"),  # Base bot pattern
            
            # Transaction patterns (adjusted for Base)
            amount >= 100,  # Lower amounts due to Base ecosystem
            token == "USDC" and amount >= 50,  # Base USDC trading
            
            # Base-specific contract patterns
            any(pattern in address for pattern in ["base", "aero", "dead", "beef"]),
        ]
        return any(patterns)
    
    def calculate_token_sell_score(self, token_data: Dict) -> float:
        """Calculate Base sell pressure score with native token considerations"""
        wallet_scores = token_data["wallet_scores"]
        sells = token_data["sells"]
        total_estimated_eth = token_data["total_estimated_eth"]
        
        if not wallet_scores or total_estimated_eth == 0 or not sells:
            return 0.0
        
        max_possible_wallet_score = 300
        
        # Base-specific weighted scoring
        weighted_eth_score = 0.0
        for sell in sells:
            wallet_score = sell.get("wallet_score", max_possible_wallet_score)
            estimated_eth = sell.get("estimated_eth_value", 0)
            confidence = sell.get("confidence", "LOW")
            method = sell.get("sell_method", "UNKNOWN")
            is_base_native = sell.get("is_base_native", False)
            
            # Base native penalty (selling native tokens is more concerning)
            native_multiplier = 1.5 if is_base_native else 1.0
            
            # Confidence multipliers
            confidence_multipliers = {
                "HIGH": 1.0,     # Known platforms = full weight
                "MEDIUM": 0.9,   # Likely BasedBot/Sigma = high weight
                "LOW": 0.6       # Unknown = reduced weight
            }
            
            # Base-specific method multipliers
            method_multipliers = {
                "CEX": 2.0,          # CEX = strongest sell signal on Base
                "TELEGRAM_BOT": 1.8, # BasedBot/Sigma selling = very strong
                "MEV_BOT": 1.6,      # MEV = quick exit
                "DEX": 1.4,          # DEX = normal sell
                "P2P_OTC": 1.3,      # P2P = possible OTC
                "UNKNOWN": 1.0       # Unknown = baseline
            }
            
            confidence_mult = confidence_multipliers.get(confidence, 0.5)
            method_mult = method_multipliers.get(method, 1.0)
            
            if estimated_eth > 0:
                wallet_quality_multiplier = (max_possible_wallet_score - wallet_score + 100) / 100
                eth_component = math.log(1 + estimated_eth * 1000) * 2  # Scale for Base amounts
                weighted_eth_score += eth_component * wallet_quality_multiplier * confidence_mult * method_mult * native_multiplier
        
        # Weighted consensus score
        score_components = self.calculate_score_components(wallet_scores, max_possible_wallet_score)
        weighted_consensus_score = score_components["weighted_consensus"]
        
        # Base early adoption bonus (selling early on Base is more significant)
        base_early_bonus = 1.2
        
        final_score = (weighted_eth_score * weighted_consensus_score * base_early_bonus) / 10
        return round(final_score, 2)
    
    def get_detailed_sell_metrics(self, token_data: Dict) -> Dict:
        """Get detailed Base sell metrics"""
        sells = token_data["sells"]
        
        # Enhanced breakdowns for Base
        method_breakdown = {}
        confidence_breakdown = {}
        platform_breakdown = {}
        native_breakdown = {"native": {"count": 0, "total_eth": 0}, "bridged": {"count": 0, "total_eth": 0}}
        
        for sell in sells:
            method = sell.get("sell_method", "UNKNOWN")
            confidence = sell.get("confidence", "LOW")
            platform = sell.get("platform", "Unknown")
            is_base_native = sell.get("is_base_native", False)
            
            # Standard breakdowns
            for breakdown, key in [(method_breakdown, method), (confidence_breakdown, confidence), (platform_breakdown, platform)]:
                if key not in breakdown:
                    breakdown[key] = {"count": 0, "total_eth": 0}
                
                eth_val = sell.get("estimated_eth_value", 0)
                breakdown[key]["count"] += 1
                breakdown[key]["total_eth"] += eth_val
            
            # Base native vs bridged breakdown
            eth_val = sell.get("estimated_eth_value", 0)
            if is_base_native:
                native_breakdown["native"]["count"] += 1
                native_breakdown["native"]["total_eth"] += eth_val
            else:
                native_breakdown["bridged"]["count"] += 1
                native_breakdown["bridged"]["total_eth"] += eth_val
        
        # Top sells by value
        top_sells = sorted(sells, key=lambda x: x.get("estimated_eth_value", 0), reverse=True)[:5]
        
        return {
            "method_breakdown": method_breakdown,
            "confidence_breakdown": confidence_breakdown,
            "platform_breakdown": platform_breakdown,
            "native_breakdown": native_breakdown,
            "top_sells": top_sells
        }
    
    def get_ranked_tokens(self, token_summary: Dict) -> List[tuple]:
        """Get Base tokens ranked by sell pressure score"""
        scored_tokens = []
        
        for token, data in token_summary.items():
            sell_score = self.calculate_token_sell_score(data)
            scored_tokens.append((token, data, sell_score))
        
        return sorted(scored_tokens, key=lambda x: x[2], reverse=True)
    
    def analyze_all_sell_methods(self, num_wallets: int = 1, days_back: int = 1):
        """Analyze ALL sell methods on Base network"""
        print(f"\n🔵 COMPREHENSIVE BASE SELL PRESSURE ANALYSIS")
        print(f"=" * 60)
        print(f"📊 Tracking ALL Base sell methods:")
        print(f"   ✅ Traditional DEXs (Uniswap, Aerodrome, BaseSwap)")
        print(f"   🤖 Telegram Bots (BasedBot, Sigma, Maestro)")
        print(f"   🏦 CEX deposits")
        print(f"   🤝 P2P/OTC transfers")
        print(f"   🔍 Unknown Base trading contracts")
        print(f"   🔵 Base Native token tracking")
        print(f"=" * 60)
        
        top_wallets = self.get_top_wallets(num_wallets)
        
        if not top_wallets:
            print("No Base wallets found in database!")
            return {}
        
        all_sells = []
        token_summary = {}
        method_summary = {"DEX": 0, "CEX": 0, "TELEGRAM_BOT": 0, "MEV_BOT": 0, "P2P_OTC": 0, "UNKNOWN": 0}
        base_native_summary = {"native": 0, "bridged": 0}
        
        for i, wallet in enumerate(top_wallets, 1):
            wallet_address = wallet["address"]
            wallet_score = wallet["score"]
            
            print(f"\n[{i}/{num_wallets}] Base Wallet: {wallet_address} (Score: {wallet_score})")
            
            try:
                sells = self.analyze_wallet_sells(wallet_address, days_back)
                
                # Add wallet score to each sell
                for sell in sells:
                    sell["wallet_score"] = wallet_score
                
                all_sells.extend(sells)
                
                # Aggregate data
                for sell in sells:
                    token = sell["token_sold"]
                    method = sell["sell_method"]
                    estimated_eth = sell.get("estimated_eth_value", 0)
                    is_base_native = sell.get("is_base_native", False)
                    
                    # Token summary
                    if token not in token_summary:
                        token_summary[token] = {
                            "count": 0,
                            "wallets": set(),
                            "total_estimated_eth": 0,
                            "wallet_scores": [],
                            "sells": [],
                            "methods": set(),
                            "platforms": set(),
                            "confidence_levels": set(),
                            "is_base_native": is_base_native
                        }
                    
                    token_summary[token]["count"] += 1
                    token_summary[token]["wallets"].add(wallet_address)
                    token_summary[token]["total_estimated_eth"] += estimated_eth
                    token_summary[token]["wallet_scores"].append(wallet_score)
                    token_summary[token]["sells"].append(sell)
                    token_summary[token]["methods"].add(method)
                    token_summary[token]["platforms"].add(sell.get("platform", "Unknown"))
                    token_summary[token]["confidence_levels"].add(sell.get("confidence", "LOW"))
                    
                    # Method summary
                    method_summary[method] += 1
                    
                    # Base native summary
                    if is_base_native:
                        base_native_summary["native"] += 1
                    else:
                        base_native_summary["bridged"] += 1
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                print(f"Error analyzing Base wallet {wallet_address}: {e}")
                continue
        
        return self.generate_comprehensive_base_sell_analysis(all_sells, token_summary, method_summary, base_native_summary)
    
    def generate_comprehensive_base_sell_analysis(self, all_sells, token_summary, method_summary, base_native_summary):
        """Generate comprehensive Base sell analysis"""
        print(f"\n" + "=" * 80)
        print(f"COMPREHENSIVE BASE SELL PRESSURE ANALYSIS (All Methods)")
        print(f"=" * 80)
        
        print(f"🔴 Total Base alpha token sells: {len(all_sells)}")
        print(f"🪙 Unique alpha tokens sold: {len(token_summary)}")
        
        total_estimated_eth = sum(sell.get("estimated_eth_value", 0) for sell in all_sells)
        total_estimated_usd = sum(sell.get("estimated_usd_value", 0) for sell in all_sells)
        print(f"💰 Total estimated value: {total_estimated_eth:.4f} ETH (~${total_estimated_usd:,.0f})")
        
        # Base native vs bridged breakdown
        native_count = base_native_summary["native"]
        bridged_count = base_native_summary["bridged"]
        total_sells = native_count + bridged_count
        
        if total_sells > 0:
            native_pct = (native_count / total_sells) * 100
            bridged_pct = (bridged_count / total_sells) * 100
            print(f"🔵 Base Native sells: {native_count} ({native_pct:.1f}%)")
            print(f"🌉 Bridged/External sells: {bridged_count} ({bridged_pct:.1f}%)")
        
        if len(all_sells) == 0:
            print("\n✅ No Base sell pressure detected!")
            return {}
        
        # Base-specific method breakdown
        print(f"\n📊 BASE SELL METHOD BREAKDOWN:")
        
        # Categorize methods for Base
        bot_methods = method_summary.get("TELEGRAM_BOT", 0) + method_summary.get("MEV_BOT", 0)
        dex_methods = method_summary.get("DEX", 0)
        cex_methods = method_summary.get("CEX", 0)
        other_methods = method_summary.get("P2P_OTC", 0) + method_summary.get("UNKNOWN", 0)
        
        total_sells_count = len(all_sells)
        
        if dex_methods > 0:
            print(f"🔄 Base DEXs: {dex_methods} sells ({dex_methods/total_sells_count*100:.1f}%)")
        if bot_methods > 0:
            print(f"🤖 BasedBot/Sigma/Others: {bot_methods} sells ({bot_methods/total_sells_count*100:.1f}%)")
        if cex_methods > 0:
            print(f"🏦 CEX Deposits: {cex_methods} sells ({cex_methods/total_sells_count*100:.1f}%)")
        if other_methods > 0:
            print(f"🔍 P2P/Unknown: {other_methods} sells ({other_methods/total_sells_count*100:.1f}%)")
        
        # Get ranked tokens by Base sell pressure
        ranked_tokens = self.get_ranked_tokens(token_summary)
        
        # Base sell pressure rankings
        print(f"\n🚨 BASE SELL PRESSURE RANKINGS:")
        
        for i, (token, data, sell_score) in enumerate(ranked_tokens[:10], 1):
            wallet_count = len(data["wallets"])
            estimated_eth = data["total_estimated_eth"]
            methods = ", ".join(list(data["methods"])[:2])
            is_base_native = data.get("is_base_native", False)
            native_flag = "🔵" if is_base_native else "🌉"
            
            warning = ["🚨", "⚠️", "⚠️"][i-1] if i <= 3 else f"{i:2d}."
            print(f"  {warning} {native_flag}{token:>10}: σ={sell_score:>6.1f} | {wallet_count}W | {estimated_eth:.4f}Ξ | {methods}")
        
        # Detailed breakdown for top 3 Base tokens
        print(f"\n🔍 TOP 3 BASE TOKENS UNDER SELL PRESSURE:")
        for i, (token, data, sell_score) in enumerate(ranked_tokens[:3], 1):
            is_base_native = data.get("is_base_native", False)
            native_status = "Base Native 🔵" if is_base_native else "Bridged/External 🌉"
            
            print(f"\n  {i}. {token} (Base Sell Score: {sell_score}) - {native_status}")
            
            metrics = self.get_detailed_sell_metrics(data)
            wallet_count = len(data["wallets"])
            estimated_eth = data["total_estimated_eth"]
            
            # Contract address
            contract_addresses = set()
            for sell in data["sells"]:
                ca = sell.get("contract_address", "")
                if ca:
                    contract_addresses.add(ca)
            main_ca = list(contract_addresses)[0] if contract_addresses else "N/A"
            
            print(f"     📍 Contract Address: {main_ca}")
            print(f"     💰 Total Value: {estimated_eth:.4f} ETH")
            print(f"     👥 Sell Consensus: {wallet_count} wallets")
            
            # Enhanced Base method breakdown
            print(f"     📊 Base Sell Method Analysis:")
            for method, method_data in sorted(metrics["method_breakdown"].items(), 
                                            key=lambda x: x[1]["total_eth"], reverse=True):
                count = method_data["count"]
                eth_val = method_data["total_eth"]
                method_emoji = {
                    "DEX": "🔄", "CEX": "🏦", "TELEGRAM_BOT": "🤖", 
                    "MEV_BOT": "⚡", "P2P_OTC": "🤝", "UNKNOWN": "❓"
                }
                emoji = method_emoji.get(method, "❓")
                print(f"         {emoji} {method}: {count} sells ({eth_val:.4f} ETH)")
            
            # Base native vs bridged breakdown
            print(f"     🔵 Base Native vs Bridged:")
            native_data = metrics["native_breakdown"]["native"]
            bridged_data = metrics["native_breakdown"]["bridged"]
            print(f"         🔵 Native: {native_data['count']} sells ({native_data['total_eth']:.4f} ETH)")
            print(f"         🌉 Bridged: {bridged_data['count']} sells ({bridged_data['total_eth']:.4f} ETH)")
        
        return {
            "total_sells": len(all_sells),
            "unique_tokens": len(token_summary),
            "total_estimated_eth": total_estimated_eth,
            "ranked_tokens": ranked_tokens,
            "method_summary": method_summary,
            "base_native_summary": base_native_summary,
            "all_sells": all_sells
        }

def main():
    """Main function for comprehensive Base sell analysis"""
    tracker = BaseComprehensiveSellTracker()
    
    print("🔵 BASE NETWORK COMPREHENSIVE SELL PRESSURE TRACKER")
    print("=" * 50)
    print("Tracking ALL Base sell methods including BasedBot/Sigma")
    
    if not tracker.test_connection():
        print("❌ Connection failed")
        return
    
    try:
        results = tracker.analyze_all_sell_methods(num_wallets=1, days_back=1)
        
        if results and results.get("ranked_tokens"):
            print(f"\n🚨 BASE SELL PRESSURE DETECTED!")
            print(f"💰 Total value being sold: {results.get('total_estimated_eth', 0):.4f} ETH")
            print(f"🪙 {results.get('unique_tokens', 0)} unique Base tokens under pressure")
            
            native_count = results["base_native_summary"]["native"]
            bridged_count = results["base_native_summary"]["bridged"]
            
            print(f"🔵 Base Native token sells: {native_count}")
            print(f"🌉 Bridged/External sells: {bridged_count}")
            
            # Show top tokens under pressure
            print(f"\n🏆 TOP 10 BASE TOKENS UNDER SELL PRESSURE:")
            for i, (token, data, score) in enumerate(results["ranked_tokens"][:10], 1):
                wallet_count = len(data["wallets"])
                estimated_eth = data["total_estimated_eth"]
                methods = ", ".join(list(data["methods"])[:2])
                is_base_native = data.get("is_base_native", False)
                native_flag = "🔵" if is_base_native else "🌉"
                
                if i == 1:
                    warning = "🚨"
                elif i <= 3:
                    warning = "⚠️"
                elif i <= 5:
                    warning = "📉"
                else:
                    warning = f"{i:2d}."
                
                print(f"   {warning} {native_flag}{token}: σ={score:.1f} | {wallet_count}W | {estimated_eth:.4f}Ξ | via {methods}")
    
            if native_count > bridged_count:
                print(f"\n⚠️ WARNING: More Base native tokens being sold than bridged tokens!")
                print(f"💡 This could indicate broader Base ecosystem concerns")
            
        else:
            print(f"\n✅ No significant Base sell pressure detected!")
            print(f"💡 Strong holding conviction among Base smart wallets")
            
    except Exception as e:
        print(f"❌ Base sell analysis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()