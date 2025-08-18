import motor.motor_asyncio
import logging
from typing import List, Dict, Optional
from config.settings import settings

logger = logging.getLogger(__name__)

class DatabaseClient:
    """MongoDB client for wallet data"""
    
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(settings.database.mongo_uri)
        self.db = self.client[settings.database.db_name]
        self.wallets_collection = self.db[settings.database.wallets_collection]
        
    async def __aenter__(self):
        """Initialize connection"""
        try:
            await self.client.admin.command('ping')
            logger.info("✅ MongoDB connection established")
            return self
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            raise
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close connection"""
        self.client.close()
        logger.info("🔒 MongoDB connection closed")
    
    async def get_top_wallets(self, network: str = None, limit: int = 173) -> List[Dict]:
        """Get top wallets"""
        try:
            query = {}
            
            cursor = self.wallets_collection.find(query).sort('score', 1).limit(limit)
            wallets = await cursor.to_list(length=limit)
            
            logger.info(f"📊 Retrieved {len(wallets)} wallets")
            return wallets
            
        except Exception as e:
            logger.error(f"❌ Error fetching wallets: {e}")
            return []
    
    async def count_wallets(self, network: str = None) -> int:
        """Count total wallets"""
        try:
            query = {}
            if network:
                query['network'] = network
            
            count = await self.wallets_collection.count_documents(query)
            return count
        except Exception as e:
            logger.error(f"❌ Error counting wallets: {e}")
            return 0