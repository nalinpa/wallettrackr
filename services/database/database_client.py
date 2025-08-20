import motor.motor_asyncio
import logging
from typing import List, Dict, Optional
from pymongo import IndexModel, ASCENDING, DESCENDING
from config.settings import settings

logger = logging.getLogger(__name__)

class DatabaseClient:
    """MongoDB client for wallet data with proper connection pooling and indexes"""
    
    def __init__(self):
        # Better connection with proper pooling
        self.client = motor.motor_asyncio.AsyncIOMotorClient(
            settings.database.mongo_uri,
            maxPoolSize=20,
            minPoolSize=5,
            maxIdleTimeMS=30000,
            waitQueueTimeoutMS=5000,
            serverSelectionTimeoutMS=10000
        )
        self.db = self.client[settings.database.db_name]
        self.wallets_collection = self.db[settings.database.wallets_collection]
        self._indexes_created = False
        
    async def __aenter__(self):
        """Initialize connection with indexes"""
        try:
            await self.client.admin.command('ping')
            await self._create_indexes()
            logger.info("✅ MongoDB connection established")
            return self
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            raise
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close connection"""
        self.client.close()
        logger.info("🔒 MongoDB connection closed")
    
    async def _create_indexes(self):
        """Create necessary indexes for performance"""
        if self._indexes_created:
            return
            
        try:
            indexes = [
                IndexModel([("score", DESCENDING)]),  # For top wallet queries
                IndexModel([("address", ASCENDING)], unique=True),  # Address lookup
                IndexModel([("network", ASCENDING), ("score", DESCENDING)]),  # Network queries
            ]
            
            await self.wallets_collection.create_indexes(indexes)
            self._indexes_created = True
            logger.info("✅ Database indexes created")
            
        except Exception as e:
            logger.warning(f"⚠️ Index creation failed: {e}")
    
    async def get_top_wallets(self, network: str = None, limit: int = 173) -> List[Dict]:
        """Get top wallets with better query performance"""
        try:
            # Use aggregation pipeline for better performance
            pipeline = []
            
            pipeline.extend([
                {"$sort": {"score": -1}},
                {"$limit": limit},
                {"$project": {
                    "address": 1,
                    "score": 1,
                    "_id": 0  # Exclude _id to reduce data transfer
                }}
            ])
            
            cursor = self.wallets_collection.aggregate(pipeline)
            wallets = await cursor.to_list(length=limit)
            
            logger.info(f"📊 Retrieved {len(wallets)} wallets")
            return wallets
            
        except Exception as e:
            logger.error(f"❌ Error fetching wallets: {e}")
            # Return empty list instead of raising to prevent cascade failures
            return []
    
    async def count_wallets(self, network: str = None) -> int:
        """Count total wallets with better error handling"""
        try:
            query = {"network": network} if network else {}
            count = await self.wallets_collection.count_documents(query)
            return count
        except Exception as e:
            logger.error(f"❌ Error counting wallets: {e}")
            return 0
    
    async def get_wallet_batch(self, addresses: List[str]) -> List[Dict]:
        """Get multiple wallets by addresses efficiently"""
        try:
            cursor = self.wallets_collection.find(
                {"address": {"$in": addresses}},
                {"address": 1, "score": 1, "network": 1, "_id": 0}
            )
            wallets = await cursor.to_list(length=len(addresses))
            return wallets
        except Exception as e:
            logger.error(f"❌ Error fetching wallet batch: {e}")
            return []
    
    async def health_check(self) -> bool:
        """Check database health"""
        try:
            await self.client.admin.command('ping')
            return True
        except Exception:
            return False