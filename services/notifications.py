import httpx
import asyncio
import logging
from typing import Optional
import os

logger = logging.getLogger(__name__)

class TelegramClient:
    """Simple Telegram bot client for sending notifications"""
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        self._client: Optional[httpx.AsyncClient] = None
        
    async def __aenter__(self):
        """Initialize client"""
        if self.bot_token and self.chat_id:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
            logger.info("✅ Telegram client initialized")
        else:
            logger.warning("⚠️ Telegram bot token or chat ID not configured")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup client"""
        if self._client:
            await self._client.aclose()
    
    async def send_message(self, message: str) -> bool:
        """Send a message to Telegram"""
        if not self._client or not self.bot_token or not self.chat_id:
            logger.debug("📱 Telegram not configured, skipping notification")
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            
            # Split long messages
            if len(message) > 4000:
                message = message[:4000] + "..."
            
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
            
            response = await self._client.post(url, json=payload)
            
            if response.status_code == 200:
                logger.info("✅ Telegram message sent successfully")
                return True
            else:
                logger.error(f"❌ Telegram API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error sending Telegram message: {e}")
            return False
    
    async def test_connection(self) -> bool:
        """Test Telegram bot connection"""
        if not self._client or not self.bot_token:
            return False
        
        try:
            url = f"{self.base_url}/getMe"
            response = await self._client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                bot_name = data.get('result', {}).get('first_name', 'Unknown')
                logger.info(f"✅ Telegram bot connection OK: {bot_name}")
                return True
            else:
                logger.error(f"❌ Telegram connection failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Telegram connection test failed: {e}")
            return False

# Global instances
telegram_client = TelegramClient()

async def send_test_notification():
    """Send a test notification to verify setup"""
    test_message = """
🧪 TEST NOTIFICATION 🧪
Crypto Alpha Monitor is working!
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    async with telegram_client:
        await telegram_client.send_message(test_message)

if __name__ == "__main__":
    # Test the notification system
    asyncio.run(send_test_notification())