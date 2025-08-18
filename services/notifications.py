import httpx
import asyncio
import logging
from typing import Optional
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class TelegramClient:
    """Enhanced Telegram bot client for sending notifications"""
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        self._client: Optional[httpx.AsyncClient] = None
        self.last_message_time = None
        
        # Log configuration status
        if self.bot_token and self.chat_id:
            logger.info(f"✅ Telegram configured: Bot token ends with ...{self.bot_token[-10:] if len(self.bot_token) > 10 else 'SHORT'}")
            logger.info(f"✅ Telegram chat ID: {self.chat_id}")
        else:
            logger.warning(f"⚠️ Telegram not configured:")
            logger.warning(f"  Bot token: {'✅ Set' if self.bot_token else '❌ Missing'}")
            logger.warning(f"  Chat ID: {'✅ Set' if self.chat_id else '❌ Missing'}")
        
    async def __aenter__(self):
        """Initialize client"""
        if self.bot_token and self.chat_id:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
            )
            logger.info("✅ Telegram client initialized")
            
            # Test the connection
            try:
                await self.test_connection()
            except Exception as e:
                logger.error(f"❌ Telegram connection test failed: {e}")
        else:
            logger.warning("⚠️ Telegram bot token or chat ID not configured")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup client"""
        if self._client:
            await self._client.aclose()
            logger.info("🔒 Telegram client closed")
    
    async def send_message(self, message: str, parse_mode: str = "Markdown") -> bool:
        """Send a message to Telegram with enhanced error handling"""
        if not self._client or not self.bot_token or not self.chat_id:
            logger.debug("📱 Telegram not configured, skipping notification")
            return False
        
        # Rate limiting - don't send more than 1 message per 3 seconds
        now = datetime.now()
        if self.last_message_time and (now - self.last_message_time).total_seconds() < 3:
            logger.debug("⏳ Rate limiting Telegram message")
            await asyncio.sleep(3)
        
        try:
            url = f"{self.base_url}/sendMessage"
            
            # Split long messages
            if len(message) > 4000:
                message = message[:3950] + "\n\n... (message truncated)"
                logger.warning("✂️ Telegram message truncated due to length")
            
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
                "disable_notification": False  # Enable notifications
            }
            
            logger.debug(f"📤 Sending Telegram message to chat {self.chat_id}")
            logger.debug(f"📝 Message preview: {message[:100]}...")
            
            response = await self._client.post(url, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                message_id = result.get('result', {}).get('message_id')
                logger.info(f"✅ Telegram message sent successfully (ID: {message_id})")
                self.last_message_time = now
                return True
            else:
                error_data = response.text
                try:
                    error_json = response.json()
                    error_description = error_json.get('description', 'Unknown error')
                    error_code = error_json.get('error_code', response.status_code)
                    
                    logger.error(f"❌ Telegram API error {error_code}: {error_description}")
                    
                    # Specific error handling
                    if error_code == 400:
                        if "chat not found" in error_description.lower():
                            logger.error("💬 Chat not found - check your TELEGRAM_CHAT_ID")
                        elif "bot was blocked" in error_description.lower():
                            logger.error("🚫 Bot was blocked by user - unblock the bot in Telegram")
                    elif error_code == 401:
                        logger.error("🔑 Unauthorized - check your TELEGRAM_BOT_TOKEN")
                    elif error_code == 429:
                        logger.error("⏰ Rate limited by Telegram - waiting before retry")
                        await asyncio.sleep(60)
                        
                except Exception:
                    logger.error(f"❌ Telegram HTTP error: {response.status_code} - {error_data}")
                
                return False
                
        except httpx.TimeoutException:
            logger.error("⏰ Telegram request timeout")
            return False
        except httpx.NetworkError as e:
            logger.error(f"🌐 Telegram network error: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected Telegram error: {e}")
            return False
    
    async def test_connection(self) -> bool:
        """Test Telegram bot connection"""
        if not self._client or not self.bot_token:
            logger.error("❌ Cannot test Telegram: client not initialized or no bot token")
            return False
        
        try:
            url = f"{self.base_url}/getMe"
            logger.debug(f"🔍 Testing Telegram connection to: {url}")
            
            response = await self._client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                bot_info = data.get('result', {})
                bot_name = bot_info.get('first_name', 'Unknown')
                bot_username = bot_info.get('username', 'Unknown')
                logger.info(f"✅ Telegram bot connection OK: @{bot_username} ({bot_name})")
                
                # Test chat access
                await self.test_chat_access()
                return True
            else:
                error_text = response.text
                logger.error(f"❌ Telegram getMe failed: {response.status_code} - {error_text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Telegram connection test failed: {e}")
            return False
    
    async def test_chat_access(self) -> bool:
        """Test if bot can access the specified chat"""
        if not self.chat_id:
            logger.error("❌ No chat ID to test")
            return False
        
        try:
            url = f"{self.base_url}/getChat"
            payload = {"chat_id": self.chat_id}
            
            response = await self._client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                chat_info = data.get('result', {})
                chat_title = chat_info.get('title') or chat_info.get('first_name', 'Private Chat')
                chat_type = chat_info.get('type', 'unknown')
                logger.info(f"✅ Telegram chat access OK: '{chat_title}' (type: {chat_type})")
                return True
            else:
                error_text = response.text
                logger.error(f"❌ Telegram chat access failed: {response.status_code} - {error_text}")
                logger.error(f"💡 Make sure the bot is added to the chat and has permission to send messages")
                return False
                
        except Exception as e:
            logger.error(f"❌ Telegram chat test failed: {e}")
            return False

# Global instance
telegram_client = TelegramClient()

async def send_alert_notifications(alerts: list):
    """Send notifications for new alerts - ENHANCED WITH LINKS AND NO LIMITS"""
    if not alerts:
        logger.debug("📱 No alerts to send")
        return
    
    logger.info(f"📱 Sending notifications for {len(alerts)} alerts")
    
    try:
        async with telegram_client:            
            # Send summary message first if multiple alerts
            if len(alerts) > 1:
                summary_message = format_alert_summary(alerts)
                await telegram_client.send_message(summary_message)
                await asyncio.sleep(2)  # Brief pause between messages
            
            # Send ALL individual alerts (no limit)
            for i, alert in enumerate(alerts):
                try:
                    message = format_alert_message(alert)
                    success = await telegram_client.send_message(message)
                    
                    if success:
                        logger.info(f"📱 Sent notification {i+1}/{len(alerts)} for {alert.get('token', 'Unknown')}")
                    else:
                        logger.error(f"❌ Failed to send notification for {alert.get('token', 'Unknown')}")
                    
                    # Brief pause between individual messages to avoid rate limits
                    if i < len(alerts) - 1:  # Don't wait after the last message
                        await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"❌ Error sending notification for {alert.get('token', 'unknown')}: {e}")
                    
            logger.info(f"✅ Completed sending {len(alerts)} notifications")
                
    except Exception as e:
        logger.error(f"❌ Error in send_alert_notifications: {e}")

def format_alert_summary(alerts: list) -> str:
    """Format a summary message for multiple alerts - ENHANCED"""
    try:
        total_alerts = len(alerts)
        buy_count = len([a for a in alerts if a.get('alert_type') == 'new_token'])
        sell_count = len([a for a in alerts if a.get('alert_type') == 'sell_pressure'])
        
        networks = list(set(alert.get('network', 'unknown') for alert in alerts))
        
        # Get top tokens by score
        top_tokens = []
        for alert in alerts[:5]:  # Show top 5 in summary
            token = alert.get('token', 'Unknown')
            data = alert.get('data', {})
            score = data.get('alpha_score') or data.get('sell_score', 0)
            eth_value = data.get('total_eth_spent') or data.get('total_eth_value') or data.get('total_estimated_eth', 0)
            top_tokens.append(f"• {token}: {score:.1f} ({eth_value:.3f} ETH)")
        
        top_tokens_text = "\n".join(top_tokens) if top_tokens else "No token data available"
        
        message = f"""
