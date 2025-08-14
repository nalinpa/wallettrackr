from web3 import Web3
from typing import Dict, List, Optional, Tuple, Any
import logging
import time
import json
from datetime import datetime
from .tracker_utils import TokenUtils, ContractUtils, NetworkConfig
from config.settings import alchemy_config

logger = logging.getLogger(__name__)

class Web3Manager:
    """Manages Web3 connections for multiple networks"""
    
    def __init__(self):
        self.connections = {}
        self.supported_networks = ["ethereum", "base"]
    
    def get_web3(self, network: str) -> Web3:
        """Get or create Web3 connection for network"""
        if network not in self.connections:
            try:
                network_config = NetworkConfig.get_config(network)
                alchemy_url = network_config['alchemy_url']
                
                self.connections[network] = Web3(Web3.HTTPProvider(
                    alchemy_url,
                    request_kwargs={'timeout': alchemy_config.timeout_seconds}
                ))
                
                # Verify connection
                if self.connections[network].is_connected():
                    current_block = self.connections[network].eth.block_number
                    logger.info(f"✅ Connected to {network} via Web3 - Block: {current_block}")
                else:
                    raise ConnectionError(f"Failed to connect to {network}")
                    
            except Exception as e:
                logger.error(f"❌ Failed to create Web3 connection for {network}: {e}")
                raise
        
        return self.connections[network]
    
    def test_all_connections(self) -> Dict[str, bool]:
        """Test all network connections"""
        results = {}
        for network in self.supported_networks:
            try:
                w3 = self.get_web3(network)
                results[network] = w3.is_connected()
            except Exception as e:
                logger.error(f"Connection test failed for {network}: {e}")
                results[network] = False
        
        return results

