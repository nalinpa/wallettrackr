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
        
        # Define excluded tokens and contracts (same as BuyAnalyzer)
        self.EXCLUDED_ASSETS = {
            'ETH', 'WETH', 'USDC', 'USDT', 'DAI', 'BUSD', 'FRAX', 'LUSD', 'USDC.E'
        }
        
        self.EXCLUDED_CONTRACTS = {
            # Ethereum mainnet stablecoins
            '0xdac17f958d2ee523a2206206994597c13d831ec7',  # USDT
            '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',  # USDC
            '0x6b175474e89094c44da98b954eedeac495271d0f',  # DAI
            '0x4fabb145d64652a948d72533023f6e7a623c7c53',  # BUSD
            '0x853d955acef822db058eb8505911ed77f175b99e',  # FRAX
            '0x5f98805a4e8be255a32880fdec7f6728c6568ba0',  # LUSD
            
            # WETH variants
            '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',  # WETH
            '0xa1319274692170c2eaa25c6e5ce3a56da79782f0',  # WETH (Base)
            
            # Base network stablecoins
            '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913',  # USDC on Base
            '0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca',  # USDbC on Base
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
    
    def add_excluded_token(self, symbol: str = None, contract_address: str = None):
        """Add token to exclusion list"""
        if symbol:
            self.EXCLUDED_ASSETS.add(symbol.upper())
            logger.info(f"Added {symbol} to excluded assets")
        
        if contract_address:
            self.EXCLUDED_CONTRACTS.add(contract_address.lower())
            logger.info(f"Added {contract_address} to excluded contracts")
    
    def is_excluded_token(self, asset: str, contract_address: str = None) -> bool:
        """Check if token should be excluded"""
        # Check by symbol
        if asset.upper() in self.EXCLUDED_ASSETS:
            return True
        
        # Check by contract address
        if contract_address and contract_address.lower() in self.EXCLUDED_CONTRACTS:
            return True
        
        # Check for stablecoin patterns
        if any(stable in asset.upper() for stable in ['USD', 'USDC', 'USDT', 'DAI']):
            if len(asset) <= 6:  # Short names are likely stablecoins
                return True
        
        return False
    
    async def analyze_wallets_concurrent(self, num_wallets: int = 173, 
                                       days_back: float = 1.0) -> AnalysisResult:
        """Analyze sell pressure concurrently"""
        start_time = time.time()
        logger.info(f"🚀 Starting {self.network} sell analysis: {num_wallets} wallets, {days_back} days")
        
        try:
            # Get wallets
            wallets = await self.services.database.get_top_wallets(self.network, num_wallets)
            if not wallets:
                logger.warning(f"⚠️ No wallets found for {self.network}")
                return self._empty_result()
            
            logger.info(f"📊 Retrieved {len(wallets)} wallets")
            
            # Get block range  
            start_block, end_block = await self.services.alchemy.get_block_range(days_back)
            logger.info(f"🔍 Analyzing blocks {start_block} to {end_block}")
            
            # Get all transfers concurrently
            wallet_addresses = [w['address'] for w in wallets]
            logger.info(f"⚡ Fetching transfers for {len(wallet_addresses)} wallets concurrently...")
            
            all_transfers = await self.services.alchemy.get_transfers_batch(
                wallet_addresses, start_block, end_block
            )
            
            logger.info(f"📦 Retrieved transfers for {len(all_transfers)} wallets")
            
            # Process sells concurrently
            sell_tasks = []
            for wallet in wallets:
                address = wallet['address']
                transfers = all_transfers.get(address, {"outgoing": [], "incoming": []})
                task = self._process_wallet_sells(wallet, transfers)
                sell_tasks.append(task)
            
            logger.info(f"🔄 Processing {len(sell_tasks)} wallets concurrently...")
            wallet_results = await asyncio.gather(*sell_tasks, return_exceptions=True)
            
            # Collect results
            all_sells = []
            error_count = 0
            for result in wallet_results:
                if isinstance(result, Exception):
                    error_count += 1
                    logger.warning(f"⚠️ Wallet processing error: {result}")
                elif isinstance(result, list):
                    all_sells.extend(result)
            
            if error_count > 0:
                logger.warning(f"⚠️ {error_count} wallets had processing errors")
            
            analysis_time = time.time() - start_time
            logger.info(f"✅ Sell analysis complete in {analysis_time:.2f}s: {len(all_sells)} sells")
            
            return self._aggregate_results(all_sells, analysis_time, wallets)
            
        except Exception as e:
            analysis_time = time.time() - start_time
            logger.error(f"❌ Sell analysis failed after {analysis_time:.2f}s: {e}", exc_info=True)
            return self._empty_result()
    
    async def analyze_with_progress(self, num_wallets: int = 173, 
                                  days_back: float = 1.0) -> AsyncGenerator[Dict, None]:
        """Analyze with progress updates"""
        start_time = time.time()
        
        try:
            # Initialization
            yield {
                'type': 'progress',
                'stage': 'initializing',
                'percentage': 0,
                'message': f'Initializing {self.network} sell analysis...'
            }
            
            # Get wallets
            wallets = await self.services.database.get_top_wallets(self.network, num_wallets)
            if not wallets:
                yield {
                    'type': 'error',
                    'message': f'No wallets found for {self.network}'
                }
                return
            
            yield {
                'type': 'progress',
                'stage': 'fetching_transfers',
                'percentage': 20,
                'message': f'Retrieved {len(wallets)} wallets, fetching transfers...'
            }
            
            # Get transfers
            start_block, end_block = await self.services.alchemy.get_block_range(days_back)
            wallet_addresses = [w['address'] for w in wallets]
            all_transfers = await self.services.alchemy.get_transfers_batch(
                wallet_addresses, start_block, end_block
            )
            
            yield {
                'type': 'progress',
                'stage': 'processing_sells',
                'percentage': 50,
                'message': f'Processing sell pressure from {len(all_transfers)} wallets...'
            }
            
            # Process in batches for progress updates
            all_sells = []
            batch_size = 10
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
            analysis_time = time.time() - start_time
            result = self._aggregate_results(all_sells, analysis_time, wallets)
            
            yield {
                'type': 'progress',
                'percentage': 100,
                'message': f'Sell analysis complete in {analysis_time:.1f}s'
            }
            
            yield {'type': 'results', 'data': result.dict()}
            yield {'type': 'complete'}
            
        except Exception as e:
            logger.error(f"❌ Streaming sell analysis failed: {e}", exc_info=True)
            yield {
                'type': 'error',
                'message': f'Sell analysis failed: {str(e)}'
            }
    
    async def _process_wallet_sells(self, wallet: Dict, transfers: Dict) -> List[Purchase]:
        """Process sells for a single wallet - FIXED FILTERING AND ETH CALCULATION"""
        try:
            outgoing = transfers.get('outgoing', [])
            incoming = transfers.get('incoming', [])
            
            if not outgoing:
                return []
            
            sells = []
            wallet_score = wallet.get('score', 0)
            
            # Define excluded tokens and contract addresses
            EXCLUDED_ASSETS = self.EXCLUDED_ASSETS
            EXCLUDED_CONTRACTS = self.EXCLUDED_CONTRACTS
            
            # Process outgoing ERC20 transfers as potential sells
            for transfer in outgoing:
                try:
                    # Get asset and contract info
                    asset = transfer.get("asset")
                    contract_info = transfer.get("rawContract", {})
                    contract_address = contract_info.get("address") or ""
                    contract_address = contract_address.lower() if contract_address else ""
                    
                    # Skip ETH transfers
                    if not asset or asset == "ETH":
                        continue
                    
                    # Skip excluded assets by symbol
                    if asset.upper() in EXCLUDED_ASSETS:
                        logger.info(f"🚫 Filtered out excluded sell asset: {asset}")
                        continue
                    
                    # Skip excluded contracts by address
                    if contract_address in EXCLUDED_CONTRACTS:
                        logger.info(f"🚫 Filtered out stablecoin sell: {asset} ({contract_address[:10]}...)")
                        continue
                    
                    # Use the utility method for additional filtering
                    if self.is_excluded_token(asset, contract_address):
                        logger.info(f"🚫 Filtered out sell by pattern matching: {asset}")
                        continue
                    
                    # Get transfer details
                    value_str = transfer.get("value", "0")
                    try:
                        # Handle scientific notation and large numbers properly
                        amount_sold = float(value_str)
                    except ValueError:
                        logger.debug(f"Could not parse sell amount: {value_str}")
                        continue
                    
                    if amount_sold <= 0:
                        continue
                    
                    # Get transaction hash for ETH received calculation
                    tx_hash = transfer.get("hash", "")
                    block_num = transfer.get("blockNum", "0x0")
                    
                    # FIXED: Proper ETH received calculation for sells
                    # Look for corresponding incoming ETH transfer in same block/tx
                    eth_received = self._calculate_eth_received(incoming, tx_hash, block_num)
                    
                    # Skip if no ETH was received (likely not a sell)
                    if eth_received < 0.0001:  # Minimum 0.0001 ETH threshold
                        # For sells, we might not always see ETH incoming immediately
                        # Use a rough estimate based on token amount
                        eth_received = min(amount_sold * 0.00001, 1.0)  # Conservative estimate
                    
                    # Skip dust sells
                    if eth_received < 0.001:  # Minimum 0.001 ETH threshold for sells
                        continue
                    
                    # Get contract address if available
                    final_contract_address = contract_address if contract_address else ""
                    
                    # Create sell record (using Purchase model but for sells)
                    sell = Purchase(
                        transaction_hash=tx_hash,
                        token_bought=asset,  # Token that was sold
                        amount_received=eth_received,  # ETH received from sell
                        eth_spent=0,  # This is a sell, not a purchase
                        wallet_address=wallet["address"],
                        platform="Uniswap",  # Default - could be enhanced
                        block_number=int(block_num, 16) if block_num != "0x0" else 0,
                        timestamp=datetime.now(),
                        sophistication_score=wallet_score,
                        web3_analysis={
                            "contract_address": final_contract_address,
                            "amount_sold": amount_sold,
                            "is_sell": True
                        }
                    )
                    
                    sells.append(sell)
                    
                except (ValueError, TypeError, KeyError) as e:
                    logger.debug(f"Error processing sell transfer: {e}")
                    continue
            
            return sells
            
        except Exception as e:
            logger.error(f"Error processing wallet sells {wallet.get('address', 'unknown')}: {e}")
            return []
    
    def _calculate_eth_received(self, incoming_transfers: List[Dict], target_tx: str, target_block: str) -> float:
        """Calculate ETH received from a sell - FIXED CALCULATION"""
        if not target_tx or not incoming_transfers:
            return 0.0
        
        total_eth_received = 0.0
        
        for transfer in incoming_transfers:
            # Match by transaction hash (most accurate)
            if transfer.get("hash") == target_tx:
                asset = transfer.get("asset", "")
                if asset == "ETH":
                    try:
                        value_str = transfer.get("value", "0")
                        eth_amount = float(value_str)
                        total_eth_received += eth_amount
                    except (ValueError, TypeError):
                        continue
            
            # Fallback: match by block number if tx hash not available
            elif transfer.get("blockNum") == target_block:
                asset = transfer.get("asset", "")
                if asset == "ETH":
                    try:
                        value_str = transfer.get("value", "0")
                        eth_amount = float(value_str)
                        # Only add reasonable amounts (likely sell proceeds, not large transfers)
                        if 0.001 <= eth_amount <= 50.0:  # Reasonable sell range
                            total_eth_received += eth_amount
                    except (ValueError, TypeError):
                        continue
        
        return total_eth_received
    
    def _aggregate_results(self, sells: List[Purchase], analysis_time: float, wallets: List[Dict]) -> AnalysisResult:
        """Aggregate sells into result - FIXED SCORING"""
        if not sells:
            return self._empty_result()
        
        # Create wallet score lookup
        wallet_scores = {w['address']: w.get('score', 0) for w in wallets}
        
        # Group by token (the token that was sold)
        token_summary = {}
        total_eth_received = 0
        
        for sell in sells:
            token = sell.token_bought  # This is the token that was sold
            
            if token not in token_summary:
                token_summary[token] = {
                    'total_sells': 0,
                    'total_estimated_eth': 0,
                    'total_amount_sold': 0,
                    'wallets': set(),
                    'platforms': set(),
                    'sells': [],
                    'contract_address': '',
                    'avg_wallet_score': 0,
                    'wallet_scores': [],
                    'avg_sophistication': None,
                    'is_base_native': self.network == 'base'
                }
            
            token_data = token_summary[token]
            token_data['total_sells'] += 1
            token_data['total_estimated_eth'] += sell.amount_received
            token_data['wallets'].add(sell.wallet_address)
            token_data['platforms'].add(sell.platform)
            token_data['sells'].append(sell)
            
            # Add wallet score
            wallet_score = wallet_scores.get(sell.wallet_address, 0)
            token_data['wallet_scores'].append(wallet_score)
            
            # Get contract address and amount sold from web3_analysis
            if sell.web3_analysis:
                if sell.web3_analysis.get('contract_address'):
                    token_data['contract_address'] = sell.web3_analysis['contract_address']
                if sell.web3_analysis.get('amount_sold'):
                    token_data['total_amount_sold'] += sell.web3_analysis['amount_sold']
            
            total_eth_received += sell.amount_received
        
        # Calculate sell pressure scores and rank tokens
        ranked_tokens = []
        for token, data in token_summary.items():
            wallet_count = len(data['wallets'])
            eth_received = data['total_estimated_eth']
            
            # Calculate average wallet score
            if data['wallet_scores']:
                data['avg_wallet_score'] = sum(data['wallet_scores']) / len(data['wallet_scores'])
            
            # FIXED: Sell pressure score calculation
            # Higher score = more sell pressure (bad for token)
            # Base score on: wallet count * ETH received, with wallet quality multiplier
            base_score = (wallet_count * 15) + (eth_received * 200)  # Higher multipliers for sell pressure
            wallet_quality_multiplier = 1 + (data['avg_wallet_score'] / 100)  # Smart wallets selling = more concerning
            sell_pressure_score = base_score * wallet_quality_multiplier
            
            # Convert sets to lists for serialization
            data['wallets'] = list(data['wallets'])
            data['platforms'] = list(data['platforms'])
            data['wallet_count'] = wallet_count
            
            # Remove sells and wallet_scores from final data (too much data for API)
            del data['sells']
            del data['wallet_scores']
            
            ranked_tokens.append((token, data, sell_pressure_score))
        
        # Sort by sell pressure score (highest = most sell pressure)
        ranked_tokens.sort(key=lambda x: x[2], reverse=True)
        
        # Build method summary (platforms used for selling)
        method_summary = {}
        for sell in sells:
            platform = sell.platform
            method_summary[platform] = method_summary.get(platform, 0) + 1
        
        logger.info(f"📊 Final sell results: {len(sells)} sells, {len(token_summary)} tokens, {total_eth_received:.4f} ETH total")
        
        return AnalysisResult(
            network=self.network,
            analysis_type="sell",
            total_transactions=len(sells),
            unique_tokens=len(token_summary),
            total_eth_value=total_eth_received,
            ranked_tokens=ranked_tokens,
            performance_metrics={
                'analysis_time_seconds': analysis_time,
                'method_summary': method_summary,
                'platform_summary': method_summary  # For compatibility
            },
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