🚨 *CRYPTO ALERT SUMMARY* 🚨

📊 *{total_alerts} New Alerts Detected*
🆕 Buy Signals: {buy_count}
📉 Sell Pressure: {sell_count}
🌐 Networks: {', '.join(networks).upper()}

🔝 *Top Alerts:*
{top_tokens_text}

⏰ {datetime.now().strftime('%H:%M:%S UTC')}
"""
        
        return message.strip()
        
    except Exception as e:
        logger.error(f"Error formatting alert summary: {e}")
        return f"🚨 {len(alerts)} new crypto alerts detected!"
    
def format_alert_message(alert: dict) -> str:
    """Format individual alert for Telegram - ENHANCED WITH TRADING LINKS"""
    try:
        data = alert.get('data', {})
        alert_type = alert.get('alert_type', 'unknown')
        confidence = alert.get('confidence', 'LOW')
        token = alert.get('token', 'Unknown')
        network = alert.get('network', 'unknown').lower()
        network_display = network.upper()
        
        # Get ETH value
        eth_value = data.get('total_eth_spent') or data.get('total_eth_value') or data.get('total_estimated_eth', 0)
        
        # Get contract address
        contract_address = data.get('contract_address', '')
        contract_short = f"{contract_address[:6]}...{contract_address[-4:]}" if contract_address else "N/A"
        
        # Generate trading links
        links_section = ""
        if contract_address:
            # DexScreener link
            dexscreener_url = f"https://dexscreener.com/{network}/{contract_address}"
            
            # Uniswap link (works for both Ethereum and Base)
            uniswap_url = f"https://app.uniswap.org/#/swap?outputCurrency={contract_address}&chain={network}"
            
            # Explorer link
            explorer_url = get_explorer_link(contract_address, network)
            
            links_section = f"""
