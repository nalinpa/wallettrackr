import schedule
import time
import threading
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
import json
import os
from typing import Dict, List, Set
import requests
from dataclasses import dataclass, asdict
from collections import defaultdict



monitor_bp = Blueprint('monitor', __name__)

@dataclass
class TokenAlert:
    """Enhanced data class for token alerts with trading links"""
    token: str
    wallet_count: int
    total_eth_spent: float
    platforms: List[str]
    contract_address: str
    first_seen: datetime
    alert_type: str
    alpha_score: float = 0.0
    network: str = 'base'
    
    def to_dict(self):
        # Generate trading links
        uniswap_url = f"https://app.uniswap.org/#/swap?outputCurrency={self.contract_address}&chain={self.network}"
        dexscreener_url = f"https://dexscreener.com/{self.network}/{self.contract_address}"
        
        return {
            **asdict(self),
            'first_seen': self.first_seen.isoformat(),
            'uniswap_url': uniswap_url,
            'dexscreener_url': dexscreener_url
        }
        
class TokenMonitor:
    """Automated monitoring system for smart wallet activity"""
    
    def __init__(self):
        self.is_running = False
        self.monitor_thread = None
        self.last_check = None  # Track actual last check time
        self.last_check_block = {}  # Track last block checked per network
        self.known_tokens = set()
        self.token_history = defaultdict(list)
        self.alerts = []
        self.config = self.load_config()
        self.scheduler_job = None
        
        # Track purchases to avoid duplicates
        self.seen_purchases = set()  # Set of (tx_hash, token) tuples
        
        # Notification settings
        self.notification_channels = {
            'console': True,
            'file': True,
            'webhook': False,
            'telegram': True,
            'discord': False
        }
        
        # Alert thresholds
        self.alert_thresholds = {
            'min_wallets': 2,  # Lower threshold for faster alerts
            'min_eth_spent': 0.5,  # Lower threshold for Base
            'surge_multiplier': 2.0,
            'min_alpha_score': 30.0  # Lower for Base
        }
    
    def load_config(self):
        """Load configuration from file or environment"""
        config_file = 'config/monitor_config.json'
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                return json.load(f)
        
        return {
            'check_interval_minutes': 60,
            'networks': ['base'],  # Default to Base only
            'analysis_types': ['buy'],
            'num_wallets': 50,  # Reduced for faster checks
            'use_interval_for_timeframe': True,  # New: use check interval for timeframe
            'save_history': True,
            'history_file': 'alerts/token_history.json',
            'alerts_file': 'alerts/alerts.json'
        }
    
    def save_config(self):
        """Save configuration to file"""
        os.makedirs('config', exist_ok=True)
        with open('config/monitor_config.json', 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def calculate_time_window(self):
        """Calculate how far back to check based on interval"""
        if self.config.get('use_interval_for_timeframe', True) and self.last_check:
            # Calculate hours since last check
            time_diff = datetime.now() - self.last_check
            hours_back = max(time_diff.total_seconds() / 3600, 0.5)  # At least 30 minutes
            
            # Convert to days for the API (partial days supported)
            days_back = hours_back / 24
            
            print(f"⏰ Checking {hours_back:.1f} hours back (since last check)")
            return days_back
        else:
            # Use configured interval
            interval_minutes = self.config['check_interval_minutes']
            hours_back = (interval_minutes / 60) * 1.5  # Add 50% buffer
            days_back = hours_back / 24
            
            print(f"⏰ Checking {hours_back:.1f} hours back (based on interval)")
            return days_back
    
    def start_monitoring(self):
        """Start the automated monitoring"""
        if self.is_running:
            return {'status': 'error', 'message': 'Monitor already running'}
        
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        return {'status': 'success', 'message': 'Monitor started'}
    
    def stop_monitoring(self):
        """Stop the automated monitoring"""
        if not self.is_running:
            return {'status': 'error', 'message': 'Monitor not running'}
        
        self.is_running = False
        if self.scheduler_job:
            schedule.cancel_job(self.scheduler_job)
        
        return {'status': 'success', 'message': 'Monitor stopped'}
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        # Schedule the check
        interval = self.config['check_interval_minutes']
        self.scheduler_job = schedule.every(interval).minutes.do(self.check_for_new_tokens)
        
        # Run first check immediately
        self.check_for_new_tokens()
        
        while self.is_running:
            schedule.run_pending()
            time.sleep(30)  # Check schedule every 30 seconds
    
    def check_for_new_tokens(self):
        """Check for new token purchases"""
        print(f"\n{'='*60}")
        print(f"🔍 AUTOMATED TOKEN MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        
        all_alerts = []
        
        # Calculate time window
        days_back = self.calculate_time_window()
        
        for network in self.config['networks']:
            for analysis_type in self.config['analysis_types']:
                alerts = self._analyze_network(network, analysis_type, days_back)
                all_alerts.extend(alerts)
        
        # Process and send alerts
        if all_alerts:
            self._process_alerts(all_alerts)
        else:
            print("✅ No new significant token activity detected")
        
        # Update last check time AFTER successful check
        self.last_check = datetime.now()
        
        # Calculate next check time
        next_check = self.last_check + timedelta(minutes=self.config['check_interval_minutes'])
        print(f"⏰ Next check at {next_check.strftime('%H:%M:%S')}")
    
    def _analyze_network(self, network: str, analysis_type: str, days_back: float) -> List[TokenAlert]:
        """Analyze a specific network for new tokens"""
        print(f"\n📊 Checking {network.upper()} {analysis_type} activity...")
        print(f"   Time window: {days_back*24:.1f} hours")
        print(f"   Wallets to check: {self.config['num_wallets']}")
        
        try:
            # Import and run the appropriate analyzer
            if network == 'eth' and analysis_type == 'buy':
                from buy_tracker import EthComprehensiveTracker
                analyzer = EthComprehensiveTracker()
                results = analyzer.analyze_all_trading_methods(
                    num_wallets=self.config['num_wallets'],
                    days_back=days_back  # Use calculated days_back
                )
            elif network == 'base' and analysis_type == 'buy':
                from base_buy_tracker import BaseComprehensiveTracker
                analyzer = BaseComprehensiveTracker()
                results = analyzer.analyze_all_trading_methods(
                    num_wallets=self.config['num_wallets'],
                    days_back=days_back  # Use calculated days_back
                )
            else:
                print(f"   ⚠️ Unsupported: {network} {analysis_type}")
                return []
            
            # Process results for alerts
            return self._extract_alerts(results, network)
            
        except Exception as e:
            print(f"❌ Error analyzing {network}: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _extract_alerts(self, results: Dict, network: str) -> List[TokenAlert]:
        """Extract alert-worthy tokens from results - DEBUG VERSION"""
        alerts = []
        
        if not results:
            print("   ❌ No results returned from analysis")
            return alerts
        
        if not results.get('ranked_tokens'):
            print("   ❌ No ranked tokens in results")
            return alerts
        
        print(f"\n   📊 ALERT DETECTION DEBUG:")
        print(f"   Thresholds: min_wallets={self.alert_thresholds['min_wallets']}, "
            f"min_eth={self.alert_thresholds['min_eth_spent']}, "
            f"min_score={self.alert_thresholds['min_alpha_score']}")
        
        # Get current token set for this network
        network_key = f"{network}_tokens"
        
        previous_tokens = self.known_tokens.copy() if self.known_tokens else set()
        current_tokens = set()
        new_purchases_found = 0
        
        # Check all purchases for truly new activity
        all_purchases = results.get('all_purchases', [])
        print(f"   Total purchases found: {len(all_purchases)}")
        
        for purchase in all_purchases:
            tx_hash = purchase.get('transaction_hash', '')
            token = purchase.get('token_bought', '')
            
            # Create unique identifier for this purchase
            purchase_id = (tx_hash, token)
            
            # Check if this is a new purchase we haven't seen
            if purchase_id not in self.seen_purchases:
                self.seen_purchases.add(purchase_id)
                new_purchases_found += 1
        
        print(f"   🆕 Found {new_purchases_found} new purchases since last check")
        print(f"   Previously known tokens: {len(previous_tokens)}")
        print(f"   Analyzing top {min(20, len(results['ranked_tokens']))} tokens...")
        
        # Process top tokens for alerts
        tokens_checked = 0
        tokens_meeting_criteria = 0
        
        for token, data, alpha_score in results['ranked_tokens'][:20]:  # Top 20 tokens
            current_tokens.add(token)
            tokens_checked += 1
            
            wallet_count = len(data.get('wallets', []))
            eth_spent = data.get('total_eth_spent', 0)
            platforms = list(data.get('platforms', []))
            
            # Debug output for each token
            print(f"\n   Token #{tokens_checked}: {token}")
            print(f"      Wallets: {wallet_count} (need >= {self.alert_thresholds['min_wallets']})")
            print(f"      ETH: {eth_spent:.4f} (need >= {self.alert_thresholds['min_eth_spent']})")
            print(f"      Score: {alpha_score:.1f} (need >= {self.alert_thresholds['min_alpha_score']})")
            print(f"      Is new? {token not in previous_tokens}")
            
            # Get contract address
            contract_address = 'N/A'
            if 'purchases' in data and data['purchases']:
                contract_address = data['purchases'][0].get('contract_address', 'N/A')
            
            # Count new purchases for this token
            token_new_purchases = 0
            for purchase in data.get('purchases', []):
                tx_hash = purchase.get('transaction_hash', '')
                purchase_id = (tx_hash, token)
                if purchase_id in self.seen_purchases:
                    token_new_purchases += 1
            
            print(f"      New purchases for this token: {token_new_purchases}")
            
            # Check if token meets alert criteria
            meets_wallets = wallet_count >= self.alert_thresholds['min_wallets']
            meets_eth = eth_spent >= self.alert_thresholds['min_eth_spent']
            meets_score = alpha_score >= self.alert_thresholds['min_alpha_score']
            
            meets_criteria = meets_wallets and meets_eth and meets_score
            
            print(f"      Meets criteria? {meets_criteria} (W:{meets_wallets} E:{meets_eth} S:{meets_score})")
            
            if not meets_criteria:
                print(f"      ❌ Skipping - doesn't meet criteria")
                continue
            
            tokens_meeting_criteria += 1
            
            # Alert if it's a new token OR has significant new activity
            should_alert = False
            alert_reason = ""
            
            if token not in previous_tokens:
                should_alert = True
                alert_reason = "NEW TOKEN"
                alert_type = 'new'
            elif token_new_purchases >= 2:
                should_alert = True
                alert_reason = f"SURGE ({token_new_purchases} new purchases)"
                alert_type = 'surge'
            else:
                print(f"      ❌ Skipping - not new and insufficient new activity")
                continue
            
            if should_alert:
                print(f"      ✅ CREATING ALERT: {alert_reason}")
                
                alert = TokenAlert(
                    token=token,
                    wallet_count=wallet_count,
                    total_eth_spent=eth_spent,
                    platforms=platforms,
                    contract_address=contract_address,
                    first_seen=datetime.now(),
                    alert_type=alert_type,
                    alpha_score=alpha_score,
                    network=network
                )
                alerts.append(alert)
                
                print(f"   🚨 ALERT CREATED: {token} - {alert_type.upper()} - {wallet_count} wallets, {eth_spent:.3f} ETH")
            
            # Update history
            self.token_history[token].append({
                'timestamp': datetime.now().isoformat(),
                'wallet_count': wallet_count,
                'eth_spent': eth_spent,
                'alpha_score': alpha_score,
                'network': network
            })
        
        # Update known tokens
        self.known_tokens = current_tokens
        
        print(f"\n   📊 ALERT SUMMARY:")
        print(f"   Tokens checked: {tokens_checked}")
        print(f"   Tokens meeting criteria: {tokens_meeting_criteria}")
        print(f"   Alerts generated: {len(alerts)}")
        print(f"   Known tokens now: {len(self.known_tokens)}")
        
        # Clean up old purchases (keep last 1000)
        if len(self.seen_purchases) > 1000:
            self.seen_purchases = set(list(self.seen_purchases)[-1000:])
        
        return alerts
      
    
    def _process_alerts(self, alerts: List[TokenAlert]):
        """Process and send alerts through configured channels"""
        # Group alerts by type
        new_tokens = [a for a in alerts if a.alert_type == 'new']
        surge_tokens = [a for a in alerts if a.alert_type == 'surge']
        
        # Console notification
        if self.notification_channels['console']:
            self._console_notification(new_tokens, surge_tokens)
        
        # File notification
        if self.notification_channels['file']:
            self._file_notification(alerts)
        
        # Webhook notification
        if self.notification_channels['webhook']:
            self._webhook_notification(alerts)
        
        # Telegram notification
        if self.notification_channels['telegram']:
            self._telegram_notification(new_tokens, surge_tokens)
        
        # Discord notification
        if self.notification_channels['discord']:
            self._discord_notification(new_tokens, surge_tokens)
        
        # Store alerts
        self.alerts.extend(alerts)
        self._save_alerts()
    
    def _console_notification(self, new_tokens: List[TokenAlert], surge_tokens: List[TokenAlert]):
        """Print alerts to console"""
        if new_tokens:
            print(f"\n🚨 NEW TOKENS DETECTED ({len(new_tokens)}):")
            for alert in new_tokens:
                print(f"  🆕 {alert.token} ({alert.network.upper()})")
                print(f"     💰 {alert.total_eth_spent:.4f} ETH from {alert.wallet_count} wallets")
                print(f"     📊 Alpha Score: {alert.alpha_score:.1f}")
                print(f"     🔗 Contract: {alert.contract_address}")
                print(f"     🏪 Platforms: {', '.join(alert.platforms[:3])}")
        
        if surge_tokens:
            print(f"\n⚡ SURGE IN ACTIVITY ({len(surge_tokens)}):")
            for alert in surge_tokens:
                print(f"  📈 {alert.token} ({alert.network.upper()})")
                print(f"     💰 {alert.total_eth_spent:.4f} ETH from {alert.wallet_count} wallets")
                print(f"     📊 Alpha Score: {alert.alpha_score:.1f}")
    
    def _file_notification(self, alerts: List[TokenAlert]):
        """Save alerts to file"""
        os.makedirs('alerts', exist_ok=True)
        filename = f"alerts/alerts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump([alert.to_dict() for alert in alerts], f, indent=2)
        print(f"📁 Alerts saved to {filename}")
    
    def _webhook_notification(self, alerts: List[TokenAlert]):
        """Send alerts to webhook"""
        webhook_url = os.getenv('MONITOR_WEBHOOK_URL')
        if not webhook_url:
            return
        
        try:
            payload = {
                'timestamp': datetime.now().isoformat(),
                'alerts': [alert.to_dict() for alert in alerts]
            }
            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code == 200:
                print(f"📤 Webhook notification sent")
        except Exception as e:
            print(f"❌ Webhook error: {e}")
    
    def _telegram_notification(self, new_tokens: List[TokenAlert], surge_tokens: List[TokenAlert]):
        """Send alerts to Telegram"""
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        if not bot_token or not chat_id:
            return
        
        message = "🚨 *BASE ALPHA ALERT*\n\n"
        
        if new_tokens:
            message += f"*NEW TOKENS ({len(new_tokens)}):*\n"
            for alert in new_tokens[:5]:  # Top 5
                message += f"• {alert.token} - {alert.total_eth_spent:.2f}Ξ - Score: {alert.alpha_score:.0f}\n"
                message += f"  CA: `{alert.contract_address}`\n"
        
        if surge_tokens:
            message += f"\n*SURGE ACTIVITY ({len(surge_tokens)}):*\n"
            for alert in surge_tokens[:5]:  # Top 5
                message += f"• {alert.token} - {alert.total_eth_spent:.2f}Ξ - Score: {alert.alpha_score:.0f}\n"
        
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                print(f"📱 Telegram notification sent")
        except Exception as e:
            print(f"❌ Telegram error: {e}")
    
    def _discord_notification(self, new_tokens: List[TokenAlert], surge_tokens: List[TokenAlert]):
        """Send alerts to Discord"""
        webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
        
        if not webhook_url:
            return
        
        embeds = []
        
        if new_tokens:
            for alert in new_tokens[:3]:  # Limit to 3 to avoid Discord limits
                embed = {
                    'title': f'🆕 New Token: {alert.token}',
                    'color': 0x00ff00,
                    'fields': [
                        {'name': '💰 ETH Spent', 'value': f'{alert.total_eth_spent:.3f} ETH', 'inline': True},
                        {'name': '👥 Wallets', 'value': str(alert.wallet_count), 'inline': True},
                        {'name': '📊 Score', 'value': f'{alert.alpha_score:.0f}', 'inline': True},
                        {'name': '🔗 Contract', 'value': f'```{alert.contract_address}```', 'inline': False},
                        {'name': '🏪 Platforms', 'value': ', '.join(alert.platforms[:3]), 'inline': False}
                    ],
                    'timestamp': datetime.now().isoformat(),
                    'footer': {'text': f'Network: {alert.network.upper()}'}
                }
                embeds.append(embed)
        
        if embeds:
            try:
                payload = {'embeds': embeds}
                response = requests.post(webhook_url, json=payload, timeout=10)
                if response.status_code == 204:
                    print(f"💬 Discord notification sent")
            except Exception as e:
                print(f"❌ Discord error: {e}")
    
    def _save_alerts(self):
        """Save alerts history"""
        if self.config.get('save_history'):
            os.makedirs('alerts', exist_ok=True)
            with open(self.config['alerts_file'], 'w') as f:
                json.dump([alert.to_dict() for alert in self.alerts[-100:]], f, indent=2)  # Keep last 100
    
    def get_status(self):
        """Get current monitor status"""
        next_check = None
        if self.last_check and self.is_running:
            next_check = self.last_check + timedelta(minutes=self.config['check_interval_minutes'])
        
        return {
            'is_running': self.is_running,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'next_check': next_check.isoformat() if next_check else None,
            'config': self.config,
            'notification_channels': self.notification_channels,
            'alert_thresholds': self.alert_thresholds,
            'recent_alerts': [alert.to_dict() for alert in self.alerts[-10:]],  # Last 10 alerts
            'stats': {
                'total_alerts': len(self.alerts),
                'known_tokens': len(self.known_tokens),
                'seen_purchases': len(self.seen_purchases)
            }
        }

# Global monitor instance
monitor = TokenMonitor()

if __name__ == "__main__":
    # Test the monitor directly
    print("Testing monitor...")
    monitor.config['num_wallets'] = 10  # Quick test
    monitor.check_for_new_tokens()