import asyncio
from dataclasses import dataclass
from typing import Optional
from .blockchain.alchemy_client import AlchemyClient
from .database.database_client import DatabaseClient
from .blockchain.analysis import AnalysisService  # Add this import
import logging

logger = logging.getLogger(__name__)

@dataclass
class ServiceContainer:
    """Service dependency injection container"""
    
    network: str
    alchemy: Optional[AlchemyClient] = None
    database: Optional[DatabaseClient] = None
    analysis: Optional[AnalysisService] = None  # Add this field
    _initialized: bool = False
    
    async def __aenter__(self):
        """Initialize all services"""
        if not self._initialized:
            logger.info(f"🚀 Initializing services for {self.network}")
            
            # Initialize services concurrently
            alchemy_task = AlchemyClient(self.network).__aenter__()
            database_task = DatabaseClient().__aenter__()
            
            # AnalysisService doesn't need async initialization, so create it directly
            self.analysis = AnalysisService(network=self.network)
            
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
            
            # AnalysisService doesn't need async cleanup
            self.analysis = None
            
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
        
        if self.analysis:
            try:
                # Test analysis service by getting summary
                summary = await self.analysis.get_analysis_summary()
                results['analysis'] = len(summary.get('supported_methods', [])) > 0
            except:
                results['analysis'] = False
        
        return results
    
    async def get_service_info(self) -> dict:
        """Get information about available services"""
        info = {
            'network': self.network,
            'initialized': self._initialized,
            'services': {}
        }
        
        if self.alchemy:
            info['services']['alchemy'] = {
                'available': True,
                'network': self.network,
                'type': 'blockchain_client'
            }
        
        if self.database:
            info['services']['database'] = {
                'available': True,
                'type': 'database_client'
            }
        
        if self.analysis:
            try:
                analysis_summary = await self.analysis.get_analysis_summary()
                info['services']['analysis'] = {
                    'available': True,
                    'type': 'analysis_service',
                    'capabilities': analysis_summary
                }
            except:
                info['services']['analysis'] = {
                    'available': True,
                    'type': 'analysis_service',
                    'capabilities': {}
                }
        
        return info

# Factory function
async def create_services(network: str) -> ServiceContainer:
    """Create and initialize service container"""
    container = ServiceContainer(network)
    await container.__aenter__()
    return container

# Utility function to check if all services are available
async def check_all_services(network: str) -> dict:
    """Check availability of all services for a network"""
    async with ServiceContainer(network) as services:
        connections = await services.test_connections()
        service_info = await services.get_service_info()
        
        return {
            'network': network,
            'connection_tests': connections,
            'service_info': service_info,
            'all_services_available': all(connections.values())
        }