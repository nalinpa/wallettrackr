import asyncio
import logging
from typing import List, Dict, Optional, AsyncGenerator
from datetime import datetime
import time

from services.service_container import ServiceContainer
from core.data.models import Purchase, AnalysisResult

logger = logging.getLogger(__name__)

class SellAnalyzer:
    """Sell pressure analyzer with concurrent processing"""
    
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
        """Analyze sell pressure concurrently"""
        start_time = time.time()
        logger.info(f"🚀 Starting {self.network} sell analysis: {num_wallets} wallets, {days_back} days")
        
        # Get wallets
        wallets = await self.services.database.get_top_wallets(self.network, num_wallets)
        if not wallets:
            return self._empty_result()
        
        # Get block range  
        start_block, end_block = await self.services.alchemy.get_block_range(days_back)
        
        # Get all transfers concurrently
        wallet_addresses = [w['address'] for w in wallets]
        logger.info(f"⚡ Fetching transfers for {len(wallet_addresses)} wallets concurrently...")
        
        all_transfers = await self.services.alchemy.get_transfers_batch(
            wallet_addresses, start_block, end_block
        )
        
        # Process sells concurrently
        sell_tasks = []
        for wallet in wallets:
            address = wallet['address']
            transfers = all_transfers.get(address, {"outgoing": [], "incoming": []})
            task = self._process_wallet_sells(wallet, transfers)
            sell_tasks.append(task)
        
        wallet_results = await asyncio.gather(*sell_tasks, return_exceptions=True)
        
        # Collect results
        all_sells = []
        for result in wallet_results:
            if isinstance(result, list):
                all_sells.extend(result)
        
        analysis_time = time.time() - start_time
        logger.info(f"✅ Sell analysis complete in {analysis_time:.2f}s: {len(all_sells)} sells")
        
        return self._aggregate_results(all_sells, analysis_time)
    
    async def analyze_with_progress(self, num_wallets: int = 173, 
                                  days_back: float = 1.0) -> AsyncGenerator[Dict, None]:
        """Analyze with progress updates"""
        yield {'type': 'progress', 'stage': 'initializing', 'percentage': 0}
        
        # Get wallets
        wallets = await self.services.database.get_top_wallets(self.network, num_wallets)
        
        yield {'type': 'progress', 'stage': 'fetching_transfers', 'percentage': 20}
        
        # Get transfers
        start_block, end_block = await self.services.alchemy.get_block_range(days_back)
        wallet_addresses = [w['address'] for w in wallets]
        all_transfers = await self.services.alchemy.get_transfers_batch(
            wallet_addresses, start_block, end_block
        )
        
        yield {'type': 'progress', 'stage': 'processing_sells', 'percentage': 50}
        
        # Process in batches
        all_sells = []
        batch_size = 5
        processed = 0
        
        for i in range(0, len(wallets), batch_size):
            batch = wallets[i:i + batch_size]
            
            batch_tasks = []
            for wallet in batch:
                address = wallet['address']
                transfers = all_transfers.get(address, {"outgoing": [], "incoming": []})
                task = self._process_wallet_sells(wallet, transfers)
                batch_tasks.append(task)
            
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for result in batch_results:
                processed += 1
                if isinstance(result, list):
                    all_sells.extend(result)
                
                yield {
                    'type': 'progress',
                    'processed': processed,
                    'total': len(wallets),
                    'percentage': int(50 + (processed / len(wallets)) * 40)
                }
        
        # Final results
        result = self._aggregate_results(all_sells, 0)
        yield {'type': 'results', 'data': result.dict()}
        yield {'type': 'complete'}
    
    async def _process_wallet_sells(self, wallet: Dict, transfers: Dict) -> List[Purchase]:
        """Process sells for a single wallet"""
        outgoing = transfers.get('outgoing', [])
        
        if not outgoing:
            return []
        
        sells = []
        
        # Process outgoing ERC20 transfers as potential sells
        for transfer in outgoing:
            token_sold = transfer.get("asset")
            if not token_sold or token_sold in ["ETH"]:
                continue
            
            try:
                amount_sold = float(transfer.get("value", 0))
                if amount_sold <= 1:  # Skip dust
                    continue
                
                # Create sell record
                sell = Purchase(
                    transaction_hash=transfer.get("hash", ""),
                    token_bought="ETH",  # Assuming sold for ETH
                    amount_received=amount_sold * 0.0005,  # Rough ETH estimate
                    eth_spent=0,  # This is a sell
                    wallet_address=wallet["address"],
                    platform="Unknown",
                    block_number=int(transfer.get("blockNum", "0x0"), 16),
                    timestamp=datetime.now(),
                    sophistication_score=None,
                    web3_analysis=None
                )
                
                sells.append(sell)
                
            except (ValueError, TypeError):
                continue
        
        return sells
    
    def _aggregate_results(self, sells: List[Purchase], analysis_time: float) -> AnalysisResult:
        """Aggregate sells into result"""
        if not sells:
            return self._empty_result()
        
        # Group by token (the token that was sold)
        token_summary = {}
        for sell in sells:
            # For sells, we need to figure out what token was actually sold
            # This is a simplified version - you might want to enhance this
            token = "UNKNOWN"  # You'd extract this from the transfer data
            
            if token not in token_summary:
                token_summary[token] = {
                    'count': 0,
                    'total_estimated_eth': 0,
                    'wallets': set(),
                    'sells': []
                }
            
            token_summary[token]['count'] += 1
            token_summary[token]['total_estimated_eth'] += sell.amount_received
            token_summary[token]['wallets'].add(sell.wallet_address)
            token_summary[token]['sells'].append(sell)
        
        # Rank by estimated ETH value
        ranked_tokens = sorted(
            [(token, data, data['total_estimated_eth']) for token, data in token_summary.items()],
            key=lambda x: x[2],
            reverse=True
        )
        
        return AnalysisResult(
            network=self.network,
            analysis_type="sell",
            total_transactions=len(sells),
            unique_tokens=len(token_summary),
            total_eth_value=sum(s.amount_received for s in sells),
            ranked_tokens=ranked_tokens,
            performance_metrics={'analysis_time_seconds': analysis_time},
            web3_enhanced=False
        )
    
    def _empty_result(self) -> AnalysisResult:
        """Return empty result"""
        return AnalysisResult(
            network=self.network,
            analysis_type="sell",
            total_transactions=0,
            unique_tokens=0,
            total_eth_value=0.0,
            ranked_tokens=[],
            performance_metrics={'analysis_time_seconds': 0.0},
            web3_enhanced=False
        )