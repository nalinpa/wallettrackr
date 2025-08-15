"""
Enhanced sell_tracker.py with Web3 integration
Extends your existing sell tracker with Web3 capabilities for better sell pressure analysis
"""

from .tracker_utils import EnhancedBaseTracker, NetworkSpecificMixins
from typing import List, Dict
import math
import time
import logging

logger = logging.getLogger(__name__)

class Web3EnhancedSellTracker(EnhancedBaseTracker):
    """Enhanced sell pressure tracker with Web3 analysis capabilities"""
    
    def __init__(self, network: str):
        super().__init__(network)
        self.min_tokens_for_unknown = 50 if network == "base" else 100
        self.sell_cache = {}  # Cache for Web3-enhanced sells
    
    def analyze_wallet_sells(self, wallet_address: str, days_back: int = 1) -> List[Dict]:
        """Analyze token sells with Web3 enhancement"""
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
            "maxCount": "0x20"
        }])
        
        outgoing_transfers = outgoing_result.get("result", {}).get("transfers", [])
        logger.debug(f"Found {len(outgoing_transfers)} outgoing token transfers")
        
        sells = []
        method_summary = {"DEX": 0, "CEX": 0, "TELEGRAM_BOT": 0, "MEV_BOT": 0, "P2P_OTC": 0, "UNKNOWN": 0}
        
        # Web3 enhanced tracking
        web3_enhanced_count = 0
        total_sophistication = 0
        
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
            
            # Use centralized contract detection (now Web3-enhanced)
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
                
                # Create basic sell
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
                    "is_base_native": is_base_native,
                    "wallet_address": wallet_address
                }
                
                # 🚀 NEW: Enhance with Web3 data
                if self.web3_enabled and tx_hash:
                    enhanced_sell = self._enhance_sell_with_web3(sell, tx_hash)
                    sells.append(enhanced_sell)
                    web3_enhanced_count += 1
                    
                    # Track sophistication for summary
                    sophistication = enhanced_sell.get('sophistication_score', 0)
                    if sophistication > 0:
                        total_sophistication += sophistication
                    
                    # Enhanced logging with Web3 data
                    web3_data = enhanced_sell.get('web3_analysis', {})
                    method_used = web3_data.get('method_used', 'unknown')
                    
                    method_emoji = {
                        "DEX": "🔄", "CEX": "🏦", "TELEGRAM_BOT": "🤖", 
                        "MEV_BOT": "⚡", "P2P_OTC": "🤝", "UNKNOWN": "❓"
                    }
                    confidence_emoji = {"HIGH": "✅", "MEDIUM": "⚠️", "LOW": "❓"}
                    native_flag = "🔵" if is_base_native else ""
                    sophistication_flag = "🧠" if sophistication > 70 else "🔰" if sophistication > 40 else ""
                    
                    logger.debug(f"{method_emoji.get(sell_method, '❓')}{confidence_emoji[confidence]} {native_flag}{sophistication_flag}SOLD: {token_sold} ({amount_sold:.0f}) → {recipient_name} [{method_used}] | ~${estimated_usd:.0f} | Sophistication: {sophistication:.0f}")
                else:
                    sells.append(sell)
                    
                    # Original logging
                    method_emoji = {
                        "DEX": "🔄", "CEX": "🏦", "TELEGRAM_BOT": "🤖", 
                        "MEV_BOT": "⚡", "P2P_OTC": "🤝", "UNKNOWN": "❓"
                    }
                    confidence_emoji = {"HIGH": "✅", "MEDIUM": "⚠️", "LOW": "❓"}
                    native_flag = "🔵" if is_base_native else ""
                    
                    logger.debug(f"{method_emoji.get(sell_method, '❓')}{confidence_emoji[confidence]} {native_flag}SOLD: {token_sold} ({amount_sold:.0f}) → {recipient_name} | ~${estimated_usd:.0f}")
                
                method_summary[sell_method] += 1
        
        # Enhanced summary logging
        if sells:
            total_estimated_eth = sum(s.get("estimated_eth_value", 0) for s in sells)
            total_estimated_usd = sum(s.get("estimated_usd_value", 0) for s in sells)
            unique_tokens = len(set(s.get("token_sold") for s in sells))
            
            # Web3 enhanced stats
            if self.web3_enabled and web3_enhanced_count > 0:
                avg_sophistication = total_sophistication / web3_enhanced_count if web3_enhanced_count > 0 else 0
                high_sophistication_count = len([s for s in sells if s.get('sophistication_score', 0) > 70])
                sophisticated_methods = set()
                for s in sells:
                    web3_data = s.get('web3_analysis', {})
                    method = web3_data.get('method_used', 'unknown')
                    if method != 'unknown':
                        sophisticated_methods.add(method)
                
                print(f"📉 Found {len(sells)} sells: {unique_tokens} tokens, {total_estimated_eth:.4f} ETH (~${total_estimated_usd:.0f})")
                print(f"🧠 Avg Sophistication: {avg_sophistication:.1f} | High Sophistication: {high_sophistication_count}")
                if sophisticated_methods:
                    print(f"⚙️  Methods Used: {', '.join(list(sophisticated_methods)[:3])}")
            else:
                print(f"📉 Found {len(sells)} sells: {unique_tokens} tokens, {total_estimated_eth:.4f} ETH (~${total_estimated_usd:.0f})")
        
        logger.info(f"Found {len(sells)} significant {self.network} token sells")
        return sells
    
    def _enhance_sell_with_web3(self, sell: Dict, tx_hash: str) -> Dict:
        """Enhance sell data with Web3 analysis"""
        if not self.web3_enabled or not hasattr(self, 'web3_tracker'):
            return sell
        
        try:
            # Get detailed transaction analysis
            tx_details = self.web3_tracker.tx_analyzer.get_transaction_details(tx_hash)
            
            # Calculate sell-specific sophistication score
            sophistication_score = self._calculate_sell_sophistication_score(tx_details, sell)
            
            # Combine with basic sell data
            enhanced_sell = sell.copy()
            enhanced_sell.update({
                'web3_analysis': {
                    'gas_efficiency': tx_details.get('gas_efficiency', 0),
                    'gas_cost_eth': tx_details.get('total_gas_cost_eth', 0),
                    'method_used': tx_details.get('input_analysis', {}).get('method_name', 'unknown'),
                    'is_swap': tx_details.get('input_analysis', {}).get('is_swap', False),
                    'complexity_score': tx_details.get('input_analysis', {}).get('complexity_score', 0),
                    'block_timestamp': tx_details.get('timestamp', 0),
                    'sell_pressure_indicators': self._analyze_sell_pressure_indicators(tx_details, sell)
                },
                'sophistication_score': sophistication_score
            })
            
            return enhanced_sell
            
        except Exception as e:
            logger.error(f"Error enhancing sell analysis: {e}")
            return sell
    
    def _calculate_sell_sophistication_score(self, tx_details: Dict, sell: Dict) -> float:
        """Calculate sophistication score specific to sell transactions"""
        if not tx_details:
            return 0.0
        
        score = 0.0
        
        # Gas efficiency (important for sell timing)
        gas_efficiency = tx_details.get('gas_efficiency', 0)
        if gas_efficiency > 0.9:  # Very efficient
            score += 25
        elif gas_efficiency > 0.7:
            score += 15
        
        # Method sophistication (selling methods)
        input_analysis = tx_details.get('input_analysis', {})
        method_name = input_analysis.get('method_name', 'unknown')
        
        # Sell-specific method scoring
        sell_method_scores = {
            'transfer': 5,  # Simple transfer (low sophistication)
            'transferFrom': 10,  # Approved transfer
            'swapExactTokensForETH': 25,  # DEX sell
            'swapExactTokensForTokens': 30,  # DEX token swap
            'exactOutputSingle': 35,  # Uniswap V3 precision
            'exactOutput': 35,  # Uniswap V3 multi-hop
            'unknown': 0
        }
        
        score += sell_method_scores.get(method_name, 0)
        
        # Complexity bonus
        complexity = input_analysis.get('complexity_score', 0)
        score += complexity * 15  # Up to 15 points for complex transactions
        
        # Sell pressure timing analysis
        confidence = sell.get('confidence', 'LOW')
        if confidence == 'HIGH':
            score += 20  # High confidence recipient
        elif confidence == 'MEDIUM':
            score += 10
        
        # Platform sophistication
        platform = sell.get('platform', 'Unknown')
        platform_scores = {
            '1inch': 20,  # Aggregator = sophisticated
            'Uniswap': 15,  # Popular DEX
            'Telegram Bot': 25,  # Bot usage = sophisticated
            'Unknown': 0
        }
        score += platform_scores.get(platform, 0)
        
        # Gas price analysis (not panic selling vs. strategic selling)
        gas_price_gwei = tx_details.get('gas_price_gwei', 0)
        if 5 <= gas_price_gwei <= 25:  # Reasonable gas price = planned sell
            score += 10
        elif gas_price_gwei > 100:  # Very high gas = panic sell
            score -= 15
        
        return min(score, 100)  # Cap at 100
    
    def _analyze_sell_pressure_indicators(self, tx_details: Dict, sell: Dict) -> Dict:
        """Analyze indicators of sell pressure sophistication"""
        indicators = {
            'panic_sell_score': 0,
            'strategic_sell_score': 0,
            'timing_score': 0
        }
        
        # Gas price analysis
        gas_price_gwei = tx_details.get('gas_price_gwei', 0)
        if gas_price_gwei > 100:
            indicators['panic_sell_score'] += 30
        elif gas_price_gwei < 20:
            indicators['strategic_sell_score'] += 20
        
        # Method analysis
        method_name = tx_details.get('input_analysis', {}).get('method_name', 'unknown')
        if 'exact' in method_name.lower():
            indicators['strategic_sell_score'] += 15  # Precise amount = planned
        
        # Efficiency analysis
        gas_efficiency = tx_details.get('gas_efficiency', 0)
        if gas_efficiency > 0.8:
            indicators['strategic_sell_score'] += 10
        
        # Timing analysis (could be enhanced with block time patterns)
        timestamp = tx_details.get('timestamp', 0)
        if timestamp > 0:
            import datetime
            dt = datetime.datetime.fromtimestamp(timestamp)
            hour = dt.hour
            
            # Market hours vs. off-hours selling
            if 9 <= hour <= 16:  # Business hours
                indicators['strategic_sell_score'] += 5
            elif 22 <= hour or hour <= 6:  # Night selling
                indicators['panic_sell_score'] += 10
        
        # Calculate timing score
        indicators['timing_score'] = max(0, indicators['strategic_sell_score'] - indicators['panic_sell_score'])
        
        return indicators
    
    def _determine_sell_method(self, contract_info: Dict, to_address: str, amount: float, token: str) -> tuple:
        """Determine sell method using centralized contract detection"""
        if contract_info["type"] != "UNKNOWN":
            return contract_info["type"], contract_info["name"], "HIGH"
        
        # Enhanced heuristic detection with Web3 insights
        if self.web3_enabled and hasattr(self, 'web3_tracker'):
            try:
                # Get additional contract analysis
                address_analysis = self.web3_tracker.tx_analyzer.analyze_address_activity(to_address)
                if address_analysis.get('is_contract', False):
                    contract_data = address_analysis.get('contract_info', {})
                    complexity = contract_data.get('complexity_score', 0)
                    
                    if complexity > 0.5:  # High complexity contract
                        return "SMART_CONTRACT", f"Complex {self.network.title()} Contract", "MEDIUM"
            except Exception as e:
                logger.debug(f"Web3 contract analysis failed: {e}")
        
        # Fallback to heuristic detection
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
        """Enhanced sell pressure score calculation with Web3 data"""
        wallet_scores = token_data["wallet_scores"]
        sells = token_data["sells"]
        total_estimated_eth = token_data["total_estimated_eth"]
        
        if not wallet_scores or total_estimated_eth == 0 or not sells:
            return 0.0
        
        max_possible_wallet_score = 300
        weighted_eth_score = 0.0
        sophistication_bonus = 1.0
        
        # 🚀 NEW: Include Web3 sophistication data
        sophistication_scores = []
        panic_sell_indicators = 0
        strategic_sell_indicators = 0
        
        for sell in sells:
            wallet_score = sell.get("wallet_score", max_possible_wallet_score)
            estimated_eth = sell.get("estimated_eth_value", 0)
            confidence = sell.get("confidence", "LOW")
            method = sell.get("sell_method", "UNKNOWN")
            is_base_native = sell.get("is_base_native", False)
            
            # Web3 enhancements
            sophistication = sell.get("sophistication_score", 0)
            if sophistication > 0:
                sophistication_scores.append(sophistication)
            
            web3_data = sell.get("web3_analysis", {})
            sell_pressure_indicators = web3_data.get("sell_pressure_indicators", {})
            panic_sell_indicators += sell_pressure_indicators.get("panic_sell_score", 0)
            strategic_sell_indicators += sell_pressure_indicators.get("strategic_sell_score", 0)
            
            # Network-specific multipliers
            confidence_multipliers = {"HIGH": 1.0, "MEDIUM": 0.9, "LOW": 0.6}
            method_multipliers = {
                "CEX": 2.0, "TELEGRAM_BOT": 1.8, "MEV_BOT": 1.6,
                "DEX": 1.4, "P2P_OTC": 1.3, "SMART_CONTRACT": 1.5, "UNKNOWN": 1.0
            }
            
            # Base native penalty
            native_multiplier = 1.5 if (self.network == "base" and is_base_native) else 1.0
            
            # 🚀 NEW: Sophistication multiplier for sell pressure
            if sophistication > 0:
                # Higher sophistication = more credible sell pressure
                sophistication_multiplier = 1.0 + (sophistication / 300)  # Up to 1.33x
            else:
                sophistication_multiplier = 1.0
            
            confidence_mult = confidence_multipliers.get(confidence, 0.5)
            method_mult = method_multipliers.get(method, 1.0)
            
            if estimated_eth > 0:
                wallet_quality_multiplier = (max_possible_wallet_score - wallet_score + 100) / 100
                eth_component = math.log(1 + estimated_eth * 1000) * 2
                weighted_eth_score += eth_component * wallet_quality_multiplier * confidence_mult * method_mult * native_multiplier * sophistication_multiplier
        
        # 🚀 NEW: Calculate sophistication bonus for sell pressure
        if sophistication_scores:
            avg_sophistication = sum(sophistication_scores) / len(sophistication_scores)
            sophistication_bonus = 1.0 + (avg_sophistication / 400)  # Up to 1.25x
            
            # Panic vs strategic sell analysis
            if strategic_sell_indicators > panic_sell_indicators:
                sophistication_bonus *= 1.1  # Strategic selling = more credible pressure
            elif panic_sell_indicators > strategic_sell_indicators * 2:
                sophistication_bonus *= 0.9  # Panic selling = less credible
        
        # Use parent class consensus calculation
        score_components = self.calculate_score_components(wallet_scores, max_possible_wallet_score)
        weighted_consensus_score = score_components["weighted_consensus"]
        
        # Network bonus
        network_bonus = 1.2 if self.network == "base" else 1.0
        
        final_score = (weighted_eth_score * weighted_consensus_score * network_bonus * sophistication_bonus) / 10
        return round(final_score, 2)
    
    def get_ranked_tokens(self, token_summary: Dict) -> List[tuple]:
        """Get tokens ranked by enhanced sell pressure score"""
        scored_tokens = []
        
        for token, data in token_summary.items():
            sell_score = self.calculate_token_sell_score(data)
            scored_tokens.append((token, data, sell_score))
        
        return sorted(scored_tokens, key=lambda x: x[2], reverse=True)
    
    def analyze_wallet_purchases(self, wallet_address: str, days_back: int) -> List[Dict]:
        """Not used for sell tracker, but required by abstract base"""
        return []
    
    def analyze_all_trading_methods(self, num_wallets: int = 173, max_wallets_for_sse: bool = False, days_back: int = 1) -> Dict:
        """Analyze all sell methods - main entry point"""
        return self.analyze_all_sell_methods(num_wallets, max_wallets_for_sse, days_back)
    
    def analyze_all_sell_methods(self, num_wallets: int = 173, max_wallets_for_sse: bool = False, days_back: int = 1) -> Dict:
        """Enhanced analyze ALL sell methods with Web3 insights"""
        logger.info(f"Starting comprehensive {self.network} sell pressure analysis: {num_wallets} wallets, {days_back} days")
        
        # Limit wallets for SSE to prevent hanging
        if max_wallets_for_sse:
            num_wallets = min(num_wallets, 25)  # Max 25 for SSE
            logger.info(f"SSE mode: limiting to {num_wallets} wallets")
        
        print(f"🚀 Starting {self.network.title()} Sell Pressure Analysis")
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
        
        all_sells = []
        token_summary = {}
        method_summary = {"DEX": 0, "CEX": 0, "TELEGRAM_BOT": 0, "MEV_BOT": 0, "P2P_OTC": 0, "SMART_CONTRACT": 0, "UNKNOWN": 0}
        
        # Network-specific summary
        network_summary = {}
        if self.network == "base":
            network_summary = {"native": 0, "bridged": 0}
        
        # Web3 enhanced tracking
        web3_analysis_summary = {
            "total_transactions_analyzed": 0,
            "sophisticated_sells": 0,
            "panic_sells": 0,
            "strategic_sells": 0,
            "method_distribution": {},
            "avg_sophistication": 0,
            "avg_gas_efficiency": 0,
            "sell_pressure_confidence": 0
        }
        
        for i, wallet in enumerate(top_wallets, 1):
            wallet_address = wallet["address"]
            
            # Progress logging with Web3 awareness
            if i % 5 == 1 or i <= 3:
                sophistication_info = ""
                if self.web3_enabled and wallet.get('web3_analysis'):
                    wallet_sophistication = wallet['web3_analysis'].get('sophistication_score', 0)
                    sophistication_info = f" (Sophistication: {wallet_sophistication:.0f})"
                
                print(f"🔄 Processing wallet {i}/{len(top_wallets)}: {wallet_address[:10]}...{sophistication_info}")
                logger.info(f"Progress: {i}/{len(top_wallets)} wallets processed")
            
            wallet_score = wallet["score"]
            
            # Progress updates every wallet
            print(f"🔄 [{i}/{len(top_wallets)}] Processing wallet {wallet_address[:8]}... (Score: {wallet_score})")
            
            # Send progress via logger (which gets captured by SSE)
            if i % 5 == 1 or i <= 3:
                logger.info(f"Progress: {i}/{len(top_wallets)} wallets processed")
                logger.info(f"[{i}/{num_wallets}] {self.network.title()} Wallet: {wallet_address} (Score: {wallet_score})")
            
            try:
                sells = self.analyze_wallet_sells(wallet_address, days_back)
                
                # Add wallet score
                for sell in sells:
                    sell["wallet_score"] = wallet_score
                
                all_sells.extend(sells)
                
                # 🚀 NEW: Update Web3 analysis summary
                if self.web3_enabled:
                    for sell in sells:
                        web3_data = sell.get('web3_analysis', {})
                        if web3_data:
                            web3_analysis_summary["total_transactions_analyzed"] += 1
                            
                            sophistication = sell.get('sophistication_score', 0)
                            if sophistication > 70:
                                web3_analysis_summary["sophisticated_sells"] += 1
                            
                            # Analyze sell pressure indicators
                            sell_indicators = web3_data.get('sell_pressure_indicators', {})
                            panic_score = sell_indicators.get('panic_sell_score', 0)
                            strategic_score = sell_indicators.get('strategic_sell_score', 0)
                            
                            if panic_score > strategic_score:
                                web3_analysis_summary["panic_sells"] += 1
                            elif strategic_score > panic_score:
                                web3_analysis_summary["strategic_sells"] += 1
                            
                            method = web3_data.get('method_used', 'unknown')
                            if method != 'unknown':
                                web3_analysis_summary["method_distribution"][method] = web3_analysis_summary["method_distribution"].get(method, 0) + 1
                            
                            gas_efficiency = web3_data.get('gas_efficiency', 0)
                            if gas_efficiency > 0:
                                current_avg = web3_analysis_summary["avg_gas_efficiency"]
                                count = web3_analysis_summary["total_transactions_analyzed"]
                                web3_analysis_summary["avg_gas_efficiency"] = ((current_avg * (count - 1)) + gas_efficiency) / count
                
                # Aggregate data
                self._aggregate_sell_data(sells, token_summary, method_summary, network_summary, wallet_address)
                
                # Enhanced progress summary every 10 wallets
                if i % 10 == 0:
                    total_sells_so_far = len(all_sells)
                    progress_msg = f"📈 Progress Update: {i} wallets, {total_sells_so_far} sells"
                    
                    if self.web3_enabled and web3_analysis_summary["total_transactions_analyzed"] > 0:
                        sophisticated_pct = (web3_analysis_summary["sophisticated_sells"] / web3_analysis_summary["total_transactions_analyzed"]) * 100
                        panic_count = web3_analysis_summary["panic_sells"]
                        strategic_count = web3_analysis_summary["strategic_sells"]
                        progress_msg += f" | 🧠 {sophisticated_pct:.1f}% sophisticated | Panic: {panic_count}, Strategic: {strategic_count}"
                    
                    print(progress_msg)
                
                time.sleep(0.5)  # Rate limiting
                
                # Memory cleanup every 10 wallets
                if i % 10 == 0:
                    import gc
                    gc.collect()
                    logger.debug(f"Memory cleanup at wallet {i}")
                
            except Exception as e:
                logger.error(f"Error analyzing {self.network} wallet {wallet_address}: {e}")
                continue
        
        return self._generate_sell_analysis(all_sells, token_summary, method_summary, network_summary, web3_analysis_summary)
    
    def _aggregate_sell_data(self, sells, token_summary, method_summary, network_summary, wallet_address):
        """Enhanced aggregation with Web3 data"""
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
                    "is_base_native": is_base_native,
                    # 🚀 NEW: Web3 enhanced fields
                    "web3_enhanced": self.web3_enabled,
                    "sophistication_scores": [],
                    "panic_sell_count": 0,
                    "strategic_sell_count": 0,
                    "avg_gas_efficiency": 0,
                    "high_sophistication_count": 0,
                    "sell_pressure_confidence": 0
                }
            
            token_summary[token]["count"] += 1
            token_summary[token]["wallets"].add(wallet_address)
            token_summary[token]["total_estimated_eth"] += estimated_eth
            token_summary[token]["wallet_scores"].append(sell.get("wallet_score", 300))
            token_summary[token]["sells"].append(sell)
            token_summary[token]["methods"].add(method)
            token_summary[token]["platforms"].add(sell.get("platform", "Unknown"))
            token_summary[token]["confidence_levels"].add(sell.get("confidence", "LOW"))
            
            # 🚀 NEW: Web3 enhanced aggregation
            if self.web3_enabled:
                sophistication = sell.get("sophistication_score", 0)
                if sophistication > 0:
                    token_summary[token]["sophistication_scores"].append(sophistication)
                    if sophistication > 70:
                        token_summary[token]["high_sophistication_count"] += 1
                
                # Analyze sell pressure indicators
                web3_data = sell.get("web3_analysis", {})
                sell_indicators = web3_data.get("sell_pressure_indicators", {})
                panic_score = sell_indicators.get("panic_sell_score", 0)
                strategic_score = sell_indicators.get("strategic_sell_score", 0)
                
                if panic_score > strategic_score:
                    token_summary[token]["panic_sell_count"] += 1
                elif strategic_score > panic_score:
                    token_summary[token]["strategic_sell_count"] += 1
                
                gas_efficiency = web3_data.get("gas_efficiency", 0)
                if gas_efficiency > 0:
                    current_avg = token_summary[token]["avg_gas_efficiency"]
                    count = len(token_summary[token]["sophistication_scores"])
                    if count > 0:
                        token_summary[token]["avg_gas_efficiency"] = ((current_avg * (count - 1)) + gas_efficiency) / count
                
                # Calculate sell pressure confidence
                total_indicators = panic_score + strategic_score
                if total_indicators > 0:
                    confidence_score = strategic_score / total_indicators  # Strategic = more confident pressure
                    token_summary[token]["sell_pressure_confidence"] = confidence_score
            
            # Method summary
            method_summary[method] += 1
            
            # Network-specific summary
            if self.network == "base" and isinstance(network_summary, dict):
                if is_base_native:
                    network_summary["native"] += 1
                else:
                    network_summary["bridged"] += 1
    
    def _generate_sell_analysis(self, all_sells, token_summary, method_summary, network_summary, web3_analysis_summary=None):
        """Generate enhanced sell analysis results with Web3 insights"""
        logger.info(f"Generating {self.network} sell analysis...")
        
        if not all_sells:
            logger.info(f"✅ No significant {self.network} sell pressure detected!")
            print(f"✅ No significant {self.network} sell pressure detected!")
            return {}
        
        total_estimated_eth = sum(sell.get("estimated_eth_value", 0) for sell in all_sells)
        total_estimated_usd = sum(sell.get("estimated_usd_value", 0) for sell in all_sells)
        
        ranked_tokens = self.get_ranked_tokens(token_summary)
        
        # Enhanced summary output with Web3 data
        print("="*60)
        print(f"🎉 {self.network.title()} Sell Pressure Analysis Complete!")
        print(f"📉 Total Sells: {len(all_sells)}")
        print(f"🪙 Unique Tokens: {len(token_summary)}")
        print(f"💰 Total Estimated ETH: {total_estimated_eth:.4f} ETH")
        print(f"💵 Total USD Value: ${total_estimated_usd:.0f}")
        
        # 🚀 NEW: Web3 enhanced summary
        if self.web3_enabled and web3_analysis_summary and web3_analysis_summary["total_transactions_analyzed"] > 0:
            total_analyzed = web3_analysis_summary["total_transactions_analyzed"]
            sophisticated_count = web3_analysis_summary["sophisticated_sells"]
            panic_count = web3_analysis_summary["panic_sells"]
            strategic_count = web3_analysis_summary["strategic_sells"]
            sophisticated_pct = (sophisticated_count / total_analyzed) * 100
            avg_gas_efficiency = web3_analysis_summary["avg_gas_efficiency"]
            
            print(f"🧠 Web3 Enhanced Sell Analysis:")
            print(f"   ⚡ Transactions Analyzed: {total_analyzed}")
            print(f"   🎯 Sophisticated Sells: {sophisticated_count} ({sophisticated_pct:.1f}%)")
            print(f"   😰 Panic Sells: {panic_count}")
            print(f"   🎯 Strategic Sells: {strategic_count}")
            print(f"   ⛽ Avg Gas Efficiency: {avg_gas_efficiency:.1f}%")
            
            if web3_analysis_summary["method_distribution"]:
                top_methods = sorted(web3_analysis_summary["method_distribution"].items(), key=lambda x: x[1], reverse=True)[:3]
                methods_str = ", ".join([f"{method}({count})" for method, count in top_methods])
                print(f"   🔧 Top Sell Methods: {methods_str}")
            
            # Calculate overall sell pressure confidence
            if strategic_count + panic_count > 0:
                confidence_ratio = strategic_count / (strategic_count + panic_count)
                confidence_level = "HIGH" if confidence_ratio > 0.6 else "MEDIUM" if confidence_ratio > 0.3 else "LOW"
                print(f"   📊 Sell Pressure Confidence: {confidence_level} ({confidence_ratio:.2f})")
        
        if ranked_tokens:
            top_token = ranked_tokens[0]
            sell_score = top_token[2]
            print(f"🏆 Top Sell Pressure: {top_token[0]} (Sell Score: {sell_score})")
            
            # Show Web3 insights for top token
            if self.web3_enabled and top_token[1].get("sophistication_scores"):
                avg_sophistication = sum(top_token[1]["sophistication_scores"]) / len(top_token[1]["sophistication_scores"])
                high_soph_count = top_token[1]["high_sophistication_count"]
                panic_count = top_token[1]["panic_sell_count"]
                strategic_count = top_token[1]["strategic_sell_count"]
                confidence = top_token[1]["sell_pressure_confidence"]
                
                print(f"   🧠 Avg Sophistication: {avg_sophistication:.1f} | High-Soph: {high_soph_count}")
                print(f"   📊 Panic: {panic_count}, Strategic: {strategic_count} | Confidence: {confidence:.2f}")
        
        # Method breakdown
        if method_summary:
            print("🔧 Sell Method Breakdown:")
            for method, count in sorted(method_summary.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / len(all_sells)) * 100
                method_emoji = {
                    "DEX": "🔄", "CEX": "🏦", "TELEGRAM_BOT": "🤖", 
                    "MEV_BOT": "⚡", "P2P_OTC": "🤝", "SMART_CONTRACT": "🔧", "UNKNOWN": "❓"
                }
                emoji = method_emoji.get(method, "❓")
                print(f"   {emoji} {method}: {count} ({percentage:.1f}%)")
        
        # Base native breakdown (if applicable)
        if self.network == "base" and network_summary:
            native_count = network_summary["native"]
            bridged_count = network_summary["bridged"]
            total_count = native_count + bridged_count
            if total_count > 0:
                native_pct = (native_count / total_count) * 100
                print(f"🔵 Base Native Sells: {native_count} ({native_pct:.1f}%), Bridged: {bridged_count} ({100-native_pct:.1f}%)")
        
        print("="*60)
        
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
        
        # 🚀 NEW: Add Web3 analysis summary
        if self.web3_enabled and web3_analysis_summary:
            result["web3_analysis"] = web3_analysis_summary
        
        return result

