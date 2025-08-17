import asyncio
from dataclasses import dataclass
from typing import Optional
from .blockchain.alchemy_client import AlchemyClient
from .database.database_client import DatabaseClient
import logging

logger = logging.getLogger(__name__)

@dataclass
class ServiceContainer:
    """Service dependency injection container"""
    
    network: str
    alchemy: Optional[AlchemyClient] = None
    database: Optional[DatabaseClient] = None
    _initialized: bool = False
    
    async def __aenter__(self):
        """Initialize all services"""
        if not self._initialized:
            logger.info(f"🚀 Initializing services for {self.network}")
            
            # Initialize services concurrently
            alchemy_task = AlchemyClient(self.network).__aenter__()
            database_task = DatabaseClient().__aenter__()
            
            self.alchemy, self.database = await asyncio.gather(
                alchemy_task, database_task
            )
            
            self._initialized = True
            logger.info(f"✅ All services initialized for {self.network}")
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup all services"""
        if self._initialized:
            cleanup_tasks = []
            
            if self.alchemy:
                cleanup_tasks.append(self.alchemy.__aexit__(exc_type, exc_val, exc_tb))
            
            if self.database:
                cleanup_tasks.append(self.database.__aexit__(exc_type, exc_val, exc_tb))
            
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            
            logger.info(f"🔒 All services cleaned up for {self.network}")
    
    async def test_connections(self) -> dict[str, bool]:
        """Test all service connections"""
        results = {}
        
        if self.alchemy:
            results['alchemy'] = await self.alchemy.test_connection()
        
        if self.database:
            try:
                count = await self.database.count_wallets()
                results['database'] = count > 0
            except:
                results['database'] = False
        
        return results

# Factory function
async def create_services(network: str) -> ServiceContainer:
    """Create and initialize service container"""
    container = ServiceContainer(network)
    await container.__aenter__()
    return container