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
import logging

# Import settings
from config.settings import settings, monitor_config, analysis_config, telegram_config

monitor_bp = Blueprint('monitor', __name__)

# Configure logger
logger = logging.getLogger(__name__)

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
        # Generate trading links based on network
        links = self._generate_trading_links()
        
        return {
            **asdict(self),
            'first_seen': self.first_seen.isoformat(),
            **links
        }
    
    def _generate_trading_links(self):
        """Generate network-specific trading links for Base and Ethereum only"""
        # Network-specific chain IDs and names (Base and Ethereum only)
        chain_info = {
            'base': {'chain_id': 'base', 'chain_name': 'Base', 'uniswap_chain': 'base'},
            'ethereum': {'chain_id': 'ethereum', 'chain_name': 'Ethereum', 'uniswap_chain': 'mainnet'},
            'eth': {'chain_id': 'ethereum', 'chain_name': 'Ethereum', 'uniswap_chain': 'mainnet'}
        }
        
        network_lower = self.network.lower()
        info = chain_info.get(network_lower, chain_info['base'])  # Default to base
        
        # Uniswap URL
        uniswap_url = f"https://app.uniswap.org/#/swap?outputCurrency={self.contract_address}&chain={info['uniswap_chain']}"
        
        # DexScreener URL
        dexscreener_url = f"https://dexscreener.com/{info['chain_id']}/{self.contract_address}"
        
        # Additional useful links
        additional_links = {
            'uniswap_url': uniswap_url,
            'dexscreener_url': dexscreener_url,
            'trading_links': {
                'uniswap': uniswap_url,
                'dexscreener': dexscreener_url
            }
        }
        
        # Add network-specific explorer links
        if network_lower == 'base':
            additional_links['explorer_url'] = f"https://basescan.org/token/{self.contract_address}"
            additional_links['trading_links']['basescan'] = additional_links['explorer_url']
        elif network_lower in ['ethereum', 'eth']:
            additional_links['explorer_url'] = f"https://etherscan.io/token/{self.contract_address}"
            additional_links['trading_links']['etherscan'] = additional_links['explorer_url']
        
        return additional_links
    
    def get_uniswap_link(self):
        """Get Uniswap trading link"""
        return self._generate_trading_links()['uniswap_url']
    
    def get_dexscreener_link(self):
        """Get DexScreener link"""
        return self._generate_trading_links()['dexscreener_url']
    
    def get_all_links(self):
        """Get all trading links as formatted text"""
        links = self._generate_trading_links()
        return {
            'uniswap': links['uniswap_url'],
            'dexscreener': links['dexscreener_url'],
            'explorer': links.get('explorer_url', '')
        }

def should_exclude_token(token_symbol):
    """Check if token should be excluded based on settings"""
    return token_symbol.upper() in [t.upper() for t in analysis_config.excluded_tokens]

