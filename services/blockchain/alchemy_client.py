import asyncio
import httpx
import orjson
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from config.settings import alchemy_config, NetworkConfig

logger = logging.getLogger(__name__)

class AlchemyClient:
    """Alchemy blockchain API client with better error handling and performance"""
    
    def __init__(self, network: str):
        self.network = network
        self.network_config = NetworkConfig.get_config(network)
        self.base_url = self.network_config['alchemy_url']
        self._client: Optional[httpx.AsyncClient] = None
        self._request_count = 0
        self._failures = 0
        self._rate_limiter = asyncio.Semaphore(15)  # Reduced to prevent rate limits
    
    async def __aenter__(self):
        """Initialize client with better connection pooling"""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(45.0, connect=10.0),  # Longer timeout, faster connect
            limits=httpx.Limits(
                max_connections=30,
                max_keepalive_connections=15
            ),
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': f'CryptoAlpha-{self.network}/2.0'
            }
        )
        logger.info(f"✅ Alchemy client initialized for {self.network}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup client with stats"""
        if self._client:
            await self._client.aclose()
            success_rate = ((self._request_count - self._failures) / max(self._request_count, 1)) * 100
            logger.info(f"🔒 Alchemy client closed for {self.network}: "
                       f"{self._request_count} requests, {success_rate:.1f}% success")
    
    async def make_request(self, method: str, params: List, retries: int = 2) -> Dict:
        """Make API request with exponential backoff retry"""
        async with self._rate_limiter:
            for attempt in range(retries + 1):
                try:
                    self._request_count += 1
                    
                    payload = {
                        "id": self._request_count,
                        "jsonrpc": "2.0", 
                        "method": method,
                        "params": params
                    }
                    
                    response = await self._client.post(
                        self.base_url,
                        content=orjson.dumps(payload),
                        timeout=30.0
                    )
                    
                    if response.status_code == 200:
                        return orjson.loads(response.content)
                    elif response.status_code == 429:  # Rate limited
                        wait_time = 2 ** attempt
                        logger.warning(f"⚠️ Rate limited, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"❌ HTTP {response.status_code} for {method}")
                        self._failures += 1
                        if attempt == retries:
                            return {}
                        await asyncio.sleep(0.5 * (attempt + 1))
                        
                except httpx.TimeoutException:
                    logger.error(f"⏰ Timeout for {method} (attempt {attempt + 1})")
                    self._failures += 1
                    if attempt < retries:
                        await asyncio.sleep(1.0 * (attempt + 1))
                    else:
                        return {}
                        
                except Exception as e:
                    logger.error(f"❌ Request error for {method}: {e}")
                    self._failures += 1
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
                    else:
                        return {}
            
            return {}
    
    async def get_block_number(self) -> int:
        """Get current block number with caching"""
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
        """Get transfers for multiple addresses with smart batching"""
        logger.info(f"🚀 Fetching transfers for {len(addresses)} addresses")
        
        # Process in smaller batches to avoid API limits
        batch_size = 4 if self.network == "ethereum" else 6
        batches = [addresses[i:i + batch_size] for i in range(0, len(addresses), batch_size)]
        
        all_results = {}
        
        for i, batch in enumerate(batches):
            try:
                # Process batch concurrently
                batch_tasks = []
                for address in batch:
                    task = self._get_address_transfers(address, start_block, end_block)
                    batch_tasks.append((address, task))
                
                # Execute batch
                for address, task in batch_tasks:
                    try:
                        result = await task
                        all_results[address] = result
                    except Exception as e:
                        logger.error(f"❌ Failed to get transfers for {address}: {e}")
                        all_results[address] = {"outgoing": [], "incoming": []}
                
                # Progress logging
                processed = (i + 1) * batch_size
                logger.debug(f"📊 Processed {min(processed, len(addresses))}/{len(addresses)} addresses")
                
                # Brief pause between batches to be nice to API
                if i < len(batches) - 1:
                    await asyncio.sleep(0.2)
                    
            except Exception as e:
                logger.error(f"❌ Batch {i} failed: {e}")
                # Add empty results for failed batch
                for address in batch:
                    if address not in all_results:
                        all_results[address] = {"outgoing": [], "incoming": []}

        logger.info(f"✅ Completed transfer fetching for {len(all_results)} addresses")
        return all_results
    
    async def _get_address_transfers(self, address: str, start_block: str, end_block: str) -> Dict[str, List]:
        """Get both outgoing and incoming transfers for an address"""
        # Execute both directions concurrently
        outgoing_task = self._get_transfers_direction(address, start_block, end_block, "from")
        incoming_task = self._get_transfers_direction(address, start_block, end_block, "to")
        
        try:
            outgoing, incoming = await asyncio.gather(outgoing_task, incoming_task)
            return {
                "outgoing": outgoing if isinstance(outgoing, list) else [],
                "incoming": incoming if isinstance(incoming, list) else []
            }
        except Exception as e:
            logger.error(f"❌ Error getting transfers for {address}: {e}")
            return {"outgoing": [], "incoming": []}
    
    async def _get_transfers_direction(self, address: str, start_block: str, 
                                     end_block: str, direction: str) -> List[Dict]:
        """Get transfers in specific direction with better parameters"""
        address_param = "fromAddress" if direction == "from" else "toAddress"
        
        params = [{
            address_param: address,
            "fromBlock": start_block,
            "toBlock": end_block,
            "category": ["external", "erc20"],
            "withMetadata": True,
            "excludeZeroValue": True,
            "maxCount": "0x28"  # Reduced from 0x32 to 0x28 (40 instead of 50)
        }]
        
        result = await self.make_request("alchemy_getAssetTransfers", params)
        return result.get("result", {}).get("transfers", [])
    
    async def get_token_metadata(self, contract_address: str) -> Dict:
        """Get token metadata with better error handling"""
        try:
            result = await self.make_request("alchemy_getTokenMetadata", [contract_address])
            
            if result.get("result"):
                metadata = result["result"]
                logger.debug(f"✅ Got metadata for {metadata.get('symbol', 'Unknown')}")
                return metadata
            else:
                logger.warning(f"⚠️ No metadata for {contract_address}")
                return {}
                
        except Exception as e:
            logger.error(f"❌ Error getting token metadata: {e}")
            return {}
    
    async def test_connection(self) -> bool:
        """Test connection with health check"""
        try:
            current_block = await self.get_block_number()
            if current_block > 0:
                logger.info(f"✅ {self.network} connection OK - Block: {current_block}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ {self.network} connection failed: {e}")
            return False
    
    def get_stats(self) -> Dict:
        """Get client statistics"""
        success_rate = ((self._request_count - self._failures) / max(self._request_count, 1)) * 100
        return {
            "network": self.network,
            "total_requests": self._request_count,
            "failures": self._failures,
            "success_rate": round(success_rate, 1)
        }