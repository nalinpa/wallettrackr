import asyncio
import logging
from typing import List, Dict, Optional, Set
from datetime import datetime
import time

from services.service_container import ServiceContainer
from core.data.models import Purchase, AnalysisResult

logger = logging.getLogger(__name__)

class BuyAnalyzer:
    """Buy transaction analyzer with better performance and error handling"""
    
    def __init__(self, network: str):
        self.network = network
        self.services: Optional[ServiceContainer] = None
        
        # Pre-compile exclusion sets for O(1) lookup
        self.EXCLUDED_ASSETS = frozenset({
            'ETH', 'WETH', 'USDC', 'USDT', 'DAI', 'BUSD', 'FRAX', 'LUSD', 'USDC.E'
        })
        
        self.EXCLUDED_CONTRACTS = frozenset({
            '0xdac17f958d2ee523a2206206994597c13d831ec7',  # USDT
            '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',  # USDC
            '0x6b175474e89094c44da98b954eedeac495271d0f',  # DAI
            '0x4fabb145d64652a948d72533023f6e7a623c7c53',  # BUSD
            '0x853d955acef822db058eb8505911ed77f175b99e',  # FRAX
            '0x5f98805a4e8be255a32880fdec7f6728c6568ba0',  # LUSD
            '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',  # WETH
            '0xa1319274692170c2eaa25c6e5ce3a56da79782f0',  # WETH (Base)
            '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913',  # USDC on Base
            '0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca',  # USDbC on Base
        })
        
        # Performance tracking
        self.stats = {
            "wallets_processed": 0,
            "wallets_failed": 0,
            "transfers_processed": 0,
            "purchases_found": 0,
            "tokens_filtered": 0
        }
    
    async def __aenter__(self):
        """Initialize services"""
        self.services = ServiceContainer(self.network)
        await self.services.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup services"""
        if self.services:
            await self.services.__aexit__(exc_type, exc_val, exc_tb)
    
    def is_excluded_token(self, asset: str, contract_address: str = None) -> bool:
        """Fast token exclusion check using pre-compiled sets"""
        # Check by symbol (O(1) lookup)
        if asset.upper() in self.EXCLUDED_ASSETS:
            return True
        
        # Check by contract address (O(1) lookup)
        if contract_address and contract_address.lower() in self.EXCLUDED_CONTRACTS:
            return True
        
        # Pattern matching for stablecoins (cached check)
        asset_upper = asset.upper()
        if len(asset) <= 6 and any(stable in asset_upper for stable in ['USD', 'DAI']):
            return True
        
        return False
    
    async def analyze_wallets_concurrent(self, num_wallets: int = 173, 
                                       days_back: float = 1.0) -> AnalysisResult:
        """Main analysis with better error handling and performance tracking"""
        start_time = time.time()
        logger.info(f"🚀 Starting {self.network} buy analysis: {num_wallets} wallets, {days_back} days")
        
        try:
            # Reset stats
            self.stats = {k: 0 for k in self.stats}
            
            # Get wallets
            wallets = await self.services.database.get_top_wallets(self.network, num_wallets)
            if not wallets:
                logger.warning(f"⚠️ No wallets found for {self.network}")
                return self._empty_result()
            
            logger.info(f"📊 Retrieved {len(wallets)} wallets")
            
            # Get block range
            start_block, end_block = await self.services.alchemy.get_block_range(days_back)
            logger.info(f"🔍 Analyzing blocks {start_block} to {end_block}")
            
            # Get all transfers with better batching
            wallet_addresses = [w['address'] for w in wallets]
            all_transfers = await self.services.alchemy.get_transfers_batch(
                wallet_addresses, start_block, end_block
            )
            
            logger.info(f"📦 Retrieved transfers for {len(all_transfers)} wallets")
            
            # Process transfers concurrently with smaller batches for better memory usage
            batch_size = 25  # Smaller batches for better memory management
            all_purchases = []
            
            for i in range(0, len(wallets), batch_size):
                batch = wallets[i:i + batch_size]
                
                # Process batch
                batch_tasks = []
                for wallet in batch:
                    address = wallet['address']
                    transfers = all_transfers.get(address, {"outgoing": [], "incoming": []})
                    task = self._process_wallet_transfers(wallet, transfers)
                    batch_tasks.append(task)
                
                # Execute batch concurrently
                try:
                    batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                    
                    # Collect results and handle errors
                    for j, result in enumerate(batch_results):
                        if isinstance(result, Exception):
                            self.stats["wallets_failed"] += 1
                            logger.warning(f"⚠️ Wallet processing error: {result}")
                        elif isinstance(result, list):
                            all_purchases.extend(result)
                            self.stats["wallets_processed"] += 1
                    
                    # Progress logging
                    processed = min(i + batch_size, len(wallets))
                    logger.debug(f"📊 Processed {processed}/{len(wallets)} wallets")
                    
                except Exception as e:
                    logger.error(f"❌ Batch processing failed: {e}")
                    self.stats["wallets_failed"] += batch_size
            
            analysis_time = time.time() - start_time
            self.stats["purchases_found"] = len(all_purchases)
            
            logger.info(f"✅ Analysis complete in {analysis_time:.2f}s: "
                       f"{len(all_purchases)} purchases from {self.stats['wallets_processed']} wallets")
            
            return self._aggregate_results(all_purchases, analysis_time, wallets)
            
        except Exception as e:
            analysis_time = time.time() - start_time
            logger.error(f"❌ Analysis failed after {analysis_time:.2f}s: {e}")
            return self._empty_result()
    
    async def _process_wallet_transfers(self, wallet: Dict, transfers: Dict) -> List[Purchase]:
        """Process transfers for a single wallet with better validation"""
        try:
            incoming = transfers.get('incoming', [])
            outgoing = transfers.get('outgoing', [])
            
            if not incoming:
                return []
            
            purchases = []
            wallet_score = wallet.get('score', 0)
            
            # Track transfers processed for stats
            self.stats["transfers_processed"] += len(incoming)
            
            # Process incoming ERC20 transfers as token purchases
            for transfer in incoming:
                try:
                    # Get asset and contract info
                    asset = transfer.get("asset")
                    contract_info = transfer.get("rawContract", {})
                    contract_address = contract_info.get("address", "").lower()
                    
                    # Skip ETH transfers
                    if not asset or asset == "ETH":
                        continue
                    
                    # Fast exclusion check
                    if self.is_excluded_token(asset, contract_address):
                        self.stats["tokens_filtered"] += 1
                        continue
                    
                    # Validate and parse amounts
                    try:
                        amount = float(transfer.get("value", "0"))
                    except (ValueError, TypeError):
                        continue
                    
                    if amount <= 0:
                        continue
                    
                    # Get transaction details
                    tx_hash = transfer.get("hash", "")
                    block_num = transfer.get("blockNum", "0x0")
                    
                    # Calculate ETH spent with better logic
                    eth_spent = self._calculate_eth_spent(outgoing, tx_hash, block_num)
                    
                    # More reasonable minimum threshold
                    if eth_spent < 0.0005:  # 0.0005 ETH minimum
                        continue
                    
                    # Create purchase record
                    purchase = Purchase(
                        transaction_hash=tx_hash,
                        token_bought=asset,
                        amount_received=amount,
                        eth_spent=eth_spent,
                        wallet_address=wallet["address"],
                        platform="DEX",  # Generic platform
                        block_number=int(block_num, 16) if block_num != "0x0" else 0,
                        timestamp=datetime.now(),
                        sophistication_score=wallet_score,
                        web3_analysis={"contract_address": contract_address}
                    )
                    
                    purchases.append(purchase)
                    
                except Exception as e:
                    logger.debug(f"Error processing individual transfer: {e}")
                    continue
            
            return purchases
            
        except Exception as e:
            logger.error(f"Error processing wallet {wallet.get('address', 'unknown')}: {e}")
            return []
    
    def _calculate_eth_spent(self, outgoing_transfers: List[Dict], target_tx: str, target_block: str) -> float:
        """Calculate ETH spent with improved accuracy"""
        if not target_tx or not outgoing_transfers:
            return 0.0
        
        total_eth = 0.0
        
        # First pass: exact transaction hash match
        for transfer in outgoing_transfers:
            if transfer.get("hash") == target_tx and transfer.get("asset") == "ETH":
                try:
                    eth_amount = float(transfer.get("value", "0"))
                    total_eth += eth_amount
                except (ValueError, TypeError):
                    continue
        
        # If no exact match, try block-based matching with limits
        if total_eth == 0.0:
            for transfer in outgoing_transfers:
                if (transfer.get("blockNum") == target_block and 
                    transfer.get("asset") == "ETH"):
                    try:
                        eth_amount = float(transfer.get("value", "0"))
                        # Only count reasonable purchase amounts
                        if 0.0001 <= eth_amount <= 50.0:
                            total_eth += eth_amount
                    except (ValueError, TypeError):
                        continue
        
        return total_eth
    
    def _aggregate_results(self, purchases: List[Purchase], analysis_time: float, wallets: List[Dict]) -> AnalysisResult:
        """Aggregate purchases with better performance and accuracy"""
        if not purchases:
            return self._empty_result()
        
        # Create wallet score lookup
        wallet_scores = {w['address']: w.get('score', 0) for w in wallets}
        
        # Group by token using dict for O(1) access
        token_summary = {}
        total_eth_spent = 0.0
        
        for purchase in purchases:
            token = purchase.token_bought
            
            if token not in token_summary:
                token_summary[token] = {
                    'total_purchases': 0,
                    'total_eth_spent': 0.0,
                    'wallets': set(),
                    'platforms': set(),
                    'contract_address': '',
                    'wallet_scores': [],
                    'is_base_native': self.network == 'base'
                }
            
            data = token_summary[token]
            data['total_purchases'] += 1
            data['total_eth_spent'] += purchase.eth_spent
            data['wallets'].add(purchase.wallet_address)
            data['platforms'].add(purchase.platform)
            
            # Add wallet score
            wallet_score = wallet_scores.get(purchase.wallet_address, 0)
            data['wallet_scores'].append(wallet_score)
            
            # Get contract address
            if purchase.web3_analysis and purchase.web3_analysis.get('contract_address'):
                data['contract_address'] = purchase.web3_analysis['contract_address']
            
            total_eth_spent += purchase.eth_spent
        
        # Calculate metrics and rank tokens
        ranked_tokens = []
        for token, data in token_summary.items():
            wallet_count = len(data['wallets'])
            eth_spent = data['total_eth_spent']
            
            # Calculate average wallet score
            if data['wallet_scores']:
                data['avg_wallet_score'] = sum(data['wallet_scores']) / len(data['wallet_scores'])
            else:
                data['avg_wallet_score'] = 0.0
            
            # Better alpha score calculation
            base_score = (wallet_count * 15) + (eth_spent * 50)
            quality_multiplier = 1 + (data['avg_wallet_score'] / 100)
            alpha_score = base_score * quality_multiplier
            
            # Convert sets to lists and clean up
            data['wallets'] = list(data['wallets'])
            data['platforms'] = list(data['platforms'])
            data['wallet_count'] = wallet_count
            del data['wallet_scores']  # Remove to save memory
            
            ranked_tokens.append((token, data, alpha_score))
        
        # Sort by alpha score
        ranked_tokens.sort(key=lambda x: x[2], reverse=True)
        
        # Build platform summary
        platform_summary = {}
        for purchase in purchases:
            platform = purchase.platform
            platform_summary[platform] = platform_summary.get(platform, 0) + 1
        
        logger.info(f"📊 Final results: {len(purchases)} purchases, "
                   f"{len(token_summary)} tokens, {total_eth_spent:.4f} ETH total")
        logger.info(f"📈 Performance: {self.stats}")
        
        return AnalysisResult(
            network=self.network,
            analysis_type="buy",
            total_transactions=len(purchases),
            unique_tokens=len(token_summary),
            total_eth_value=total_eth_spent,
            ranked_tokens=ranked_tokens,
            performance_metrics={
                'analysis_time_seconds': analysis_time,
                'platform_summary': platform_summary,
                'stats': self.stats
            },
            web3_enhanced=False
        )
    
    def _empty_result(self) -> AnalysisResult:
        """Return empty result with stats"""
        return AnalysisResult(
            network=self.network,
            analysis_type="buy",
            total_transactions=0,
            unique_tokens=0,
            total_eth_value=0.0,
            ranked_tokens=[],
            performance_metrics={
                'analysis_time_seconds': 0.0,
                'stats': self.stats
            },
            web3_enhanced=False
        )