# Backwards compatibility - update the original class name
ComprehensiveSellTracker = Web3EnhancedSellTracker

# Convenience classes for specific networks
class EthComprehensiveSellTracker(Web3EnhancedSellTracker):
    def __init__(self):
        super().__init__("ethereum")

class BaseComprehensiveSellTracker(Web3EnhancedSellTracker):
    def __init__(self, network="base"):
        super().__init__(network)

def main():
    """Test the enhanced sell tracker"""
    # Test both networks
    for network in ["ethereum", "base"]:
        logger.info(f"Testing {network} enhanced sell tracker...")
        tracker = Web3EnhancedSellTracker(network)
        
        if tracker.test_connection():
            print(f"🧪 Testing {network} enhanced sell tracker...")
            results = tracker.analyze_all_sell_methods(num_wallets=5, days_back=0.1)  # Quick test
            
            if results:
                web3_enhanced = results.get('web3_analysis', {}).get('total_transactions_analyzed', 0) > 0
                print(f"✅ {network.title()} enhanced sell tracker working! Web3 Enhanced: {web3_enhanced}")
                logger.info(f"{network.title()} results: {len(results.get('ranked_tokens', []))} tokens")
            else:
                print(f"⚠️  {network.title()} enhanced sell tracker working but no data found")
        else:
            logger.error(f"Failed to connect to {network}")

if __name__ == "__main__":
    main()