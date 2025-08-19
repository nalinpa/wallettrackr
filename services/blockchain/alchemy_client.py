import asyncio
import httpx
import orjson
import logging
from typing import List, Dict, Optional, Tuple, Union
from datetime import datetime
from config.settings import alchemy_config, NetworkConfig

logger = logging.getLogger(__name__)

class AlchemyClient:
    """Enhanced Alchemy blockchain API client with token metadata support"""
    
    def __init__(self, network: str):
        self.network = network
        self.network_config = NetworkConfig.get_config(network)
        self.base_url = self.network_config['alchemy_url']
        self._client: Optional[httpx.AsyncClient] = None
        self._request_count = 0
        self._rate_limiter = asyncio.Semaphore(20)
    
    async def __aenter__(self):
        """Initialize client"""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=25
            ),
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': f'CryptoAlpha-{self.network}/2.0'
            },
            http2=True
        )
        logger.info(f"✅ Alchemy client initialized for {self.network}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup client"""
        if self._client:
            await self._client.aclose()
            logger.info(f"🔒 Alchemy client closed for {self.network} ({self._request_count} requests)")
    
    async def make_request(self, method: str, params: List) -> Dict:
        """Make Alchemy API request with rate limiting"""
        async with self._rate_limiter:
            payload = {
                "id": self._request_count + 1,
                "jsonrpc": "2.0",
                "method": method,
                "params": params
            }
            
            try:
                self._request_count += 1
                
                response = await self._client.post(
                    self.base_url,
                    content=orjson.dumps(payload),
                    headers={'Content-Type': 'application/json'}
                )
                response.raise_for_status()
                
                return orjson.loads(response.content)
                
            except httpx.TimeoutException:
                logger.error(f"⏰ Timeout for {method} on {self.network}")
                return {}
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    await asyncio.sleep(1)  # Rate limit backoff
                logger.error(f"🔴 HTTP {e.response.status_code} error for {method}")
                return {}
            except Exception as e:
                logger.error(f"❌ Error for {method}: {e}")
                return {}
    
    async def get_block_number(self) -> int:
        """Get current block number"""
        result = await self.make_request("eth_blockNumber", [])
        if result.get("result"):
            return int(result["result"], 16)
        return 0
    
    async def get_block_range(self, days_back: float) -> Tuple[str, str]:
        """Get block range for time period"""
        current_block = await self.get_block_number()
        
        if current_block == 0:
            return "0x0", "0x0"
        
        blocks_per_day = self.network_config.get('blocks_per_day', 7200)
        blocks_back = int(days_back * blocks_per_day)
        start_block = max(0, current_block - blocks_back)
        
        return hex(start_block), hex(current_block)
    
    # TOKEN METADATA METHODS
    
    async def get_token_metadata(self, contract_address: str) -> Dict:
        """Get token metadata including name, symbol, decimals, etc."""
        try:
            logger.info(f"📊 Getting token metadata for {contract_address}")
            
            result = await self.make_request("alchemy_getTokenMetadata", [contract_address])
            
            if result.get("result"):
                metadata = result["result"]
                logger.info(f"✅ Got metadata for {metadata.get('symbol', 'Unknown')}")
                return metadata
            else:
                logger.warning(f"⚠️ No metadata returned for {contract_address}")
                return {}
                
        except Exception as e:
            logger.error(f"❌ Error getting token metadata: {e}")
            return {}
    
    async def get_token_balances(self, address: str, token_addresses: List[str] = None) -> Dict:
        """Get token balances for an address"""
        try:
            if token_addresses:
                # Get balances for specific tokens
                params = [address, token_addresses]
                method = "alchemy_getTokenBalances"
            else:
                # Get all token balances
                params = [address]
                method = "alchemy_getTokenBalances"
            
            result = await self.make_request(method, params)
            
            if result.get("result"):
                return result["result"]
            else:
                return {"address": address, "tokenBalances": []}
                
        except Exception as e:
            logger.error(f"❌ Error getting token balances: {e}")
            return {"address": address, "tokenBalances": []}
    
    async def get_token_transfers_for_owner(self, address: str, contract_address: str = None, 
                                          from_block: str = None, to_block: str = None) -> List[Dict]:
        """Get token transfers for a specific owner"""
        try:
            # Build parameters
            params = {
                "fromAddress": address,
                "category": ["erc20"]
            }
            
            if contract_address:
                params["contractAddresses"] = [contract_address]
            
            if from_block:
                params["fromBlock"] = from_block
            if to_block:
                params["toBlock"] = to_block
            
            params["withMetadata"] = True
            params["excludeZeroValue"] = True
            params["maxCount"] = "0x64"  # 100 transfers max
            
            result = await self.make_request("alchemy_getAssetTransfers", [params])
            
            if result.get("result"):
                return result["result"].get("transfers", [])
            else:
                return []
                
        except Exception as e:
            logger.error(f"❌ Error getting token transfers: {e}")
            return []
    
    async def get_token_transfers_for_contract(self, contract_address: str, 
                                             from_block: str = None, to_block: str = None) -> List[Dict]:
        """Get all transfers for a specific token contract"""
        try:
            params = {
                "contractAddresses": [contract_address],
                "category": ["erc20"],
                "withMetadata": True,
                "excludeZeroValue": True,
                "maxCount": "0x64"  # 100 transfers max
            }
            
            if from_block:
                params["fromBlock"] = from_block
            if to_block:
                params["toBlock"] = to_block
            
            result = await self.make_request("alchemy_getAssetTransfers", [params])
            
            if result.get("result"):
                return result["result"].get("transfers", [])
            else:
                return []
                
        except Exception as e:
            logger.error(f"❌ Error getting contract transfers: {e}")
            return []
    
    async def get_token_allowances(self, owner: str, spender: str, contract_address: str) -> str:
        """Get token allowance between owner and spender"""
        try:
            # ERC20 allowance method signature
            method_sig = "0xdd62ed3e"  # allowance(address,address)
            
            # Encode the parameters (owner and spender addresses)
            owner_padded = owner[2:].lower().zfill(64) if owner.startswith("0x") else owner.lower().zfill(64)
            spender_padded = spender[2:].lower().zfill(64) if spender.startswith("0x") else spender.lower().zfill(64)
            
            data = method_sig + owner_padded + spender_padded
            
            params = [{
                "to": contract_address,
                "data": data
            }, "latest"]
            
            result = await self.make_request("eth_call", params)
            
            if result.get("result"):
                # Convert hex result to decimal
                allowance = int(result["result"], 16)
                return str(allowance)
            else:
                return "0"
                
        except Exception as e:
            logger.error(f"❌ Error getting token allowance: {e}")
            return "0"
    
    async def get_token_total_supply(self, contract_address: str) -> str:
        """Get token total supply"""
        try:
            # ERC20 totalSupply method signature
            method_sig = "0x18160ddd"  # totalSupply()
            
            params = [{
                "to": contract_address,
                "data": method_sig
            }, "latest"]
            
            result = await self.make_request("eth_call", params)
            
            if result.get("result"):
                # Convert hex result to decimal
                total_supply = int(result["result"], 16)
                return str(total_supply)
            else:
                return "0"
                
        except Exception as e:
            logger.error(f"❌ Error getting total supply: {e}")
            return "0"
    
    async def get_token_balance(self, address: str, contract_address: str) -> str:
        """Get token balance for a specific address"""
        try:
            # ERC20 balanceOf method signature
            method_sig = "0x70a08231"  # balanceOf(address)
            
            # Encode the address parameter
            address_padded = address[2:].lower().zfill(64) if address.startswith("0x") else address.lower().zfill(64)
            data = method_sig + address_padded
            
            params = [{
                "to": contract_address,
                "data": data
            }, "latest"]
            
            result = await self.make_request("eth_call", params)
            
            if result.get("result"):
                # Convert hex result to decimal
                balance = int(result["result"], 16)
                return str(balance)
            else:
                return "0"
                
        except Exception as e:
            logger.error(f"❌ Error getting token balance: {e}")
            return "0"
    
    # ENHANCED TRANSFER METHODS
    
    async def get_transfers_batch(self, addresses: List[str], start_block: str, 
                                end_block: str) -> Dict[str, Dict]:
        """Get transfers for multiple addresses concurrently - MAIN PERFORMANCE BOOST"""
        logger.info(f"🚀 Batch processing {len(addresses)} addresses")
        
        # Create tasks for all addresses
        tasks = []
        for address in addresses:
            task = self._get_address_transfers(address, start_block, end_block)
            tasks.append((address, task))
        
        # Process in batches to avoid API limits
        batch_size = 6
        all_results = {}
        
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            
            # Execute batch concurrently
            batch_results = await asyncio.gather(
                *[task for _, task in batch], 
                return_exceptions=True
            )
            
            # Collect results
            for j, (address, _) in enumerate(batch):
                if not isinstance(batch_results[j], Exception):
                    all_results[address] = batch_results[j]
                else:
                    all_results[address] = {"outgoing": [], "incoming": []}
            
            # Brief pause between batches
            if i + batch_size < len(tasks):
                await asyncio.sleep(0.3)

        print(f"✅ Completed batch processing for {len(addresses)} addresses")
        return all_results
    
    async def get_token_transfers_batch(self, contract_addresses: List[str], 
                                      start_block: str, end_block: str) -> Dict[str, List[Dict]]:
        """Get transfers for multiple token contracts concurrently"""
        logger.info(f"🪙 Batch processing transfers for {len(contract_addresses)} tokens")
        
        # Create tasks for all contracts
        tasks = []
        for contract in contract_addresses:
            task = self.get_token_transfers_for_contract(contract, start_block, end_block)
            tasks.append((contract, task))
        
        # Process in smaller batches for token transfers
        batch_size = 4
        all_results = {}
        
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            
            # Execute batch concurrently
            batch_results = await asyncio.gather(
                *[task for _, task in batch], 
                return_exceptions=True
            )
            
            # Collect results
            for j, (contract, _) in enumerate(batch):
                if not isinstance(batch_results[j], Exception):
                    all_results[contract] = batch_results[j]
                else:
                    all_results[contract] = []
            
            # Brief pause between batches
            if i + batch_size < len(tasks):
                await asyncio.sleep(1.5)

        logger.info(f"✅ Completed token transfer batch processing for {len(contract_addresses)} contracts")
        return all_results
    
    async def _get_address_transfers(self, address: str, start_block: str, end_block: str) -> Dict[str, List]:
        """Get both outgoing and incoming transfers for an address"""
        # Create both requests concurrently
        outgoing_task = self._get_transfers_direction(address, start_block, end_block, "from")
        incoming_task = self._get_transfers_direction(address, start_block, end_block, "to")
        
        # Execute both concurrently
        outgoing, incoming = await asyncio.gather(outgoing_task, incoming_task, return_exceptions=True)
        
        return {
            "outgoing": outgoing if not isinstance(outgoing, Exception) else [],
            "incoming": incoming if not isinstance(incoming, Exception) else []
        }
    
    async def _get_transfers_direction(self, address: str, start_block: str, 
                                     end_block: str, direction: str) -> List[Dict]:
        """Get transfers in specific direction"""
        address_param = "fromAddress" if direction == "from" else "toAddress"
        
        params = [{
            address_param: address,
            "fromBlock": start_block,
            "toBlock": end_block,
            "category": ["external", "erc20"],
            "withMetadata": True,
            "excludeZeroValue": True,
            "maxCount": "0x32"
        }]
        
        result = await self.make_request("alchemy_getAssetTransfers", params)
        return result.get("result", {}).get("transfers", [])
    
    # UTILITY METHODS
    
    async def test_connection(self) -> bool:
        """Test connection"""
        try:
            current_block = await self.get_block_number()
            if current_block > 0:
                logger.info(f"✅ {self.network} connection OK - Block: {current_block}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ {self.network} connection failed: {e}")
            return False
    
    async def get_transaction_receipt(self, tx_hash: str) -> Dict:
        """Get transaction receipt"""
        try:
            result = await self.make_request("eth_getTransactionReceipt", [tx_hash])
            return result.get("result", {})
        except Exception as e:
            logger.error(f"❌ Error getting transaction receipt: {e}")
            return {}
    
    async def get_transaction(self, tx_hash: str) -> Dict:
        """Get transaction details"""
        try:
            result = await self.make_request("eth_getTransactionByHash", [tx_hash])
            return result.get("result", {})
        except Exception as e:
            logger.error(f"❌ Error getting transaction: {e}")
            return {}
    
    async def get_logs(self, contract_address: str, from_block: str = None, 
                      to_block: str = None, topics: List[str] = None) -> List[Dict]:
        """Get event logs for a contract"""
        try:
            params = {
                "address": contract_address
            }
            
            if from_block:
                params["fromBlock"] = from_block
            if to_block:
                params["toBlock"] = to_block
            if topics:
                params["topics"] = topics
            
            result = await self.make_request("eth_getLogs", [params])
            return result.get("result", [])
            
        except Exception as e:
            logger.error(f"❌ Error getting logs: {e}")
            return []
    
    async def get_block_by_number(self, block_number: Union[str, int], 
                                 include_txs: bool = False) -> Dict:
        """Get block details by number"""
        try:
            if isinstance(block_number, int):
                block_number = hex(block_number)
            
            result = await self.make_request("eth_getBlockByNumber", [block_number, include_txs])
            return result.get("result", {})
            
        except Exception as e:
            logger.error(f"❌ Error getting block: {e}")
            return {}
    
    async def get_gas_price(self) -> str:
        """Get current gas price"""
        try:
            result = await self.make_request("eth_gasPrice", [])
            return result.get("result", "0x0")
        except Exception as e:
            logger.error(f"❌ Error getting gas price: {e}")
            return "0x0"
    
    async def estimate_gas(self, transaction: Dict) -> str:
        """Estimate gas for a transaction"""
        try:
            result = await self.make_request("eth_estimateGas", [transaction])
            return result.get("result", "0x0")
        except Exception as e:
            logger.error(f"❌ Error estimating gas: {e}")
            return "0x0"