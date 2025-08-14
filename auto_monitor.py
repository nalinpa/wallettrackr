import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import json
from flask import Blueprint
import requests
import io
import sys
from contextlib import redirect_stdout, redirect_stderr
import traceback

# Assuming these imports exist
from tracker.buy_tracker import ComprehensiveBuyTracker
from tracker.sell_tracker import ComprehensiveSellTracker
from config.settings import settings, monitor_config, telegram_config

logger = logging.getLogger(__name__)

@dataclass
class Alert:
    """Alert data structure"""
    timestamp: datetime
    network: str
    alert_type: str
    token: str
    message: str
    data: Dict
    confidence: str = "MEDIUM"
    
    def to_dict(self):
        return {
            'timestamp': self.timestamp.isoformat(),
            'network': self.network,
            'alert_type': self.alert_type,
            'token': self.token,
            'message': self.message,
            'data': self.data,
            'confidence': self.confidence
        }

class TelegramNotifier:
    """Telegram notification handler"""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        self.recent_alerts = {}  # {token: last_alert_time}
        self.alert_cooldown_hours = 2
        
        if self.enabled:
            logger.info(f"Telegram notifications enabled for chat: {chat_id}")
        else:
            logger.debug("Telegram notifications disabled (missing bot_token or chat_id)")
    
    def send_alert(self, alert: Alert) -> bool:
        """Send alert to Telegram with DEX links"""
        if not self.enabled:
            return False
        
        try:
            # Format message
            confidence_emoji = {"HIGH": "🔥", "MEDIUM": "⚠️", "LOW": "ℹ️"}
            type_emoji = {'new_token': '🆕', 'high_activity': '📈', 'sell_pressure': '📉'}
            
            emoji = f"{type_emoji.get(alert.alert_type, '🔔')} {confidence_emoji.get(alert.confidence, '📊')}"
            
            message = f"{emoji} *{alert.token}* Alert\n"
            message += f"🌐 Network: *{alert.network.upper()}*\n"
            message += f"📊 Type: {alert.alert_type.replace('_', ' ').title()}\n"
            message += f"🎯 Confidence: *{alert.confidence}*\n\n"
            
            # Add data details
            if alert.data:
                if 'wallet_count' in alert.data:
                    message += f"👥 Wallets: *{alert.data['wallet_count']}*\n"
                if 'total_eth_spent' in alert.data:
                    message += f"💰 ETH Spent: *{alert.data['total_eth_spent']:.3f}*\n"
                elif 'total_estimated_eth' in alert.data:
                    message += f"💰 ETH Value: *{alert.data['total_estimated_eth']:.3f}*\n"
                if 'alpha_score' in alert.data:
                    message += f"📈 Alpha Score: *{alert.data['alpha_score']:.1f}*\n"
                elif 'sell_score' in alert.data:
                    message += f"📉 Sell Score: *{alert.data['sell_score']:.1f}*\n"
                if 'platforms' in alert.data and alert.data['platforms']:
                    platforms = list(alert.data['platforms'])[:2]
                    message += f"🏪 Platforms: {', '.join(platforms)}\n"
            
            message += f"\n🕐 {alert.timestamp.strftime('%H:%M:%S')}"
            
            # Add DEX links
            message += f"\n\n🔗 *Quick Links:*"
            
            # Get contract address from alert data
            contract_address = None
            if alert.data and 'contract_address' in alert.data:
                contract_address = alert.data['contract_address']
            
            if contract_address:
                # DexScreener link
                if alert.network.lower() == 'base':
                    dexscreener_url = f"https://dexscreener.com/base/{contract_address}"
                    uniswap_url = f"https://app.uniswap.org/#/swap?outputCurrency={contract_address}&chain=base"
                else:  # ethereum
                    dexscreener_url = f"https://dexscreener.com/ethereum/{contract_address}"
                    uniswap_url = f"https://app.uniswap.org/#/swap?outputCurrency={contract_address}&chain=ethereum"
                
                message += f"\n📊 [DexScreener]({dexscreener_url})"
                message += f"\n🦄 [Uniswap]({uniswap_url})"
            else:
                # Fallback search links
                message += f"\n📊 [Search DexScreener](https://dexscreener.com/search?q={alert.token})"
                message += f"\n🦄 [Search Uniswap](https://app.uniswap.org/)"
            
            # Send to Telegram
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"✅ Telegram alert sent for {alert.token}")
                return True
            else:
                logger.error(f"❌ Telegram API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error sending Telegram alert: {e}")
            return False
    
