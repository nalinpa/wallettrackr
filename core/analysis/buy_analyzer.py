import asyncio
import logging
from typing import List, Dict, Optional, AsyncGenerator, Tuple
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
        
        # Define excluded tokens and contracts
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
        """Main analysis method - processes wallets concurrently"""
        start_time = time.time()
        logger.info(f"🚀 Starting {self.network} buy analysis: {num_wallets} wallets, {days_back} days")
        
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
            
            # Process transfers into purchases concurrently
            purchase_tasks = []
            for wallet in wallets:
                address = wallet['address']
                transfers = all_transfers.get(address, {"outgoing": [], "incoming": []})
                task = self._process_wallet_transfers(wallet, transfers)
                purchase_tasks.append(task)
            
            # Process all wallets concurrently
            logger.info(f"🔄 Processing {len(purchase_tasks)} wallets concurrently...")
            wallet_results = await asyncio.gather(*purchase_tasks, return_exceptions=True)
            
            # Collect results
            all_purchases = []
            error_count = 0
            for result in wallet_results:
                if isinstance(result, Exception):
                    error_count += 1
                    logger.warning(f"⚠️ Wallet processing error: {result}")
                elif isinstance(result, list):
                    all_purchases.extend(result)
            
            if error_count > 0:
                logger.warning(f"⚠️ {error_count} wallets had processing errors")
            
            analysis_time = time.time() - start_time
            logger.info(f"✅ Analysis complete in {analysis_time:.2f}s: {len(all_purchases)} purchases")
            
            return self._aggregate_results(all_purchases, analysis_time, wallets)
            
        except Exception as e:
            analysis_time = time.time() - start_time
            logger.error(f"❌ Analysis failed after {analysis_time:.2f}s: {e}", exc_info=True)
            return self._empty_result()
    
    async def _process_wallet_transfers(self, wallet: Dict, transfers: Dict) -> List[Purchase]:
        """Process transfers for a single wallet - FIXED ETH CALCULATION"""
        try:
            incoming = transfers.get('incoming', [])
            outgoing = transfers.get('outgoing', [])
            
            if not incoming:
                return []
            
            purchases = []
            wallet_score = wallet.get('score', 0)
            
            # Define excluded tokens and contract addresses
            EXCLUDED_ASSETS = self.EXCLUDED_ASSETS
            EXCLUDED_CONTRACTS = self.EXCLUDED_CONTRACTS
            
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
                    
                    # Skip excluded assets by symbol
                    if asset.upper() in EXCLUDED_ASSETS:
                        logger.info(f"🚫 Filtered out excluded asset: {asset}")
                        continue
                    
                    # Skip excluded contracts by address
                    if contract_address in EXCLUDED_CONTRACTS:
                        logger.info(f"🚫 Filtered out stablecoin: {asset} ({contract_address[:10]}...)")
                        continue
                    
                    # Use the utility method for additional filtering
                    if self.is_excluded_token(asset, contract_address):
                        logger.info(f"🚫 Filtered out by pattern matching: {asset}")
                        continue
                    
                    # Get transfer details
                    value_str = transfer.get("value", "0")
                    try:
                        # Handle scientific notation and large numbers properly
                        amount = float(value_str)
                    except ValueError:
                        logger.debug(f"Could not parse amount: {value_str}")
                        continue
                    
                    if amount <= 0:
                        continue
                    
                    # Get transaction hash for ETH spent calculation
                    tx_hash = transfer.get("hash", "")
                    block_num = transfer.get("blockNum", "0x0")
                    
                    # FIXED: Proper ETH spent calculation
                    # Look for corresponding outgoing ETH transfer in same block/tx
                    eth_spent = self._calculate_eth_spent(outgoing, tx_hash, block_num)
                    
                    # Skip if no ETH was spent (likely not a purchase)
                    if eth_spent < 0.0001:  # Minimum 0.0001 ETH threshold
                        continue
                    
                    # Get contract address if available
                    contract_address = contract_info.get("address", "")
                    
                    # Create purchase record
                    purchase = Purchase(
                        transaction_hash=tx_hash,
                        token_bought=asset,
                        amount_received=amount,
                        eth_spent=eth_spent,
                        wallet_address=wallet["address"],
                        platform="Uniswap",  # Default - could be enhanced
                        block_number=int(block_num, 16) if block_num != "0x0" else 0,
                        timestamp=datetime.now(),
                        sophistication_score=wallet_score,
                        web3_analysis={"contract_address": contract_address}
                    )
                    
                    purchases.append(purchase)
                    
                except (ValueError, TypeError, KeyError) as e:
                    logger.debug(f"Error processing transfer: {e}")
                    continue
            
            return purchases
            
        except Exception as e:
            logger.error(f"Error processing wallet {wallet.get('address', 'unknown')}: {e}")
            return []
    
    def _calculate_eth_spent(self, outgoing_transfers: List[Dict], target_tx: str, target_block: str) -> float:
        """Calculate ETH spent for a purchase - FIXED CALCULATION"""
        if not target_tx or not outgoing_transfers:
            return 0.0
        
        total_eth_spent = 0.0
        
        for transfer in outgoing_transfers:
            # Match by transaction hash (most accurate)
            if transfer.get("hash") == target_tx:
                asset = transfer.get("asset", "")
                if asset == "ETH":
                    try:
                        value_str = transfer.get("value", "0")
                        eth_amount = float(value_str)
                        total_eth_spent += eth_amount
                    except (ValueError, TypeError):
                        continue
            
            # Fallback: match by block number if tx hash not available
            elif transfer.get("blockNum") == target_block:
                asset = transfer.get("asset", "")
                if asset == "ETH":
                    try:
                        value_str = transfer.get("value", "0")
                        eth_amount = float(value_str)
                        # Only add smaller amounts (likely purchase costs, not large transfers)
                        if eth_amount < 10.0:  # Reasonable purchase threshold
                            total_eth_spent += eth_amount
                    except (ValueError, TypeError):
                        continue
        
        return total_eth_spent
    
    def _aggregate_results(self, purchases: List[Purchase], analysis_time: float, wallets: List[Dict]) -> AnalysisResult:
        """Aggregate purchases into final result - FIXED SCORING"""
        if not purchases:
            return self._empty_result()
        
        # Create wallet score lookup
        wallet_scores = {w['address']: w.get('score', 0) for w in wallets}
        
        # Group by token
        token_summary = {}
        total_eth_spent = 0
        
        for purchase in purchases:
            token = purchase.token_bought
            
            if token not in token_summary:
                token_summary[token] = {
                    'total_purchases': 0,
                    'total_eth_spent': 0,
                    'total_amount': 0,
                    'wallets': set(),
                    'platforms': set(),
                    'purchases': [],
                    'contract_address': '',
                    'avg_wallet_score': 0,
                    'wallet_scores': [],
                    'avg_sophistication': None,
                    'is_base_native': self.network == 'base'
                }
            
            token_data = token_summary[token]
            token_data['total_purchases'] += 1
            token_data['total_eth_spent'] += purchase.eth_spent
            token_data['total_amount'] += purchase.amount_received
            token_data['wallets'].add(purchase.wallet_address)
            token_data['platforms'].add(purchase.platform)
            token_data['purchases'].append(purchase)
            
            # Add wallet score
            wallet_score = wallet_scores.get(purchase.wallet_address, 0)
            token_data['wallet_scores'].append(wallet_score)
            
            # Get contract address from web3_analysis
            if purchase.web3_analysis and purchase.web3_analysis.get('contract_address'):
                token_data['contract_address'] = purchase.web3_analysis['contract_address']
            
            total_eth_spent += purchase.eth_spent
        
        # Calculate final metrics and rank tokens
        ranked_tokens = []
        for token, data in token_summary.items():
            wallet_count = len(data['wallets'])
            eth_spent = data['total_eth_spent']
            
            # Calculate average wallet score
            if data['wallet_scores']:
                data['avg_wallet_score'] = sum(data['wallet_scores']) / len(data['wallet_scores'])
            
            # FIXED: More reasonable alpha score calculation
            # Base score on: wallet count * ETH spent, with wallet quality multiplier
            base_score = (wallet_count * 10) + (eth_spent * 100)
            wallet_quality_multiplier = 1 + (data['avg_wallet_score'] / 100)  # 1.0 to 2.0 multiplier
            alpha_score = base_score * wallet_quality_multiplier
            
            # Convert sets to lists for serialization
            data['wallets'] = list(data['wallets'])
            data['platforms'] = list(data['platforms'])
            data['wallet_count'] = wallet_count
            
            # Remove purchases from final data (too much data for API)
            del data['purchases']
            del data['wallet_scores']
            
            ranked_tokens.append((token, data, alpha_score))
        
        # Sort by alpha score
        ranked_tokens.sort(key=lambda x: x[2], reverse=True)
        
        # Build platform summary
        platform_summary = {}
        for purchase in purchases:
            platform = purchase.platform
            platform_summary[platform] = platform_summary.get(platform, 0) + 1
        
        logger.info(f"📊 Final results: {len(purchases)} purchases, {len(token_summary)} tokens, {total_eth_spent:.4f} ETH total")
        
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
                'method_summary': platform_summary
            },
            web3_enhanced=False
        )
    
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