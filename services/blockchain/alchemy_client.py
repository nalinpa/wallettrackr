import asyncio
import httpx
import orjson
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from config.settings import alchemy_config, NetworkConfig

logger = logging.getLogger(__name__)

class AlchemyClient:
    """Alchemy blockchain API client with concurrent request support"""
    
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
                await asyncio.sleep(1)

        print(f"✅ Completed batch processing for {len(addresses)} addresses")
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