class EnhancedMonitor:
    """Enhanced monitor with rich console output like the trackers"""
    
    def __init__(self):
        self.is_running = False
        self.last_check = None
        self.next_check = None
        self.alerts = []
        self.known_tokens = set()
        self.seen_purchases = 0
        self.total_alerts = 0
        self.monitor_thread = None
        
        # Configuration
        self.config = {
            'check_interval_minutes': monitor_config.default_check_interval_minutes,
            'networks': [net.value for net in monitor_config.default_networks],
            'num_wallets': 173,
            'use_interval_for_timeframe': True,
            'alert_thresholds': monitor_config.alert_thresholds.copy()
        }
        
        self.telegram = TelegramNotifier(
            bot_token=telegram_config.bot_token,
            chat_id=telegram_config.chat_id
        )
    
    # Update notification channels based on settings
        self.notification_channels = {
            'console': True,
            'file': False,
            'telegram': True
        }
        
        self.alert_thresholds = monitor_config.alert_thresholds.copy()
    
    def start_monitoring(self) -> Dict:
        """Start the monitoring with enhanced console output"""
        if self.is_running:
            return {'status': 'error', 'message': 'Monitor already running'}
        
        print("\n" + "="*70)
        print("🚀 STARTING ENHANCED CRYPTO MONITOR")
        print("="*70)
        print(f"📊 Configuration:")
        print(f"   🕐 Check Interval: {self.config['check_interval_minutes']} minutes")
        print(f"   🌐 Networks: {', '.join(self.config['networks'])}")
        print(f"   👥 Wallets per check: {self.config['num_wallets']}")
        print(f"   🎯 Alert Thresholds:")
        for threshold, value in self.alert_thresholds.items():
            print(f"      {threshold}: {value}")
        print("="*70)
        
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info("Enhanced monitor started successfully")
        print("✅ Monitor started successfully! Check console for real-time updates.")
        
        return {
            'status': 'success', 
            'message': 'Monitor started with enhanced logging',
            'config': self.config
        }
    
    def stop_monitoring(self) -> Dict:
        """Stop the monitoring"""
        if not self.is_running:
            return {'status': 'error', 'message': 'Monitor not running'}
        
        print("\n" + "="*70)
        print("🛑 STOPPING CRYPTO MONITOR")
        print("="*70)
        print(f"📊 Session Summary:")
        print(f"   🚨 Total Alerts: {self.total_alerts}")
        print(f"   🪙 Known Tokens: {len(self.known_tokens)}")
        print(f"   💰 Seen Purchases: {self.seen_purchases}")
        if self.last_check:
            print(f"   🕐 Last Check: {self.last_check.strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)
        
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        logger.info("Monitor stopped")
        print("✅ Monitor stopped successfully!")
        
        return {'status': 'success', 'message': 'Monitor stopped'}
    
    def _monitor_loop(self):
        """Main monitoring loop with enhanced output"""
        print(f"🔄 Monitor loop started - checking every {self.config['check_interval_minutes']} minutes")
        
        while self.is_running:
            try:
                self._calculate_next_check()
                print(f"\n⏰ Next check scheduled for: {self.next_check.strftime('%H:%M:%S')}")
                
                # Wait for the interval
                self._wait_for_interval()
                
                if not self.is_running:
                    break
                
                # Perform the check
                self.check_for_new_tokens()
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
                print(f"❌ Monitor loop error: {e}")
                time.sleep(60)  # Wait a minute before retrying
    
    def _calculate_next_check(self):
        """Calculate when the next check should occur"""
        interval_seconds = self.config['check_interval_minutes'] * 60
        self.next_check = datetime.now() + timedelta(seconds=interval_seconds)
    
    def _wait_for_interval(self):
        """Wait for the check interval with progress indicators"""
        interval_seconds = self.config['check_interval_minutes'] * 60
        
        # Show countdown every 30 seconds for long intervals
        if interval_seconds > 60:
            countdown_interval = 30
            remaining = interval_seconds
            
            while remaining > 0 and self.is_running:
                if remaining % countdown_interval == 0 or remaining <= 10:
                    minutes = remaining // 60
                    seconds = remaining % 60
                    if minutes > 0:
                        print(f"⏳ Next check in {minutes}m {seconds}s...")
                    else:
                        print(f"⏳ Next check in {seconds}s...")
                
                time.sleep(min(1, remaining))
                remaining -= 1
        else:
            time.sleep(interval_seconds)
    
    def check_for_new_tokens(self):
        """Enhanced token checking with detailed console output"""
        print("\n" + "="*70)
        print("🔍 STARTING TOKEN ANALYSIS CYCLE")
        print("="*70)
        print(f"🕐 Check Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        self.last_check = datetime.now()
        cycle_alerts = []
        cycle_new_tokens = 0
        cycle_total_purchases = 0
        
        # Determine timeframe
        if self.config['use_interval_for_timeframe']:
            timeframe_hours = self.config['check_interval_minutes'] / 60
            days_back = max(0.1, timeframe_hours / 24)  # Convert to days, minimum 2.4 hours
        else:
            days_back = 1
        
        print(f"📊 Analysis Parameters:")
        print(f"   🕐 Timeframe: {days_back:.2f} days ({timeframe_hours:.1f} hours)" if self.config['use_interval_for_timeframe'] else f"   🕐 Timeframe: {days_back} days")
        print(f"   👥 Wallets: {self.config['num_wallets']}")
        print(f"   🌐 Networks: {', '.join(self.config['networks'])}")
        print("-" * 70)
        
        # Analyze each network
        for network in self.config['networks']:
            try:
                print(f"\n🌐 ANALYZING {network.upper()} NETWORK")
                print("-" * 50)
                
                network_alerts = self._analyze_network(network, days_back)
                cycle_alerts.extend(network_alerts)
                
                # Count new tokens for this network
                network_new_tokens = len([alert for alert in network_alerts if alert.alert_type == 'new_token'])
                network_purchases = sum([alert.data.get('total_purchases', 0) for alert in network_alerts])
                
                cycle_new_tokens += network_new_tokens
                cycle_total_purchases += network_purchases
                
                print(f"✅ {network.upper()} Analysis Complete:")
                print(f"   🆕 New Tokens: {network_new_tokens}")
                print(f"   💰 Total Purchases: {network_purchases}")
                print(f"   🚨 Alerts Generated: {len(network_alerts)}")
                
            except Exception as e:
                logger.error(f"Error analyzing {network}: {e}", exc_info=True)
                print(f"❌ Error analyzing {network}: {e}")
                continue
        
        # Update global stats
        self.seen_purchases += cycle_total_purchases
        self.total_alerts += len(cycle_alerts)
        
        # Process alerts
        if cycle_alerts:
            print(f"\n🚨 PROCESSING {len(cycle_alerts)} ALERTS")
            print("-" * 50)
            
            for alert in cycle_alerts:
                self._process_alert(alert)
            
            self.alerts.extend(cycle_alerts)
            
            # Keep only recent alerts
            max_alerts = monitor_config.max_stored_alerts
            if len(self.alerts) > max_alerts:
                self.alerts = self.alerts[-max_alerts:]
        
        # Cycle summary
        print("\n" + "="*70)
        print("📊 CYCLE SUMMARY")
        print("="*70)
        print(f"🆕 New Tokens Discovered: {cycle_new_tokens}")
        print(f"💰 Total Purchases Analyzed: {cycle_total_purchases}")
        print(f"🚨 Alerts Generated: {len(cycle_alerts)}")
        print(f"📈 Session Totals:")
        print(f"   🪙 Known Tokens: {len(self.known_tokens)}")
        print(f"   💰 Total Purchases: {self.seen_purchases}")
        print(f"   🚨 Total Alerts: {self.total_alerts}")
        print("="*70)
        
        if cycle_alerts:
            print("🎯 TOP ALERTS THIS CYCLE:")
            for i, alert in enumerate(cycle_alerts[:3], 1):
                confidence_emoji = {"HIGH": "🔥", "MEDIUM": "⚠️", "LOW": "ℹ️"}
                print(f"   {i}. {confidence_emoji.get(alert.confidence, '📊')} {alert.message}")
        
        print(f"⏰ Next check in {self.config['check_interval_minutes']} minutes\n")
 
    def _analyze_network(self, network: str, days_back: float) -> List[Alert]:
        """Analyze a specific network with detailed output"""
        alerts = []
        
        try:
            # Buy analysis with console capture
            print(f"🔍 Analyzing {network} buy activity...")
            
            buy_tracker = ComprehensiveBuyTracker(network)
            
            if not buy_tracker.test_connection():
                print(f"❌ {network} connection failed")
                return alerts
            
            print(f"✅ {network} connection successful")
            
            # Use configured wallet count
            monitor_wallets = self.config['num_wallets']
            print(f"📊 Analyzing {monitor_wallets} top {network} wallets...")
            
            # Capture and relay progress from buy tracker
            class ProgressCapture:
                def __init__(self, network_name):
                    self.network_name = network_name
                    self.original_print = print
                
                def write(self, text):
                    if text.strip():
                        # Relay important progress messages to monitor console
                        if any(keyword in text for keyword in ['Processing wallet', 'Found', 'purchases', 'tokens']):
                            print(f"   📊 {self.network_name}: {text.strip()}")
            
            buy_results = buy_tracker.analyze_all_trading_methods(
                num_wallets=monitor_wallets,
                days_back=days_back,
                max_wallets_for_sse=False
            )
            
            if buy_results and buy_results.get('ranked_tokens'):
                total_tokens = len(buy_results['ranked_tokens'])
                total_purchases = buy_results.get('total_purchases', 0)
                total_eth = buy_results.get('total_eth_spent', 0)
                
                print(f"💰 Found {total_tokens} tokens with buy activity")
                print(f"   📈 Total purchases: {total_purchases}")
                print(f"   💎 Total ETH spent: {total_eth:.3f}")
                
                # Process buy results for alerts
                buy_alerts = self._process_buy_results(network, buy_results)
                alerts.extend(buy_alerts)
                
                if buy_alerts:
                    print(f"   🚨 Generated {len(buy_alerts)} buy alerts")
            else:
                print(f"📊 No significant {network} buy activity detected")
            
            # Sell analysis with console capture
            print(f"🔍 Analyzing {network} sell pressure...")
            sell_tracker = ComprehensiveSellTracker(network)
            
            sell_results = sell_tracker.analyze_all_sell_methods(
                num_wallets=monitor_wallets,
                days_back=days_back,
                max_wallets_for_sse=False
            )
            
            if sell_results and sell_results.get('ranked_tokens'):
                total_sell_tokens = len(sell_results['ranked_tokens'])
                total_sells = sell_results.get('total_sells', 0)
                total_sell_eth = sell_results.get('total_estimated_eth', 0)
                
                print(f"📉 Found {total_sell_tokens} tokens with sell pressure")
                print(f"   📉 Total sells: {total_sells}")
                print(f"   💰 Total ETH value: {total_sell_eth:.3f}")
                
                # Process sell results for alerts
                sell_alerts = self._process_sell_results(network, sell_results)
                alerts.extend(sell_alerts)
                
                if sell_alerts:
                    print(f"   🚨 Generated {len(sell_alerts)} sell alerts")
            else:
                print(f"📊 No significant {network} sell pressure detected")
            
            # Network analysis summary
            total_alerts = len(alerts)
            if total_alerts > 0:
                high_conf = len([a for a in alerts if a.confidence == 'HIGH'])
                medium_conf = len([a for a in alerts if a.confidence == 'MEDIUM'])
                low_conf = len([a for a in alerts if a.confidence == 'LOW'])
                
                print(f"📊 {network.upper()} Alert Summary:")
                print(f"   🔥 High confidence: {high_conf}")
                print(f"   ⚠️ Medium confidence: {medium_conf}")
                print(f"   ℹ️ Low confidence: {low_conf}")
                
                # Show top 3 alerts
                sorted_alerts = sorted(alerts, key=lambda x: {
                    'HIGH': 3, 'MEDIUM': 2, 'LOW': 1
                }.get(x.confidence, 0), reverse=True)
                
                print(f"🏆 Top alerts:")
                for i, alert in enumerate(sorted_alerts[:3], 1):
                    confidence_emoji = {"HIGH": "🔥", "MEDIUM": "⚠️", "LOW": "ℹ️"}
                    type_emoji = {'new_token': '🆕', 'high_activity': '📈', 'sell_pressure': '📉'}
                    
                    wallets = alert.data.get('wallet_count', 0)
                    eth_value = alert.data.get('total_eth_spent', alert.data.get('total_estimated_eth', 0))
                    score = alert.data.get('alpha_score', alert.data.get('sell_score', 0))
                    
                    print(f"   {i}. {type_emoji.get(alert.alert_type, '🔔')}{confidence_emoji.get(alert.confidence, '📊')} "
                        f"{alert.token}: {wallets} wallets, {eth_value:.3f} ETH, score={score:.1f}")
            
        except Exception as e:
            logger.error(f"Error analyzing {network}: {e}", exc_info=True)
            print(f"❌ {network} analysis error: {e}")
            
            error_lines = str(e).split('\n')[:2] 
            for line in error_lines:
                if line.strip():
                    print(f"   🔍 Error detail: {line.strip()}")
        
        return alerts   
 
    def _should_alert_for_token(self, token: str, alert_type: str) -> bool:
        """Check if we should alert for this token (avoid duplicates)"""
        now = datetime.now()
        alert_key = f"{token}_{alert_type}"
        
        if alert_key in self.recent_alerts:
            last_alert_time = self.recent_alerts[alert_key]
            time_diff = now - last_alert_time
            
            if time_diff.total_seconds() < (self.alert_cooldown_hours * 3600):
                hours_remaining = self.alert_cooldown_hours - (time_diff.total_seconds() / 3600)
                print(f"🔕 Skipping duplicate alert for {token} (cooldown: {hours_remaining:.1f}h remaining)")
                return False
        
        self.recent_alerts[alert_key] = now
        return True
    
    def _process_buy_results(self, network: str, results: Dict) -> List[Alert]:
        """Process buy results and generate alerts"""
        alerts = []
        ranked_tokens = results.get('ranked_tokens', [])
        
        for token, data, alpha_score in ranked_tokens[:10]:
            wallet_count = len(data.get('wallets', []))
            total_eth = data.get('total_eth_spent', 0)
            
            if (wallet_count >= self.alert_thresholds.get('min_wallets', 3) and 
                total_eth >= self.alert_thresholds.get('min_eth_total', 0.1) and
                alpha_score >= self.alert_thresholds.get('min_alpha_score', 10)):
                
                # Check if it's a new token
                is_new = token not in self.known_tokens
                alert_type = 'new_token' if is_new else 'high_activity'
                
                # Check cooldown to prevent duplicates
                if not self._should_alert_for_token(token, alert_type):
                    continue
            
                self.known_tokens.add(token)
                
                alert_type = 'new_token' if is_new else 'high_activity'
                confidence = self._determine_confidence(wallet_count, total_eth, alpha_score)
                
                confidence_emoji = {"HIGH": "🔥", "MEDIUM": "⚠️", "LOW": "ℹ️"}
                new_flag = "🆕" if is_new else "📈"
                
                message = f"{new_flag} {confidence_emoji[confidence]} {network.upper()}: {token} - {wallet_count} wallets, {total_eth:.3f} ETH, α={alpha_score}"
                
                alert = Alert(
                    timestamp=datetime.now(),
                    network=network,
                    alert_type=alert_type,
                    token=token,
                    message=message,
                    data={
                        'wallet_count': wallet_count,
                        'total_eth_spent': total_eth,
                        'alpha_score': alpha_score,
                        'total_purchases': data.get('count', 0),
                        'platforms': list(data.get('platforms', [])),
                        'contract_address': data.get('contract_address', '') 
                    },
                    confidence=confidence
                )
                
                alerts.append(alert)
                
                print(f"🚨 ALERT: {message}")
        
        return alerts
    
    def _process_sell_results(self, network: str, results: Dict) -> List[Alert]:
        """Process sell results and generate alerts"""
        alerts = []
        ranked_tokens = results.get('ranked_tokens', [])
        
        for token, data, sell_score in ranked_tokens[:5]:  # Top 5 sell pressure tokens
            wallet_count = len(data.get('wallets', []))
            total_eth = data.get('total_estimated_eth', 0)
            
            # Check for significant sell pressure
            if (wallet_count >= self.alert_thresholds.get('min_sell_wallets', 2) and 
                total_eth >= self.alert_thresholds.get('min_sell_eth', 0.05) and
                sell_score >= self.alert_thresholds.get('min_sell_score', 5)):
                
                confidence = self._determine_sell_confidence(wallet_count, total_eth, sell_score)
                
                message = f"📉 🚨 {network.upper()}: {token} SELL PRESSURE - {wallet_count} wallets, {total_eth:.3f} ETH, score={sell_score}"
                
                alert = Alert(
                    timestamp=datetime.now(),
                    network=network,
                    alert_type='sell_pressure',
                    token=token,
                    message=message,
                    data={
                        'wallet_count': wallet_count,
                        'total_estimated_eth': total_eth,
                        'sell_score': sell_score,
                        'total_sells': data.get('count', 0),
                        'methods': list(data.get('methods', []))
                    },
                    confidence=confidence
                )
                
                alerts.append(alert)
                print(f"🚨 SELL ALERT: {message}")
        
        return alerts
    
    def test_telegram(self) -> Dict:
        """Test Telegram connection"""
        if not self.telegram.enabled:
            return {'success': False, 'message': 'Telegram not configured in settings'}
        
        test_message = f"🧪 *Test Alert*\n\nMonitor is working!\n🕐 {datetime.now().strftime('%H:%M:%S')}"
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram.bot_token}/sendMessage"
            payload = {
                'chat_id': self.telegram.chat_id,
                'text': test_message,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, json=payload, timeout=10)
            success = response.status_code == 200
            
            return {
                'success': success,
                'message': 'Test message sent!' if success else f'Error: {response.text}'
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def _determine_confidence(self, wallet_count: int, total_eth: float, alpha_score: float) -> str:
        """Determine confidence level for buy alerts"""
        if wallet_count >= 8 and total_eth >= 1.0 and alpha_score >= 50:
            return "HIGH"
        elif wallet_count >= 5 and total_eth >= 0.5 and alpha_score >= 25:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _determine_sell_confidence(self, wallet_count: int, total_eth: float, sell_score: float) -> str:
        """Determine confidence level for sell alerts"""
        if wallet_count >= 5 and total_eth >= 0.5 and sell_score >= 20:
            return "HIGH"
        elif wallet_count >= 3 and total_eth >= 0.2 and sell_score >= 10:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _process_alert(self, alert: Alert):
        """Process and send alerts through configured channels"""
        if self.notification_channels.get('console', True):
            # Console notification already handled
            pass
        
        if self.notification_channels.get('file', True):
            self._log_alert_to_file(alert)
        
        if self.notification_channels.get('telegram', False):
            success = self.telegram.send_alert(alert)
            if success:
                print(f"📱 Telegram alert sent for {alert.token}")
            else:
                print(f"❌ Failed to send Telegram alert for {alert.token}")
        
    def _log_alert_to_file(self, alert: Alert):
        """Log alert to file"""
        try:
            with open('monitor_alerts.log', 'a') as f:
                f.write(f"{alert.timestamp.isoformat()} - {alert.message}\n")
        except Exception as e:
            logger.error(f"Failed to log alert to file: {e}")
    
    def _send_webhook_alert(self, alert: Alert):
        """Send alert via webhook (placeholder)"""
        # Implementation would depend on webhook configuration
        pass
    
    def get_status(self) -> Dict:
        """Get monitor status with enhanced information"""
        return {
            'is_running': self.is_running,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'next_check': self.next_check.isoformat() if self.next_check else None,
            'config': self.config,
            'notification_channels': self.notification_channels,
            'alert_thresholds': self.alert_thresholds,
            'recent_alerts': [alert.to_dict() for alert in self.alerts[-10:]],
            'stats': {
                'total_alerts': self.total_alerts,
                'known_tokens': len(self.known_tokens),
                'seen_purchases': self.seen_purchases
            }
        }
    
    def save_config(self):
        """Save configuration (placeholder)"""
        # Implementation would save config to file/database
        logger.info("Monitor configuration saved")

# Create global monitor instance
monitor = EnhancedMonitor()

# Create Flask Blueprint for the monitor routes
monitor_bp = Blueprint('monitor', __name__)

@monitor_bp.route('/status', methods=['GET'])
def get_monitor_status():
    """Get monitor status"""
    try:
        status = monitor.get_status()
        return {'status': 'success', 'data': status}
    except Exception as e:
        logger.error(f"Error getting monitor status: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}, 500

@monitor_bp.route('/start', methods=['POST'])
def start_monitor():
    """Start the monitor"""
    try:
        result = monitor.start_monitoring()
        return result
    except Exception as e:
        logger.error(f"Error starting monitor: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}, 500

@monitor_bp.route('/stop', methods=['POST'])
def stop_monitor():
    """Stop the monitor"""
    try:
        result = monitor.stop_monitoring()
        return result
    except Exception as e:
        logger.error(f"Error stopping monitor: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}, 500

@monitor_bp.route('/check-now', methods=['POST'])
def check_now():
    """Trigger immediate check"""
    try:
        def run_check():
            monitor.check_for_new_tokens()
        
        thread = threading.Thread(target=run_check)
        thread.daemon = True
        thread.start()
        
        return {'status': 'success', 'message': 'Check initiated'}
    except Exception as e:
        logger.error(f"Error running immediate check: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}, 500
    
@monitor_bp.route('/telegram/test', methods=['POST'])
def test_telegram():
    """Test Telegram connection"""
    try:
        result = monitor.test_telegram()
        return result
    except Exception as e:
        logger.error(f"Error testing Telegram: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}, 500

# Export both the monitor instance and blueprint
__all__ = ['monitor', 'monitor_bp']