class EnhancedTransactionAnalyzer:
    """Enhanced transaction analysis using Web3"""
    
    def __init__(self, network: str, web3_manager: Web3Manager):
        self.network = network
        self.web3_manager = web3_manager
        self.w3 = web3_manager.get_web3(network)
        self.min_eth_value = NetworkConfig.get_min_eth_value(network)
    
    def get_transaction_details(self, tx_hash: str) -> Dict[str, Any]:
        """Get detailed transaction information"""
        try:
            # Get transaction and receipt
            tx = self.w3.eth.get_transaction(tx_hash)
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            
            # Calculate gas efficiency
            gas_price_gwei = self.w3.from_wei(tx['gasPrice'], 'gwei')
            gas_used = receipt['gasUsed']
            total_gas_cost_eth = self.w3.from_wei(tx['gasPrice'] * gas_used, 'ether')
            
            # Analyze transaction input
            input_analysis = self._analyze_transaction_input(tx['input'])
            
            return {
                'hash': tx_hash,
                'from': tx['from'],
                'to': tx['to'],
                'value_eth': float(self.w3.from_wei(tx['value'], 'ether')),
                'gas_price_gwei': float(gas_price_gwei),
                'gas_limit': tx['gas'],
                'gas_used': gas_used,
                'gas_efficiency': gas_used / tx['gas'] if tx['gas'] > 0 else 0,
                'total_gas_cost_eth': float(total_gas_cost_eth),
                'block_number': tx['blockNumber'],
                'transaction_index': tx['transactionIndex'],
                'success': receipt['status'] == 1,
                'contract_creation': tx['to'] is None,
                'input_analysis': input_analysis,
                'logs_count': len(receipt['logs']),
                'timestamp': self._get_block_timestamp(tx['blockNumber'])
            }
            
        except Exception as e:
            logger.error(f"Error getting transaction details for {tx_hash}: {e}")
            return {}
    
    def _analyze_transaction_input(self, input_data: str) -> Dict[str, Any]:
        """Analyze transaction input data"""
        if not input_data or input_data == '0x':
            return {'type': 'simple_transfer', 'method': None}
        
        try:
            # Get method signature (first 4 bytes)
            method_sig = input_data[:10]  # 0x + 8 hex chars
            
            # Common method signatures
            known_methods = {
                '0xa9059cbb': 'transfer',
                '0x23b872dd': 'transferFrom', 
                '0x095ea7b3': 'approve',
                '0x38ed1739': 'swapExactTokensForTokens',
                '0x7ff36ab5': 'swapExactETHForTokens',
                '0x18cbafe5': 'swapExactTokensForETH',
                '0x791ac947': 'swapExactTokensForTokensSupportingFeeOnTransferTokens',
                '0xb6f9de95': 'swapExactETHForTokensSupportingFeeOnTransferTokens',
                '0x5c11d795': 'swapExactTokensForETHSupportingFeeOnTransferTokens',
                '0x414bf389': 'exactInputSingle',  # Uniswap V3
                '0xc04b8d59': 'exactInput',  # Uniswap V3
                '0xdb3e2198': 'exactOutputSingle',  # Uniswap V3
                '0x09b81346': 'exactOutput'  # Uniswap V3
            }
            
            method_name = known_methods.get(method_sig, 'unknown')
            
            return {
                'type': 'contract_interaction',
                'method_signature': method_sig,
                'method_name': method_name,
                'is_swap': any(word in method_name.lower() for word in ['swap', 'exact']),
                'is_token_operation': any(word in method_name.lower() for word in ['transfer', 'approve']),
                'input_size_bytes': len(input_data) // 2 - 1,  # Remove 0x and convert to bytes
                'complexity_score': self._calculate_input_complexity(input_data)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing input data: {e}")
            return {'type': 'error', 'method': None}
    
    def _calculate_input_complexity(self, input_data: str) -> float:
        """Calculate complexity score based on input data"""
        if not input_data or input_data == '0x':
            return 0.0
        
        # Remove 0x prefix
        hex_data = input_data[2:]
        
        # Factors that indicate complexity
        length_score = len(hex_data) / 100  # Longer input = more complex
        unique_chars = len(set(hex_data)) / 16  # More unique hex chars = more complex
        zero_ratio = hex_data.count('0') / len(hex_data)  # Less zeros = more complex
        
        complexity = (length_score + unique_chars + (1 - zero_ratio)) / 3
        return min(complexity, 1.0)  # Cap at 1.0
    
    def _get_block_timestamp(self, block_number: int) -> int:
        """Get timestamp for a block"""
        try:
            block = self.w3.eth.get_block(block_number)
            return block['timestamp']
        except Exception as e:
            logger.error(f"Error getting block timestamp for {block_number}: {e}")
            return int(time.time())
    
    def analyze_address_activity(self, address: str, days_back: int = 1) -> Dict[str, Any]:
        """Analyze overall activity for an address"""
        try:
            # Current balance
            balance_wei = self.w3.eth.get_balance(address)
            balance_eth = float(self.w3.from_wei(balance_wei, 'ether'))
            
            # Transaction count
            tx_count = self.w3.eth.get_transaction_count(address)
            
            # Check if it's a contract
            code = self.w3.eth.get_code(address)
            is_contract = len(code) > 0
            
            # If it's a contract, get more details
            contract_info = {}
            if is_contract:
                contract_info = self._analyze_contract(address)
            
            return {
                'address': address,
                'balance_eth': balance_eth,
                'balance_wei': balance_wei,
                'transaction_count': tx_count,
                'is_contract': is_contract,
                'contract_info': contract_info,
                'activity_score': self._calculate_activity_score(balance_eth, tx_count),
                'last_analyzed': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing address {address}: {e}")
            return {}
    
    def _analyze_contract(self, address: str) -> Dict[str, Any]:
        """Analyze contract details"""
        try:
            code = self.w3.eth.get_code(address)
            code_size = len(code)
            
            # Use existing contract detection
            contract_info = ContractUtils.get_contract_info(address)
            
            return {
                'code_size_bytes': code_size,
                'detected_type': contract_info['type'],
                'detected_platform': contract_info['platform'],
                'detected_name': contract_info['name'],
                'complexity_score': min(code_size / 10000, 1.0)  # Normalized complexity
            }
            
        except Exception as e:
            logger.error(f"Error analyzing contract {address}: {e}")
            return {}
    
    def _calculate_activity_score(self, balance_eth: float, tx_count: int) -> float:
        """Calculate activity score for an address"""
        balance_score = min(balance_eth * 10, 50)  # Cap at 50
        tx_score = min(tx_count / 10, 30)  # Cap at 30
        return balance_score + tx_score
    
    def get_block_transactions(self, block_number: int, filter_significant: bool = True) -> List[Dict]:
        """Get all transactions from a block with analysis"""
        try:
            block = self.w3.eth.get_block(block_number, full_transactions=True)
            analyzed_txs = []
            
            for tx in block['transactions']:
                # Basic analysis
                tx_analysis = {
                    'hash': tx['hash'].hex(),
                    'from': tx['from'],
                    'to': tx['to'],
                    'value_eth': float(self.w3.from_wei(tx['value'], 'ether')),
                    'gas_price_gwei': float(self.w3.from_wei(tx['gasPrice'], 'gwei')),
                    'gas_limit': tx['gas']
                }
                
                # Filter for significant transactions
                if filter_significant:
                    if (tx_analysis['value_eth'] >= self.min_eth_value or 
                        tx['input'] != '0x'):  # Has input data
                        analyzed_txs.append(tx_analysis)
                else:
                    analyzed_txs.append(tx_analysis)
            
            logger.info(f"Analyzed {len(analyzed_txs)} significant transactions from block {block_number}")
            return analyzed_txs
            
        except Exception as e:
            logger.error(f"Error getting block transactions for {block_number}: {e}")
            return []

class Web3EnhancedTracker:
    """Enhanced tracker that combines existing functionality with Web3"""
    
    def __init__(self, network: str):
        self.network = network
        self.web3_manager = Web3Manager()
        self.tx_analyzer = EnhancedTransactionAnalyzer(network, self.web3_manager)
        self.w3 = self.web3_manager.get_web3(network)
    
    def enhanced_purchase_analysis(self, wallet_address: str, tx_hash: str, 
                                 basic_purchase: Dict) -> Dict:
        """Enhance basic purchase data with Web3 analysis"""
        try:
            # Get detailed transaction analysis
            tx_details = self.tx_analyzer.get_transaction_details(tx_hash)
            
            # Combine with basic purchase data
            enhanced_purchase = basic_purchase.copy()
            enhanced_purchase.update({
                'web3_analysis': {
                    'gas_efficiency': tx_details.get('gas_efficiency', 0),
                    'gas_cost_eth': tx_details.get('total_gas_cost_eth', 0),
                    'method_used': tx_details.get('input_analysis', {}).get('method_name', 'unknown'),
                    'is_swap': tx_details.get('input_analysis', {}).get('is_swap', False),
                    'complexity_score': tx_details.get('input_analysis', {}).get('complexity_score', 0),
                    'block_timestamp': tx_details.get('timestamp', 0)
                },
                'sophistication_score': self._calculate_sophistication_score(tx_details)
            })
            
            return enhanced_purchase
            
        except Exception as e:
            logger.error(f"Error enhancing purchase analysis: {e}")
            return basic_purchase
    
    def _calculate_sophistication_score(self, tx_details: Dict) -> float:
        """Calculate how sophisticated this transaction appears"""
        if not tx_details:
            return 0.0
        
        score = 0.0
        
        # Gas efficiency (lower gas usage = more sophisticated)
        gas_efficiency = tx_details.get('gas_efficiency', 0)
        if gas_efficiency > 0.9:  # Very efficient
            score += 20
        elif gas_efficiency > 0.7:
            score += 10
        
        # Method sophistication
        input_analysis = tx_details.get('input_analysis', {})
        if input_analysis.get('is_swap', False):
            score += 30  # Using DEX
        
        complexity = input_analysis.get('complexity_score', 0)
        score += complexity * 20  # More complex = more sophisticated
        
        # Gas price analysis (not overpaying = more sophisticated)
        gas_price_gwei = tx_details.get('gas_price_gwei', 0)
        if 5 <= gas_price_gwei <= 20:  # Reasonable gas price
            score += 15
        elif gas_price_gwei > 50:  # Overpaying
            score -= 10
        
        return min(score, 100)  # Cap at 100
    
    def analyze_wallet_sophistication(self, wallet_address: str) -> Dict:
        """Analyze overall wallet sophistication"""
        try:
            address_analysis = self.tx_analyzer.analyze_address_activity(wallet_address)
            
            sophistication_factors = {
                'balance_score': min(address_analysis.get('balance_eth', 0) * 5, 25),
                'activity_score': min(address_analysis.get('transaction_count', 0) / 20, 25),
                'is_contract': address_analysis.get('is_contract', False)
            }
            
            # Contract addresses get different scoring
            if sophistication_factors['is_contract']:
                contract_info = address_analysis.get('contract_info', {})
                contract_type = contract_info.get('detected_type', 'UNKNOWN')
                
                if contract_type in ['DEX', 'TELEGRAM_BOT']:
                    sophistication_factors['contract_bonus'] = 30
                else:
                    sophistication_factors['contract_bonus'] = 10
            else:
                sophistication_factors['contract_bonus'] = 0
            
            total_score = sum(sophistication_factors.values())
            
            return {
                'wallet_address': wallet_address,
                'sophistication_score': min(total_score, 100),
                'factors': sophistication_factors,
                'address_analysis': address_analysis,
                'classification': self._classify_wallet_sophistication(total_score)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing wallet sophistication: {e}")
            return {}
    
    def _classify_wallet_sophistication(self, score: float) -> str:
        """Classify wallet based on sophistication score"""
        if score >= 80:
            return "EXPERT"
        elif score >= 60:
            return "ADVANCED"
        elif score >= 40:
            return "INTERMEDIATE"
        elif score >= 20:
            return "BEGINNER"
        else:
            return "INACTIVE"
    
    def get_recent_block_range_web3(self, days_back: float = 1) -> Tuple[int, int]:
        """Get block range using Web3 (more reliable than hex conversion)"""
        try:
            current_block = self.w3.eth.block_number
            
            # Network-specific block times
            if self.network == "base":
                blocks_per_day = 43200  # ~2 second blocks
            else:
                blocks_per_day = 7200   # ~12 second blocks
            
            blocks_back = int(days_back * blocks_per_day)
            start_block = max(0, current_block - blocks_back)
            
            logger.info(f"{self.network} Web3 block range: {start_block} to {current_block}")
            return start_block, current_block
            
        except Exception as e:
            logger.error(f"Error getting Web3 block range: {e}")
            return 0, 0
    
    def test_web3_connection(self) -> bool:
        """Test Web3 connection"""
        try:
            if self.w3.is_connected():
                current_block = self.w3.eth.block_number
                logger.info(f"✅ Web3 connected to {self.network} - Block: {current_block}")
                return True
            else:
                logger.error(f"❌ Web3 not connected to {self.network}")
                return False
        except Exception as e:
            logger.error(f"❌ Web3 connection error for {self.network}: {e}")
            return False

# Global Web3 manager instance
web3_manager = Web3Manager()

def get_web3_for_network(network: str) -> Web3:
    """Convenience function to get Web3 instance"""
    return web3_manager.get_web3(network)

def test_all_web3_connections() -> Dict[str, bool]:
    """Test all Web3 connections"""
    return web3_manager.test_all_connections()