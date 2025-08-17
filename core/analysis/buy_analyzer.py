import asyncio
import logging
from typing import List, Dict, Optional, AsyncGenerator
from datetime import datetime
import time

from services.service_container import ServiceContainer
from core.data.models import Purchase, AnalysisResult

logger = logging.getLogger(__name__)

class BuyAnalyzer:
    """Buy transaction analyzer with concurrent processing"""
    
    def __init__(self, network: str):
        self.network = network
        self.services: Optional[ServiceContainer] = None
    
    async def __aenter__(self):
        """Initialize services"""
        self.services = ServiceContainer(self.network)
        await self.services.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup services"""
        if self.services:
            await self.services.__aexit__(exc_type, exc_val, exc_tb)
    
    async def analyze_wallets_concurrent(self, num_wallets: int = 173, 
                                       days_back: float = 1.0) -> AnalysisResult:
        """Main analysis method - processes wallets concurrently"""
        start_time = time.time()
        logger.info(f"🚀 Starting {self.network} buy analysis: {num_wallets} wallets, {days_back} days")
        
        # Get wallets
        wallets = await self.services.database.get_top_wallets(self.network, num_wallets)
        if not wallets:
            return self._empty_result()
        
        # Get block range
        start_block, end_block = await self.services.alchemy.get_block_range(days_back)
        
        # THE MAGIC: Get all transfers concurrently (HUGE PERFORMANCE GAIN)
        wallet_addresses = [w['address'] for w in wallets]
        logger.info(f"⚡ Fetching transfers for {len(wallet_addresses)} wallets concurrently...")
        
        all_transfers = await self.services.alchemy.get_transfers_batch(
            wallet_addresses, start_block, end_block
        )
        
        # Process transfers into purchases concurrently
        purchase_tasks = []
        for wallet in wallets:
            address = wallet['address']
            transfers = all_transfers.get(address, {"outgoing": [], "incoming": []})
            task = self._process_wallet_transfers(wallet, transfers)
            purchase_tasks.append(task)
        
        # Process all wallets concurrently
        wallet_results = await asyncio.gather(*purchase_tasks, return_exceptions=True)
        
        # Collect results
        all_purchases = []
        for result in wallet_results:
            if isinstance(result, list):
                all_purchases.extend(result)
        
        analysis_time = time.time() - start_time
        logger.info(f"✅ Analysis complete in {analysis_time:.2f}s: {len(all_purchases)} purchases")
        
        return self._aggregate_results(all_purchases, analysis_time)
    
    async def analyze_with_progress(self, num_wallets: int = 173, 
                                  days_back: float = 1.0) -> AsyncGenerator[Dict, None]:
        """Analysis with real-time progress updates"""
        # Implementation here - same as before but with clean imports
        pass
    
    async def _process_wallet_transfers(self, wallet: Dict, transfers: Dict) -> List[Purchase]:
        """Process transfers for a single wallet"""
        # Implementation here - extract purchases from transfers
        pass
    
    def _aggregate_results(self, purchases: List[Purchase], analysis_time: float) -> AnalysisResult:
        """Aggregate purchases into final result"""
        # Implementation here - group and rank tokens
        pass
    
    def _empty_result(self) -> AnalysisResult:
        """Return empty result"""
        return AnalysisResult(
            network=self.network,
            analysis_type="buy",
            total_transactions=0,
            unique_tokens=0,
            total_eth_value=0.0,
            ranked_tokens=[],
            performance_metrics={'analysis_time_seconds': 0.0},
            web3_enhanced=False
        )