class TokenMonitor:
    """Automated monitoring system for smart wallet activity"""
    
    def __init__(self):
        self.is_running = False
        self.monitor_thread = None
        self.last_check = None
        self.last_check_block = {}
        self.known_tokens = set()
        self.token_history = defaultdict(list)
        self.alerts = []
        self.config = self.load_config()
        self.scheduler_job = None
        
        # Track purchases to avoid duplicates
        self.seen_purchases = set()
        
        # Load notification settings from config
        self.notification_channels = {
            'console': True,
            'telegram': telegram_config.enabled,
            'file': True,
            'webhook': False
        }
        
        # Load alert thresholds from settings
        self.alert_thresholds = monitor_config.alert_thresholds.copy()
        
        logger.info(f"TokenMonitor initialized with settings:")
        logger.info(f"  - Default interval: {monitor_config.default_check_interval_minutes} minutes")
        logger.info(f"  - Supported networks: {[net.value for net in monitor_config.supported_networks]}")
        logger.info(f"  - Alert thresholds: {self.alert_thresholds}")
        logger.info(f"  - Telegram enabled: {telegram_config.enabled}")
        logger.info(f"  - Excluded tokens: {len(analysis_config.excluded_tokens)}")
    
    def load_config(self):
        """Load configuration from file or use settings defaults"""
        config_file = 'config/monitor_config.json'
        
        # Default config from settings
        default_config = {
            'check_interval_minutes': monitor_config.default_check_interval_minutes,
            'networks': [net.value for net in monitor_config.default_networks],
            'analysis_types': ['buy'],
            'num_wallets': analysis_config.default_wallet_count,
            'use_interval_for_timeframe': True,
            'save_history': True,
            'history_file': 'alerts/token_history.json'
        }
        
        # Load from file if it exists, otherwise use defaults
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    file_config = json.load(f)
                    # Merge with defaults, ensuring all required keys exist
                    config = {**default_config, **file_config}
                    
                    # Validate against settings limits
                    config['check_interval_minutes'] = max(
                        config['check_interval_minutes'], 
                        monitor_config.min_check_interval_minutes
                    )
                    config['check_interval_minutes'] = min(
                        config['check_interval_minutes'], 
                        monitor_config.max_check_interval_minutes
                    )
                    
                    config['num_wallets'] = min(
                        config['num_wallets'], 
                        analysis_config.max_wallet_count
                    )
                    
                    # Ensure networks are supported
                    supported_networks = [net.value for net in monitor_config.supported_networks]
                    config['networks'] = [
                        net for net in config['networks'] 
                        if net in supported_networks
                    ]
                    
                    if not config['networks']:
                        config['networks'] = [monitor_config.default_networks[0].value]
                    
                    logger.info(f"Loaded monitor config from file (validated against settings)")
                    return config
                    
            except Exception as e:
                logger.warning(f"Failed to load config file: {e}, using defaults")
        
        logger.info(f"Using default monitor config from settings")
        return default_config
    
    def save_config(self):
        """Save configuration to file"""
        try:
            os.makedirs('config', exist_ok=True)
            
            # Validate config before saving
            validated_config = self.config.copy()
            
            # Apply settings limits
            validated_config['check_interval_minutes'] = max(
                min(validated_config['check_interval_minutes'], monitor_config.max_check_interval_minutes),
                monitor_config.min_check_interval_minutes
            )
            
            validated_config['num_wallets'] = min(
                validated_config['num_wallets'], 
                analysis_config.max_wallet_count
            )
            
            with open('config/monitor_config.json', 'w') as f:
                json.dump(validated_config, f, indent=2)
                
            logger.info("Monitor config saved successfully")
            
        except Exception as e:
            logger.error(f"Failed to save monitor config: {e}")
    
    def calculate_time_window(self):
        """Calculate how far back to check based on interval and settings"""
        if self.config.get('use_interval_for_timeframe', True) and self.last_check:
            # Calculate hours since last check
            time_diff = datetime.now() - self.last_check
            hours_back = max(time_diff.total_seconds() / 3600, 0.5)  # At least 30 minutes
            
            # Convert to days for the API (partial days supported)
            days_back = hours_back / 24
            
            # Ensure we don't exceed max_days_back from settings
            days_back = min(days_back, analysis_config.max_days_back)
            
            print(f"⏰ Checking {hours_back:.1f} hours back (since last check, max {analysis_config.max_days_back} days)")
            return days_back
        else:
            # Use configured interval
            interval_minutes = self.config['check_interval_minutes']
            hours_back = (interval_minutes / 60) * 1.5  # Add 50% buffer
            days_back = min(hours_back / 24, analysis_config.max_days_back)
            
            print(f"⏰ Checking {hours_back:.1f} hours back (based on interval, max {analysis_config.max_days_back} days)")
            return days_back
    
    def start_monitoring(self):
        """Start the automated monitoring"""
        if self.is_running:
            return {'status': 'error', 'message': 'Monitor already running'}
        
        # Validate configuration before starting
        if not self.config['networks']:
            return {'status': 'error', 'message': 'No supported networks configured'}
        
        if self.config['check_interval_minutes'] < monitor_config.min_check_interval_minutes:
            return {
                'status': 'error', 
                'message': f'Check interval must be at least {monitor_config.min_check_interval_minutes} minutes'
            }
        
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        logger.info(f"Monitor started with {self.config['check_interval_minutes']} minute intervals")
        return {'status': 'success', 'message': 'Monitor started', 'config': self.config}
    
    def stop_monitoring(self):
        """Stop the automated monitoring"""
        if not self.is_running:
            return {'status': 'error', 'message': 'Monitor not running'}
        
        self.is_running = False
        if self.scheduler_job:
            schedule.cancel_job(self.scheduler_job)
        
        logger.info("Monitor stopped")
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
        print(f"Environment: {settings.environment} | Networks: {self.config['networks']}")
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
        
        # Log statistics
        logger.info(f"Monitor check completed: {len(all_alerts)} alerts, {len(self.known_tokens)} known tokens")
    
    def _analyze_network(self, network: str, analysis_type: str, days_back: float) -> List[TokenAlert]:
        """Analyze a specific network for new tokens"""
        print(f"\n📊 Checking {network.upper()} {analysis_type} activity...")
        print(f"   Time window: {days_back*24:.1f} hours")
        print(f"   Wallets to check: {self.config['num_wallets']}")
        print(f"   Excluded tokens: {len(analysis_config.excluded_tokens)}")
        
        try:
            # Get network configuration
            try:
                network_config = settings.get_network_config(network)
                min_eth_value = network_config['min_eth_value']
                print(f"   Min ETH value: {min_eth_value}")
            except ValueError as e:
                print(f"   ⚠️ Network config error: {e}")
                return []
            
            # Import and run the appropriate analyzer
            if network == 'eth' and analysis_type == 'buy':
                from tracker.buy_tracker import EthComprehensiveTracker
                analyzer = EthComprehensiveTracker()
                results = analyzer.analyze_all_trading_methods(
                    num_wallets=self.config['num_wallets'],
                    days_back=days_back
                )
            elif network == 'base' and analysis_type == 'buy':
                from tracker.base_buy_tracker import BaseComprehensiveTracker
                analyzer = BaseComprehensiveTracker()
                results = analyzer.analyze_all_trading_methods(
                    num_wallets=self.config['num_wallets'],
                    days_back=days_back
                )
            else:
                print(f"   ⚠️ Unsupported: {network} {analysis_type}")
                return []
            
            # Process results for alerts
            return self._extract_alerts(results, network)
            
        except Exception as e:
            logger.error(f"Error analyzing {network}: {e}", exc_info=True)
            print(f"❌ Error analyzing {network}: {e}")
            return []
    
    def _extract_alerts(self, results: Dict, network: str) -> List[TokenAlert]:
        """Extract alert-worthy tokens from results with settings integration"""
        alerts = []
        
        if not results:
            print("   ❌ No results returned from analysis")
            return alerts
        
        if not results.get('ranked_tokens'):
            print("   ❌ No ranked tokens in results")
            return alerts
        
        print(f"\n   📊 ALERT DETECTION (using settings thresholds):")
        print(f"   Thresholds: min_wallets={self.alert_thresholds['min_wallets']}, "
            f"min_eth={self.alert_thresholds['min_eth_spent']}, "
            f"min_score={self.alert_thresholds['min_alpha_score']}")
        
        # Get current token set for this network
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
        excluded_count = 0
        
        for token, data, alpha_score in results['ranked_tokens'][:20]:  # Top 20 tokens
            current_tokens.add(token)
            tokens_checked += 1
            
            # Check if token is excluded by settings
            if should_exclude_token(token):
                excluded_count += 1
                print(f"\n   Token #{tokens_checked}: {token} - EXCLUDED (in settings)")
                continue
            
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
            
            # Check if token meets alert criteria (from settings)
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
            elif token_new_purchases >= self.alert_thresholds.get('surge_multiplier', 2.0):
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
                
                logger.info(f"Alert created: {token} - {alert_type} - {wallet_count} wallets, {eth_spent:.3f} ETH")
            
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
        print(f"   Tokens excluded by settings: {excluded_count}")
        print(f"   Tokens meeting criteria: {tokens_meeting_criteria}")
        print(f"   Alerts generated: {len(alerts)}")
        print(f"   Known tokens now: {len(self.known_tokens)}")
        
        # Clean up old purchases (keep last 1000)
        if len(self.seen_purchases) > 1000:
            self.seen_purchases = set(list(self.seen_purchases)[-1000:])
        
        return alerts
    
    def _process_alerts(self, alerts: List[TokenAlert]):
        """Process and send alerts through configured channels"""
        if not alerts:
            return
            
        # Limit alerts per notification based on settings
        max_alerts = monitor_config.max_alerts_per_notification
        if len(alerts) > max_alerts:
            print(f"⚠️ Too many alerts ({len(alerts)}), showing top {max_alerts}")
            alerts = alerts[:max_alerts]
        
        # Group alerts by type
        new_tokens = [a for a in alerts if a.alert_type == 'new']
        surge_tokens = [a for a in alerts if a.alert_type == 'surge']
        
        # Console notification
        if self.notification_channels['console']:
            self._console_notification(new_tokens, surge_tokens)
            
        # Telegram notification
        if self.notification_channels['telegram'] and telegram_config.enabled:
            self._telegram_notification(new_tokens, surge_tokens)
        
        # File notification
        if self.notification_channels.get('file', False):
            self._file_notification(alerts)
        
        # Store alerts in memory (limit based on settings)
        self.alerts.extend(alerts)
        max_stored = monitor_config.max_stored_alerts
        if len(self.alerts) > max_stored:
            self.alerts = self.alerts[-max_stored:]
            
        logger.info(f"Processed {len(alerts)} alerts through {sum(self.notification_channels.values())} channels")
    
    def _console_notification(self, new_tokens: List[TokenAlert], surge_tokens: List[TokenAlert]):
        """Print alerts to console with trading links"""
        if new_tokens:
            print(f"\n🚨 NEW TOKENS DETECTED ({len(new_tokens)}):")
            for alert in new_tokens:
                print(f"  🆕 {alert.token} ({alert.network.upper()})")
                print(f"     💰 {alert.total_eth_spent:.4f} ETH from {alert.wallet_count} wallets")
                print(f"     📊 Alpha Score: {alert.alpha_score:.1f}")
                print(f"     🔗 Contract: {alert.contract_address}")
                print(f"     🏪 Platforms: {', '.join(alert.platforms[:3])}")
                print(f"     🦄 Uniswap: {alert.get_uniswap_link()}")
                print(f"     📈 DexScreener: {alert.get_dexscreener_link()}")
        
        if surge_tokens:
            print(f"\n⚡ SURGE IN ACTIVITY ({len(surge_tokens)}):")
            for alert in surge_tokens:
                print(f"  📈 {alert.token} ({alert.network.upper()})")
                print(f"     💰 {alert.total_eth_spent:.4f} ETH from {alert.wallet_count} wallets")
                print(f"     📊 Alpha Score: {alert.alpha_score:.1f}")
                print(f"     🦄 Uniswap: {alert.get_uniswap_link()}")
                print(f"     📈 DexScreener: {alert.get_dexscreener_link()}")
    
    def _telegram_notification(self, new_tokens: List[TokenAlert], surge_tokens: List[TokenAlert]):
        """Send alerts to Telegram with clickable links using settings"""
        if not telegram_config.bot_token or not telegram_config.chat_id:
            logger.warning("Telegram credentials not configured in settings")
            return
        
        if not new_tokens and not surge_tokens:
            return
        
        try:
            # Build message with proper links
            network_emoji = "🔵" if new_tokens and new_tokens[0].network == 'base' else "⚡"
            network_name = new_tokens[0].network.upper() if new_tokens else surge_tokens[0].network.upper()
            
            message = f"{network_emoji} *{network_name} ALPHA ALERT*\n"
            message += f"Environment: {settings.environment.upper()}\n\n"
            
            if new_tokens:
                message += f"*🆕 NEW TOKENS ({len(new_tokens)}):*\n"
                for alert in new_tokens[:5]:  # Top 5
                    message += f"• *{alert.token}* - {alert.total_eth_spent:.2f}Ξ - Score: {alert.alpha_score:.0f}\n"
                    message += f"  📋 `{alert.contract_address}`\n"
                    message += f"  🦄 [Trade on Uniswap]({alert.get_uniswap_link()})\n"
                    message += f"  📈 [View on DexScreener]({alert.get_dexscreener_link()})\n\n"
            
            if surge_tokens:
                message += f"*⚡ SURGE ACTIVITY ({len(surge_tokens)}):*\n"
                for alert in surge_tokens[:5]:  # Top 5
                    message += f"• *{alert.token}* - {alert.total_eth_spent:.2f}Ξ - Score: {alert.alpha_score:.0f}\n"
                    message += f"  🦄 [Trade on Uniswap]({alert.get_uniswap_link()})\n"
                    message += f"  📈 [View on DexScreener]({alert.get_dexscreener_link()})\n\n"
            
            # Truncate message if too long
            if len(message) > telegram_config.max_message_length:
                message = message[:telegram_config.max_message_length-50] + "\n...(truncated)"
            
            url = f"https://api.telegram.org/bot{telegram_config.bot_token}/sendMessage"
            payload = {
                'chat_id': telegram_config.chat_id,
                'text': message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': False
            }
            
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                print(f"📱 Telegram notification sent successfully")
                logger.info("Telegram notification sent successfully")
            else:
                logger.error(f"Telegram error: Status {response.status_code}, Response: {response.text}")
                print(f"❌ Telegram error: Status {response.status_code}")
                
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}", exc_info=True)
            print(f"❌ Telegram error: {e}")
    
    def _file_notification(self, alerts: List[TokenAlert]):
        """Save alerts to file"""
        try:
            os.makedirs('alerts', exist_ok=True)
            alert_file = f"alerts/alerts_{datetime.now().strftime('%Y%m%d')}.json"
            
            # Load existing alerts for today
            existing_alerts = []
            if os.path.exists(alert_file):
                with open(alert_file, 'r') as f:
                    existing_alerts = json.load(f)
            
            # Add new alerts
            for alert in alerts:
                existing_alerts.append(alert.to_dict())
            
            # Save back to file
            with open(alert_file, 'w') as f:
                json.dump(existing_alerts, f, indent=2, default=str)
                
            logger.info(f"Saved {len(alerts)} alerts to {alert_file}")
            
        except Exception as e:
            logger.error(f"Failed to save alerts to file: {e}")
    
    def get_status(self):
        """Get current monitor status with settings info"""
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
            },
            'settings_info': {
                'environment': settings.environment,
                'supported_networks': [net.value for net in monitor_config.supported_networks],
                'excluded_tokens_count': len(analysis_config.excluded_tokens),
                'telegram_enabled': telegram_config.enabled,
                'max_alerts_per_notification': monitor_config.max_alerts_per_notification,
                'max_stored_alerts': monitor_config.max_stored_alerts
            }
        }
    
    def update_config(self, new_config: dict):
        """Update configuration with validation against settings"""
        try:
            # Validate interval
            if 'check_interval_minutes' in new_config:
                interval = new_config['check_interval_minutes']
                if interval < monitor_config.min_check_interval_minutes:
                    raise ValueError(f'Interval cannot be less than {monitor_config.min_check_interval_minutes} minutes')
                if interval > monitor_config.max_check_interval_minutes:
                    raise ValueError(f'Interval cannot exceed {monitor_config.max_check_interval_minutes} minutes')
            
            # Validate wallet count
            if 'num_wallets' in new_config:
                wallets = new_config['num_wallets']
                if wallets > analysis_config.max_wallet_count:
                    raise ValueError(f'Wallet count cannot exceed {analysis_config.max_wallet_count}')
                if wallets < 1:
                    raise ValueError('Wallet count must be at least 1')
            
            # Validate networks
            if 'networks' in new_config:
                supported_networks = [net.value for net in monitor_config.supported_networks]
                invalid_networks = [net for net in new_config['networks'] if net not in supported_networks]
                if invalid_networks:
                    raise ValueError(f'Unsupported networks: {invalid_networks}. Supported: {supported_networks}')
                if not new_config['networks']:
                    raise ValueError('At least one network must be specified')
            
            # Update config
            old_interval = self.config.get('check_interval_minutes')
            self.config.update(new_config)
            
            # If interval changed and monitor is running, restart scheduler
            new_interval = self.config.get('check_interval_minutes')
            if self.is_running and old_interval != new_interval:
                if self.scheduler_job:
                    schedule.cancel_job(self.scheduler_job)
                self.scheduler_job = schedule.every(new_interval).minutes.do(self.check_for_new_tokens)
                logger.info(f"Updated monitor interval to {new_interval} minutes")
            
            # Save to file
            self.save_config()
            
            logger.info(f"Monitor config updated: {new_config}")
            return {'status': 'success', 'config': self.config}
            
        except Exception as e:
            logger.error(f"Failed to update monitor config: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def update_alert_thresholds(self, new_thresholds: dict):
        """Update alert thresholds with validation"""
        try:
            # Validate threshold values
            if 'min_wallets' in new_thresholds:
                if new_thresholds['min_wallets'] < 1:
                    raise ValueError('min_wallets must be at least 1')
            
            if 'min_eth_spent' in new_thresholds:
                if new_thresholds['min_eth_spent'] < 0:
                    raise ValueError('min_eth_spent cannot be negative')
            
            if 'min_alpha_score' in new_thresholds:
                if new_thresholds['min_alpha_score'] < 0:
                    raise ValueError('min_alpha_score cannot be negative')
            
            if 'surge_multiplier' in new_thresholds:
                if new_thresholds['surge_multiplier'] < 1:
                    raise ValueError('surge_multiplier must be at least 1')
            
            # Update thresholds
            self.alert_thresholds.update(new_thresholds)
            
            logger.info(f"Alert thresholds updated: {new_thresholds}")
            return {'status': 'success', 'thresholds': self.alert_thresholds}
            
        except Exception as e:
            logger.error(f"Failed to update alert thresholds: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def update_notification_channels(self, new_channels: dict):
        """Update notification channel settings"""
        try:
            # Validate telegram setting
            if 'telegram' in new_channels and new_channels['telegram']:
                if not telegram_config.enabled:
                    logger.warning("Telegram requested but not configured in settings")
                    new_channels['telegram'] = False
            
            # Update channels
            self.notification_channels.update(new_channels)
            
            logger.info(f"Notification channels updated: {new_channels}")
            return {'status': 'success', 'channels': self.notification_channels}
            
        except Exception as e:
            logger.error(f"Failed to update notification channels: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def get_settings_info(self):
        """Get current settings information for debugging"""
        return {
            'environment': settings.environment,
            'monitor_config': {
                'default_check_interval_minutes': monitor_config.default_check_interval_minutes,
                'min_check_interval_minutes': monitor_config.min_check_interval_minutes,
                'max_check_interval_minutes': monitor_config.max_check_interval_minutes,
                'default_networks': [net.value for net in monitor_config.default_networks],
                'supported_networks': [net.value for net in monitor_config.supported_networks],
                'alert_thresholds': monitor_config.alert_thresholds,
                'max_alerts_per_notification': monitor_config.max_alerts_per_notification,
                'max_stored_alerts': monitor_config.max_stored_alerts
            },
            'analysis_config': {
                'default_wallet_count': analysis_config.default_wallet_count,
                'max_wallet_count': analysis_config.max_wallet_count,
                'max_days_back': analysis_config.max_days_back,
                'excluded_tokens_count': len(analysis_config.excluded_tokens),
                'min_eth_value': analysis_config.min_eth_value,
                'min_eth_value_base': analysis_config.min_eth_value_base
            },
            'telegram_config': {
                'enabled': telegram_config.enabled,
                'bot_token_configured': bool(telegram_config.bot_token),
                'chat_id_configured': bool(telegram_config.chat_id),
                'max_message_length': telegram_config.max_message_length
            }
        }

# Global monitor instance with settings integration
try:
    monitor = TokenMonitor()
    logger.info("TokenMonitor instance created successfully with settings integration")
except Exception as e:
    logger.error(f"Failed to create TokenMonitor instance: {e}")
    monitor = None

# Flask Blueprint routes with enhanced settings integration
@monitor_bp.route('/status', methods=['GET'])
def get_monitor_status():
    """Get detailed monitor status including settings info"""
    try:
        if not monitor:
            return jsonify({
                'error': 'Monitor not initialized',
                'settings_available': True,
                'settings_info': {
                    'environment': settings.environment,
                    'telegram_enabled': telegram_config.enabled,
                    'supported_networks': [net.value for net in monitor_config.supported_networks]
                }
            }), 500
        
        status = monitor.get_status()
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Error getting monitor status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/start', methods=['POST'])
def start_monitor():
    """Start monitor with settings validation"""
    try:
        if not monitor:
            return jsonify({'error': 'Monitor not initialized'}), 500
        
        result = monitor.start_monitoring()
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error starting monitor: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/stop', methods=['POST'])
def stop_monitor():
    """Stop monitor"""
    try:
        if not monitor:
            return jsonify({'error': 'Monitor not initialized'}), 500
        
        result = monitor.stop_monitoring()
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error stopping monitor: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/config', methods=['GET', 'POST'])
def monitor_config_endpoint():
    """Get or update monitor configuration with settings validation"""
    try:
        if not monitor:
            if request.method == 'POST':
                return jsonify({'error': 'Monitor not initialized'}), 500
            else:
                # Return default config from settings
                return jsonify({
                    'check_interval_minutes': monitor_config.default_check_interval_minutes,
                    'networks': [net.value for net in monitor_config.default_networks],
                    'num_wallets': analysis_config.default_wallet_count,
                    'use_interval_for_timeframe': True,
                    'settings_limits': {
                        'min_check_interval_minutes': monitor_config.min_check_interval_minutes,
                        'max_check_interval_minutes': monitor_config.max_check_interval_minutes,
                        'max_wallet_count': analysis_config.max_wallet_count,
                        'supported_networks': [net.value for net in monitor_config.supported_networks]
                    }
                })
        
        if request.method == 'POST':
            new_config = request.json
            result = monitor.update_config(new_config)
            return jsonify(result)
        else:
            config = monitor.config.copy()
            config['settings_limits'] = {
                'min_check_interval_minutes': monitor_config.min_check_interval_minutes,
                'max_check_interval_minutes': monitor_config.max_check_interval_minutes,
                'max_wallet_count': analysis_config.max_wallet_count,
                'supported_networks': [net.value for net in monitor_config.supported_networks]
            }
            return jsonify(config)
        
    except Exception as e:
        logger.error(f"Error with monitor config: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/thresholds', methods=['GET', 'POST'])
def alert_thresholds_endpoint():
    """Get or update alert thresholds"""
    try:
        if not monitor:
            if request.method == 'POST':
                return jsonify({'error': 'Monitor not initialized'}), 500
            else:
                return jsonify({
                    'thresholds': monitor_config.alert_thresholds,
                    'source': 'settings_default'
                })
        
        if request.method == 'POST':
            new_thresholds = request.json
            result = monitor.update_alert_thresholds(new_thresholds)
            return jsonify(result)
        else:
            return jsonify({
                'thresholds': monitor.alert_thresholds,
                'defaults': monitor_config.alert_thresholds
            })
        
    except Exception as e:
        logger.error(f"Error with alert thresholds: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/notifications', methods=['GET', 'POST'])
def notification_channels_endpoint():
    """Get or update notification channel settings"""
    try:
        if not monitor:
            if request.method == 'POST':
                return jsonify({'error': 'Monitor not initialized'}), 500
            else:
                return jsonify({
                    'channels': {
                        'console': True,
                        'telegram': telegram_config.enabled,
                        'file': True,
                        'webhook': False
                    },
                    'telegram_configured': telegram_config.enabled
                })
        
        if request.method == 'POST':
            new_channels = request.json
            result = monitor.update_notification_channels(new_channels)
            return jsonify(result)
        else:
            return jsonify({
                'channels': monitor.notification_channels,
                'telegram_configured': telegram_config.enabled,
                'max_message_length': telegram_config.max_message_length
            })
        
    except Exception as e:
        logger.error(f"Error with notification channels: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/alerts', methods=['GET'])
def get_alerts():
    """Get recent alerts with pagination"""
    try:
        if not monitor:
            return jsonify([])
        
        limit = request.args.get('limit', 20, type=int)
        limit = min(limit, monitor_config.max_stored_alerts)  # Enforce settings limit
        
        alerts = [alert.to_dict() for alert in monitor.alerts[-limit:]]
        
        return jsonify({
            'alerts': alerts,
            'total_count': len(monitor.alerts),
            'limit': limit,
            'max_stored': monitor_config.max_stored_alerts
        })
        
    except Exception as e:
        logger.error(f"Error getting alerts: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/settings-info', methods=['GET'])
def get_settings_info():
    """Get current settings information for debugging"""
    try:
        if not monitor:
            return jsonify({
                'error': 'Monitor not initialized',
                'basic_settings': {
                    'environment': settings.environment,
                    'telegram_enabled': telegram_config.enabled,
                    'supported_networks': [net.value for net in monitor_config.supported_networks]
                }
            })
        
        return jsonify(monitor.get_settings_info())
        
    except Exception as e:
        logger.error(f"Error getting settings info: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/test', methods=['GET'])
def test_monitor():
    """Test monitor functionality with settings"""
    try:
        test_results = {
            'monitor_available': monitor is not None,
            'settings_loaded': True,
            'telegram_configured': telegram_config.enabled,
            'supported_networks': [net.value for net in monitor_config.supported_networks],
            'excluded_tokens_count': len(analysis_config.excluded_tokens),
            'alert_thresholds': monitor_config.alert_thresholds if monitor else {}
        }
        
        if monitor:
            test_results.update({
                'monitor_status': monitor.get_status(),
                'config_valid': True
            })
        
        return jsonify({
            'status': 'success',
            'test_results': test_results,
            'environment': settings.environment
        })
        
    except Exception as e:
        logger.error(f"Monitor test failed: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'error': str(e),
            'test_results': {
                'monitor_available': False,
                'settings_loaded': False
            }
        }), 500

if __name__ == "__main__":
    # Test the monitor directly with settings
    print("Testing monitor with settings integration...")
    if monitor:
        print(f"Environment: {settings.environment}")
        print(f"Supported networks: {[net.value for net in monitor_config.supported_networks]}")
        print(f"Default interval: {monitor_config.default_check_interval_minutes} minutes")
        print(f"Alert thresholds: {monitor_config.alert_thresholds}")
        print(f"Telegram enabled: {telegram_config.enabled}")
        
        # Quick test with reduced wallet count
        monitor.config['num_wallets'] = 10
        monitor.check_for_new_tokens()
    else:
        print("❌ Monitor initialization failed")