🔗 *Quick Links:*
• [📊 DexScreener]({dexscreener_url})
• [🦄 Uniswap]({uniswap_url})
• [🔍 Explorer]({explorer_url})
"""
        else:
            links_section = "\n🔗 *Links:* Contract address not available"
        
        if alert_type == 'new_token':
            score = data.get('alpha_score', 0)
            emoji = "🆕" if confidence == "LOW" else "🔥" if confidence == "HIGH" else "⚡"
            
            message = f"""
{emoji} *NEW TOKEN ALERT* {emoji}

🪙 *Token:* `{token}`
🌐 *Network:* {network_display}
📊 *Alpha Score:* {score:.1f}
💰 *ETH Spent:* {eth_value:.4f} ETH
👥 *Wallets:* {data.get('wallet_count', 0)}
🔄 *Purchases:* {data.get('total_purchases', 0)}
🎯 *Confidence:* {confidence}

📄 *Contract:* `{contract_address if contract_address else 'N/A'}`
🏪 *Platforms:* {', '.join(data.get('platforms', ['Unknown'])[:3])}
{links_section}
⏰ {datetime.now().strftime('%H:%M:%S UTC')}
"""
            
        elif alert_type == 'sell_pressure':
            score = data.get('sell_score', 0)
            emoji = "📉" if confidence == "LOW" else "🔻" if confidence == "HIGH" else "⬇️"
            
            message = f"""
{emoji} *SELL PRESSURE ALERT* {emoji}

🪙 *Token:* `{token}`
🌐 *Network:* {network_display}
📊 *Sell Score:* {score:.1f}
💰 *ETH Value:* {eth_value:.4f} ETH
👥 *Wallets:* {data.get('wallet_count', 0)}
🔄 *Sells:* {data.get('total_sells', 0)}
🎯 *Confidence:* {confidence}

📄 *Contract:* `{contract_address if contract_address else 'N/A'}`
🔧 *Methods:* {', '.join(data.get('methods', ['Unknown'])[:3])}
{links_section}
⏰ {datetime.now().strftime('%H:%M:%S UTC')}
"""
            
        else:
            message = f"""
🔔 *CRYPTO ALERT* 🔔

🪙 *Token:* `{token}`
🌐 *Network:* {network_display}
📊 *Type:* {alert_type.replace('_', ' ').title()}
💰 *ETH Value:* {eth_value:.4f} ETH
🎯 *Confidence:* {confidence}

📄 *Contract:* `{contract_address if contract_address else 'N/A'}`
{links_section}
⏰ {datetime.now().strftime('%H:%M:%S UTC')}
"""
        
        return message.strip()
        
    except Exception as e:
        logger.error(f"Error formatting alert message: {e}")
        return f"🚨 Crypto Alert: {alert.get('token', 'Unknown')} on {alert.get('network', 'Unknown')}"

def get_explorer_link(contract_address: str, network: str) -> str:
    """Get the appropriate blockchain explorer link"""
    explorers = {
        'ethereum': f"https://etherscan.io/address/{contract_address}",
        'base': f"https://basescan.org/address/{contract_address}"
    }
    
    return explorers.get(network, f"https://etherscan.io/address/{contract_address}")

# Test function to verify notifications work
async def send_test_notification():
    """Send a test notification to verify setup"""
    test_message = f"""
🧪 *TEST NOTIFICATION* 🧪

✅ Crypto Alpha Monitor is working!
📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🤖 Bot Status: Operational
📡 Notifications: Active

This is a test message to verify your Telegram notifications are working correctly.
"""
    
    try:
        async with telegram_client:
            success = await telegram_client.send_message(test_message)
            if success:
                logger.info("✅ Test notification sent successfully!")
                return True
            else:
                logger.error("❌ Test notification failed!")
                return False
    except Exception as e:
        logger.error(f"❌ Test notification error: {e}")
        return False

# Function to check notification configuration
def check_notification_config():
    """Check if Telegram notifications are properly configured"""
    issues = []
    
    if not telegram_client.bot_token:
        issues.append("❌ TELEGRAM_BOT_TOKEN environment variable not set")
    elif len(telegram_client.bot_token) < 40:
        issues.append("⚠️ TELEGRAM_BOT_TOKEN appears to be invalid (too short)")
    
    if not telegram_client.chat_id:
        issues.append("❌ TELEGRAM_CHAT_ID environment variable not set")
    elif not (telegram_client.chat_id.startswith('-') or telegram_client.chat_id.isdigit()):
        issues.append("⚠️ TELEGRAM_CHAT_ID format may be incorrect")
    
    if issues:
        logger.error("🔧 Telegram configuration issues found:")
        for issue in issues:
            logger.error(f"  {issue}")
        return False
    else:
        logger.info("✅ Telegram configuration looks good!")
        return True

if __name__ == "__main__":
    # Test the notification system
    import asyncio
    
    async def main():
        logger.info("🧪 Testing Telegram notification system...")
        
        # Check configuration
        if check_notification_config():
            # Send test notification
            await send_test_notification()
        else:
            logger.error("❌ Fix configuration issues before testing")
    
    asyncio.run(main())