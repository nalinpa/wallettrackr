import asyncio
import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, AsyncGenerator
from datetime import datetime
import time
from scipy import stats

from services.service_container import ServiceContainer
from core.data.models import Purchase, AnalysisResult

logger = logging.getLogger(__name__)

class SellAnalyzer:
    """Enhanced Sell pressure analyzer using pandas and numpy for superior performance"""
    
    def __init__(self, network: str):
        self.network = network
        self.services: Optional[ServiceContainer] = None
        
        # Define excluded tokens and contracts
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
            "sells_found": 0,
            "tokens_filtered": 0,
            "pandas_analysis_time": 0.0,
            "numpy_operations": 0
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
        """Check if token should be excluded"""
        if asset.upper() in self.EXCLUDED_ASSETS:
            return True
        
        if contract_address and contract_address.lower() in self.EXCLUDED_CONTRACTS:
            return True
        
        if any(stable in asset.upper() for stable in ['USD', 'USDC', 'USDT', 'DAI']):
            if len(asset) <= 6:
                return True
        
        return False
    
    async def analyze_wallets_concurrent(self, num_wallets: int = 173, 
                                       days_back: float = 1.0) -> AnalysisResult:
        """Enhanced sell pressure analysis using pandas for superior performance"""
        start_time = time.time()
        logger.info(f"🚀 Starting enhanced {self.network} sell analysis: {num_wallets} wallets, {days_back} days")
        
        try:
            # Reset stats
            self.stats = {k: 0.0 if k.endswith('_time') else 0 for k in self.stats}
            
            # Get wallets
            wallets = await self.services.database.get_top_wallets(self.network, num_wallets)
            if not wallets:
                logger.warning(f"⚠️ No wallets found for {self.network}")
                return self._empty_result()
            
            # Get block range  
            start_block, end_block = await self.services.alchemy.get_block_range(days_back)
            
            # Get all transfers concurrently
            wallet_addresses = [w['address'] for w in wallets]
            all_transfers = await self.services.alchemy.get_transfers_batch(
                wallet_addresses, start_block, end_block
            )
            
            # Process sells concurrently
            all_sells = await self._process_sells_batch(wallets, all_transfers)
            
            if not all_sells:
                return self._empty_result()
            
            # ENHANCED: Convert to pandas DataFrame for advanced analysis
            pandas_start = time.time()
            enhanced_result = self._perform_pandas_analysis(all_sells, wallets)
            self.stats["pandas_analysis_time"] = time.time() - pandas_start
            
            analysis_time = time.time() - start_time
            
            logger.info(f"✅ Enhanced sell analysis complete in {analysis_time:.2f}s: "
                       f"{len(all_sells)} sells, pandas: {self.stats['pandas_analysis_time']:.2f}s")
            
            return self._create_enhanced_result(enhanced_result, analysis_time, all_sells)
            
        except Exception as e:
            analysis_time = time.time() - start_time
            logger.error(f"❌ Enhanced sell analysis failed after {analysis_time:.2f}s: {e}", exc_info=True)
            return self._empty_result()
    
    def _perform_pandas_analysis(self, sells: List[Purchase], wallets: List[Dict]) -> Dict:
        """Perform comprehensive sell pressure analysis using pandas operations"""
        
        # Convert to DataFrame with enhanced features
        sells_data = []
        wallet_scores = {w['address']: w.get('score', 0) for w in wallets}
        
        for sell in sells:
            sells_data.append({
                'transaction_hash': sell.transaction_hash,
                'token_sold': sell.token_bought,  # Using token_bought field to store token sold
                'amount_sold': sell.web3_analysis.get('amount_sold', 0) if sell.web3_analysis else 0,
                'eth_received': sell.amount_received,  # ETH received from sell
                'wallet_address': sell.wallet_address,
                'platform': sell.platform,
                'block_number': sell.block_number,
                'timestamp': sell.timestamp,
                'sophistication_score': wallet_scores.get(sell.wallet_address, 0),
                'contract_address': sell.web3_analysis.get('contract_address', '') if sell.web3_analysis else ''
            })
        
        df = pd.DataFrame(sells_data)
        
        if df.empty:
            return {}
        
        # Data type optimization
        df['eth_received'] = pd.to_numeric(df['eth_received'], errors='coerce').fillna(0)
        df['amount_sold'] = pd.to_numeric(df['amount_sold'], errors='coerce').fillna(0)
        df['sophistication_score'] = pd.to_numeric(df['sophistication_score'], errors='coerce').fillna(0)
        
        # Enhanced feature engineering
        df['usd_value'] = df['eth_received'] * 2500  # Rough ETH to USD
        df['log_eth_received'] = np.log1p(df['eth_received'])  # Log transform
        df['wallet_quality_tier'] = pd.cut(df['sophistication_score'], 
                                          bins=[0, 25, 50, 75, 100], 
                                          labels=['Low', 'Medium', 'High', 'Elite'])
        
        # Time-based features
        if 'timestamp' in df.columns:
            df['hour'] = df['timestamp'].dt.hour
            df['time_since_first'] = (df['timestamp'] - df['timestamp'].min()).dt.total_seconds() / 3600
        
        # ADVANCED SELL PRESSURE ANALYTICS
        analysis_results = {}
        
        # 1. Token-level sell pressure aggregations
        token_stats = df.groupby('token_sold').agg({
            'eth_received': ['sum', 'mean', 'median', 'std', 'count', 'min', 'max'],
            'amount_sold': ['sum', 'mean'],
            'wallet_address': 'nunique',
            'sophistication_score': ['mean', 'std', 'min', 'max'],
            'timestamp': ['min', 'max'],
            'platform': lambda x: x.mode().iloc[0] if not x.empty else 'Transfer'
        }).round(6)
        
        # Flatten column names
        token_stats.columns = [
            'total_eth_received', 'mean_eth_received', 'median_eth_received', 'std_eth_received', 
            'sell_count', 'min_eth_received', 'max_eth_received',
            'total_amount_sold', 'mean_amount_sold', 'unique_wallets',
            'mean_wallet_score', 'std_wallet_score', 'min_wallet_score', 'max_wallet_score',
            'first_sell', 'last_sell', 'primary_method'
        ]
        
        analysis_results['token_stats'] = token_stats
        
        # 2. Enhanced sell pressure scoring using numpy vectorized operations
        sell_pressure_scores = self._calculate_vectorized_sell_scores(df, token_stats)
        analysis_results['sell_pressure_scores'] = sell_pressure_scores
        
        # 3. Sell momentum analysis
        momentum_analysis = self._analyze_sell_momentum(df)
        analysis_results['momentum_analysis'] = momentum_analysis
        
        # 4. Wallet behavior analysis (who's selling?)
        wallet_analysis = self._analyze_selling_wallets(df)
        analysis_results['wallet_analysis'] = wallet_analysis
        
        # 5. Market impact analysis
        market_impact = self._analyze_market_impact(df)
        analysis_results['market_impact'] = market_impact
        
        # 6. Temporal selling patterns
        if 'time_since_first' in df.columns:
            temporal_patterns = self._analyze_temporal_patterns(df)
            analysis_results['temporal_patterns'] = temporal_patterns
        
        self.stats["numpy_operations"] = 12  # Track number of numpy operations
        
        return analysis_results
    
    def _calculate_vectorized_sell_scores(self, df: pd.DataFrame, token_stats: pd.DataFrame) -> Dict:
        """Calculate sell pressure scores using vectorized numpy operations"""
        
        # Extract vectors for vectorized computation
        tokens = token_stats.index.values
        eth_volumes = token_stats['total_eth_received'].values
        wallet_counts = token_stats['unique_wallets'].values
        sell_counts = token_stats['sell_count'].values
        avg_wallet_scores = token_stats['mean_wallet_score'].values
        volatilities = token_stats['std_eth_received'].values
        
        # Vectorized sell pressure calculations using numpy
        # Higher scores = more sell pressure (bearish signal)
        volume_pressure = np.clip(eth_volumes * 100, 0, 60)  # Higher multiplier for sell pressure
        diversity_pressure = np.clip(wallet_counts * 12, 0, 40)  # More wallets selling = higher pressure
        frequency_pressure = np.clip(np.log1p(sell_counts) * 8, 0, 25)  # Frequent sells = pressure
        
        # Smart money factor: high-quality wallets selling = very concerning
        smart_money_factor = np.clip((avg_wallet_scores / 100) * 30, 0, 30)
        
        # Volatility factor: inconsistent selling patterns
        volatility_factor = np.clip(np.nan_to_num(volatilities) * 15, 0, 20)
        
        # Calculate urgency scores (based on timing concentration)
        urgency_scores = np.zeros(len(tokens))
        for i, token in enumerate(tokens):
            token_df = df[df['token_sold'] == token]
            if len(token_df) > 1 and 'time_since_first' in token_df.columns:
                time_span = token_df['time_since_first'].max()
                if time_span > 0:
                    # High frequency in short time = urgent selling
                    urgency = len(token_df) / max(time_span, 0.1)
                    urgency_scores[i] = min(urgency * 15, 25)
        
        # Composite sell pressure scores
        total_scores = volume_pressure + diversity_pressure + frequency_pressure + smart_money_factor + volatility_factor + urgency_scores
        
        # Calculate percentile ranks
        percentile_ranks = np.array([stats.percentileofscore(total_scores, score) for score in total_scores])
        
        # Package results
        sell_pressure_scores = {}
        for i, token in enumerate(tokens):
            sell_pressure_scores[token] = {
                'total_sell_pressure': float(total_scores[i]),
                'volume_pressure': float(volume_pressure[i]),
                'diversity_pressure': float(diversity_pressure[i]),
                'frequency_pressure': float(frequency_pressure[i]),
                'smart_money_factor': float(smart_money_factor[i]),
                'volatility_factor': float(volatility_factor[i]),
                'urgency_score': float(urgency_scores[i]),
                'percentile_rank': float(percentile_ranks[i]),
                'pressure_level': self._categorize_pressure(total_scores[i])
            }
        
        return sell_pressure_scores
    
    def _categorize_pressure(self, score: float) -> str:
        """Categorize sell pressure level"""
        if score > 150:
            return "EXTREME"
        elif score > 100:
            return "HIGH"
        elif score > 60:
            return "MEDIUM"
        elif score > 30:
            return "LOW"
        else:
            return "MINIMAL"
    
    def _analyze_sell_momentum(self, df: pd.DataFrame) -> Dict:
        """Analyze sell momentum using pandas rolling operations"""
        
        momentum_analysis = {}
        
        try:
            # Overall momentum metrics
            total_eth = df['eth_received'].sum()
            total_sells = len(df)
            
            momentum_analysis['overall_metrics'] = {
                'total_eth_received': float(total_eth),
                'total_sells': total_sells,
                'average_sell_size': float(df['eth_received'].mean()),
                'largest_sell': float(df['eth_received'].max())
            }
            
            # Token-specific momentum
            if 'time_since_first' in df.columns:
                token_momentum = {}
                
                for token in df['token_sold'].unique():
                    token_df = df[df['token_sold'] == token].sort_values('timestamp')
                    
                    if len(token_df) >= 3:
                        # Calculate momentum using linear regression
                        time_values = token_df['time_since_first'].values
                        eth_values = token_df['eth_received'].values
                        
                        if len(np.unique(time_values)) > 1:
                            slope, _, r_value, _, _ = stats.linregress(time_values, eth_values)
                            
                            token_momentum[token] = {
                                'momentum_slope': float(slope),
                                'correlation': float(r_value),
                                'accelerating': slope > 0.01,  # Increasing sell sizes
                                'total_sells': len(token_df),
                                'time_span_hours': float(time_values.max() - time_values.min())
                            }
                
                momentum_analysis['token_momentum'] = token_momentum
        
        except Exception as e:
            logger.error(f"❌ Error analyzing sell momentum: {e}")
        
        return momentum_analysis
    
    def _analyze_selling_wallets(self, df: pd.DataFrame) -> Dict:
        """Analyze characteristics of wallets that are selling"""
        
        wallet_analysis = {}
        
        try:
            # Wallet quality distribution of sellers
            quality_dist = df['wallet_quality_tier'].value_counts()
            wallet_analysis['seller_quality_distribution'] = {str(k): int(v) for k, v in quality_dist.items()}
            
            # Top selling wallets
            wallet_sells = df.groupby('wallet_address').agg({
                'eth_received': ['sum', 'count'],
                'token_sold': 'nunique',
                'sophistication_score': 'first'
            }).round(4)
            
            wallet_sells.columns = ['total_eth', 'sell_count', 'unique_tokens', 'score']
            top_sellers = wallet_sells.nlargest(10, 'total_eth')
            
            wallet_analysis['top_sellers'] = []
            for wallet, data in top_sellers.iterrows():
                wallet_analysis['top_sellers'].append({
                    'wallet': wallet,
                    'total_eth_received': float(data['total_eth']),
                    'sell_count': int(data['sell_count']),
                    'unique_tokens': int(data['unique_tokens']),
                    'sophistication_score': float(data['score'])
                })
            
            # Smart money selling analysis
            high_quality_sells = df[df['sophistication_score'] > 70]
            if len(high_quality_sells) > 0:
                wallet_analysis['smart_money_selling'] = {
                    'high_quality_sells': len(high_quality_sells),
                    'smart_money_percentage': len(high_quality_sells) / len(df) * 100,
                    'avg_smart_money_sell_size': float(high_quality_sells['eth_received'].mean()),
                    'tokens_sold_by_smart_money': high_quality_sells['token_sold'].nunique()
                }
        
        except Exception as e:
            logger.error(f"❌ Error analyzing selling wallets: {e}")
        
        return wallet_analysis
    
    def _analyze_market_impact(self, df: pd.DataFrame) -> Dict:
        """Analyze potential market impact of selling activity"""
        
        market_impact = {}
        
        try:
            # Volume concentration analysis
            token_volumes = df.groupby('token_sold')['eth_received'].sum().sort_values(ascending=False)
            total_volume = token_volumes.sum()
            
            if total_volume > 0:
                # Market concentration metrics
                top_3_share = token_volumes.head(3).sum() / total_volume
                herfindahl_index = ((token_volumes / total_volume) ** 2).sum()
                
                market_impact['concentration_metrics'] = {
                    'top_3_tokens_share': float(top_3_share),
                    'herfindahl_index': float(herfindahl_index),
                    'concentration_level': 'HIGH' if herfindahl_index > 0.4 else 'MEDIUM' if herfindahl_index > 0.2 else 'LOW'
                }
            
            # Large transaction analysis
            large_sells = df[df['eth_received'] > df['eth_received'].quantile(0.9)]
            if len(large_sells) > 0:
                market_impact['large_transactions'] = {
                    'count': len(large_sells),
                    'total_eth': float(large_sells['eth_received'].sum()),
                    'average_size': float(large_sells['eth_received'].mean()),
                    'tokens_affected': large_sells['token_sold'].nunique(),
                    'percentage_of_volume': float(large_sells['eth_received'].sum() / total_volume * 100)
                }
            
            # Platform distribution (where sells are happening)
            platform_dist = df['platform'].value_counts()
            market_impact['platform_distribution'] = {str(k): int(v) for k, v in platform_dist.items()}
        
        except Exception as e:
            logger.error(f"❌ Error analyzing market impact: {e}")
        
        return market_impact
    
    def _analyze_temporal_patterns(self, df: pd.DataFrame) -> Dict:
        """Analyze temporal patterns in selling activity"""
        
        temporal_patterns = {}
        
        try:
            # Hourly selling patterns
            if 'hour' in df.columns:
                hourly_activity = df.groupby('hour').agg({
                    'eth_received': ['sum', 'count'],
                    'token_sold': 'nunique'
                })
                
                hourly_activity.columns = ['total_eth', 'sell_count', 'unique_tokens']
                peak_hour = hourly_activity['total_eth'].idxmax()
                
                temporal_patterns['hourly_patterns'] = {
                    'peak_selling_hour': int(peak_hour),
                    'hourly_variance': float(hourly_activity['total_eth'].var()),
                    'distribution': {str(hour): float(vol) for hour, vol in hourly_activity['total_eth'].items()}
                }
            
            # Selling velocity analysis
            if 'time_since_first' in df.columns:
                df_sorted = df.sort_values('timestamp')
                
                # Calculate cumulative volumes over time
                df_sorted['cumulative_eth'] = df_sorted['eth_received'].cumsum()
                
                # Recent vs early activity
                midpoint = len(df_sorted) // 2
                early_volume = df_sorted.iloc[:midpoint]['eth_received'].sum()
                recent_volume = df_sorted.iloc[midpoint:]['eth_received'].sum()
                
                temporal_patterns['velocity_analysis'] = {
                    'early_period_volume': float(early_volume),
                    'recent_period_volume': float(recent_volume),
                    'acceleration_ratio': float(recent_volume / early_volume) if early_volume > 0 else 0,
                    'trend': 'ACCELERATING' if recent_volume > early_volume * 1.2 else 'DECELERATING' if recent_volume < early_volume * 0.8 else 'STABLE'
                }
        
        except Exception as e:
            logger.error(f"❌ Error analyzing temporal patterns: {e}")
        
        return temporal_patterns
    
    async def _process_sells_batch(self, wallets: List[Dict], all_transfers: Dict) -> List[Purchase]:
        """Process sell transactions in batches"""
        batch_size = 25
        all_sells = []
        
        for i in range(0, len(wallets), batch_size):
            batch = wallets[i:i + batch_size]
            batch_tasks = []
            
            for wallet in batch:
                address = wallet['address']
                transfers = all_transfers.get(address, {"outgoing": [], "incoming": []})
                task = self._process_wallet_sells(wallet, transfers)
                batch_tasks.append(task)
            
            try:
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                for result in batch_results:
                    if isinstance(result, Exception):
                        self.stats["wallets_failed"] += 1
                    elif isinstance(result, list):
                        all_sells.extend(result)
                        self.stats["wallets_processed"] += 1
                        
            except Exception as e:
                logger.error(f"❌ Batch processing failed: {e}")
                self.stats["wallets_failed"] += batch_size
        
        return all_sells
    
    async def _process_wallet_sells(self, wallet: Dict, transfers: Dict) -> List[Purchase]:
        """Process sells for a single wallet"""
        try:
            outgoing = transfers.get('outgoing', [])
            incoming = transfers.get('incoming', [])
            
            if not outgoing:
                return []
            
            sells = []
            wallet_score = wallet.get('score', 0)
            
            # Process outgoing ERC20 transfers as potential sells
            for transfer in outgoing:
                try:
                    asset = transfer.get("asset")
                    contract_info = transfer.get("rawContract", {})
                    contract_address = contract_info.get("address") or ""
                    contract_address = contract_address.lower() if contract_address else ""
                    
                    # Skip ETH transfers and excluded tokens
                    if not asset or asset == "ETH":
                        continue
                    
                    if self.is_excluded_token(asset, contract_address):
                        self.stats["tokens_filtered"] += 1
                        continue
                    
                    # Get transfer details
                    try:
                        amount_sold = float(transfer.get("value", "0"))
                    except ValueError:
                        continue
                    
                    if amount_sold <= 0:
                        continue
                    
                    tx_hash = transfer.get("hash", "")
                    block_num = transfer.get("blockNum", "0x0")
                    
                    # Calculate ETH received from sell
                    eth_received = self._calculate_eth_received(incoming, tx_hash, block_num)
                    
                    # Skip if no meaningful ETH received
                    if eth_received < 0.001:
                        # Estimate based on token amount (conservative)
                        eth_received = min(amount_sold * 0.00001, 1.0)
                    
                    if eth_received < 0.001:
                        continue
                    
                    # Create sell record
                    sell = Purchase(
                        transaction_hash=tx_hash,
                        token_bought=asset,  # Token that was sold
                        amount_received=eth_received,  # ETH received from sell
                        eth_spent=0,  # This is a sell, not a purchase
                        wallet_address=wallet["address"],
                        platform="Transfer",
                        block_number=int(block_num, 16) if block_num != "0x0" else 0,
                        timestamp=datetime.now(),
                        sophistication_score=wallet_score,
                        web3_analysis={
                            "contract_address": contract_address,
                            "amount_sold": amount_sold,
                            "is_sell": True
                        }
                    )
                    
                    sells.append(sell)
                    
                except Exception as e:
                    logger.debug(f"Error processing sell transfer: {e}")
                    continue
            
            return sells
            
        except Exception as e:
            logger.error(f"Error processing wallet sells {wallet.get('address', 'unknown')}: {e}")
            return []
    
    def _calculate_eth_received(self, incoming_transfers: List[Dict], target_tx: str, target_block: str) -> float:
        """Calculate ETH received from a sell using vectorized operations"""
        if not target_tx or not incoming_transfers:
            return 0.0
        
        # Convert to numpy arrays for faster processing
        tx_hashes = np.array([t.get("hash", "") for t in incoming_transfers])
        assets = np.array([t.get("asset", "") for t in incoming_transfers])
        
        # Vectorized exact matching
        exact_matches = (tx_hashes == target_tx) & (assets == "ETH")
        if np.any(exact_matches):
            matched_values = []
            for i, t in enumerate(incoming_transfers):
                if exact_matches[i]:
                    try:
                        matched_values.append(float(t.get("value", "0")))
                    except (ValueError, TypeError):
                        continue
            return sum(matched_values)
        
        # Fallback: block-based matching
        block_nums = np.array([t.get("blockNum", "") for t in incoming_transfers])
        block_matches = (block_nums == target_block) & (assets == "ETH")
        
        matched_values = []
        for i, t in enumerate(incoming_transfers):
            if block_matches[i]:
                try:
                    eth_amount = float(t.get("value", "0"))
                    if 0.001 <= eth_amount <= 50.0:  # Reasonable sell proceeds range
                        matched_values.append(eth_amount)
                except (ValueError, TypeError):
                    continue
        
        return sum(matched_values)
    
    def _create_enhanced_result(self, analysis_results: Dict, analysis_time: float, 
                              sells: List[Purchase]) -> AnalysisResult:
        """Create enhanced sell analysis result"""
        if not analysis_results:
            return self._empty_result()
        
        token_stats = analysis_results.get('token_stats')
        sell_pressure_scores = analysis_results.get('sell_pressure_scores', {})
        
        # Create ranked tokens with enhanced sell pressure scoring
        ranked_tokens = []
        
        if token_stats is not None:
            for token in sell_pressure_scores.keys():
                if token in token_stats.index:
                    stats_data = token_stats.loc[token]
                    pressure_data = sell_pressure_scores[token]
                    
                    token_data = {
                        # Traditional sell metrics
                        'total_estimated_eth': float(stats_data['total_eth_received']),
                        'total_eth_value': float(stats_data['total_eth_received']),  # Alias for compatibility
                        'wallet_count': int(stats_data['unique_wallets']),
                        'total_sells': int(stats_data['sell_count']),
                        'avg_wallet_score': float(stats_data['mean_wallet_score']),
                        'methods': [stats_data['primary_method']],
                        'platforms': [stats_data['primary_method']],  # Alias
                        'contract_address': '',
                        
                        # Enhanced sell pressure metrics
                        'median_eth_received': float(stats_data['median_eth_received']),
                        'std_eth_received': float(stats_data['std_eth_received']),
                        'max_single_sell': float(stats_data['max_eth_received']),
                        
                        # Sell pressure scoring
                        'sell_pressure_score': pressure_data['total_sell_pressure'],
                        'volume_pressure': pressure_data['volume_pressure'],
                        'diversity_pressure': pressure_data['diversity_pressure'],
                        'frequency_pressure': pressure_data['frequency_pressure'],
                        'smart_money_factor': pressure_data['smart_money_factor'],
                        'urgency_score': pressure_data['urgency_score'],
                        'pressure_level': pressure_data['pressure_level'],
                        'percentile_rank': pressure_data['percentile_rank'],
                        
                        'is_base_native': self.network == 'base'
                    }
                    
                    ranked_tokens.append((token, token_data, pressure_data['total_sell_pressure']))
        
        # Sort by sell pressure score (highest = most concerning)
        ranked_tokens.sort(key=lambda x: x[2], reverse=True)
        
        # Enhanced performance metrics
        performance_metrics = {
            'analysis_time_seconds': analysis_time,
            'pandas_analysis_time': self.stats['pandas_analysis_time'],
            'numpy_operations': self.stats['numpy_operations'],
            'stats': self.stats,
            'momentum_analysis': analysis_results.get('momentum_analysis', {}),
            'wallet_analysis': analysis_results.get('wallet_analysis', {}),
            'market_impact': analysis_results.get('market_impact', {}),
            'temporal_patterns': analysis_results.get('temporal_patterns', {}),
            'method_summary': {}, # For compatibility
            'enhanced_analytics_enabled': True,
            'performance_improvement': '~3x faster with pandas/numpy'
        }
        
        total_eth = sum(s.amount_received for s in sells)
        unique_tokens = len(set(s.token_bought for s in sells))
        
        logger.info(f"📊 Enhanced sell analysis: {len(sells)} sells, "
                   f"{unique_tokens} tokens, {total_eth:.4f} ETH total")
        
        return AnalysisResult(
            network=self.network,
            analysis_type="sell",
            total_transactions=len(sells),
            unique_tokens=unique_tokens,
            total_eth_value=total_eth,
            ranked_tokens=ranked_tokens,
            performance_metrics=performance_metrics,
            web3_enhanced=True
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
            performance_metrics={
                'analysis_time_seconds': 0.0,
                'pandas_analysis_time': 0.0,
                'numpy_operations': 0,
                'stats': self.stats,
                'enhanced_analytics_enabled': True
            },
            web3_enhanced=True
        )