# tracker/simple_async_tracker.py - Simple async optimization
import asyncio
import httpx
import orjson
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

class SimpleAsyncTracker:
    """Simple async tracker for immediate performance gains"""
    
    def __init__(self, network: str):
        self.network = network
        self.alchemy_url = self._get_alchemy_url()
    
    def _get_alchemy_url(self) -> str:
        """Get Alchemy URL for network"""
        from config.settings import alchemy_config
        
        urls = {
            'ethereum': f'https://eth-mainnet.g.alchemy.com/v2/{alchemy_config.api_key}',
            'base': f'https://base-mainnet.g.alchemy.com/v2/{alchemy_config.api_key}'
        }
        return urls.get(self.network, urls['base'])
    
    async def analyze_wallets_batch(self, wallet_addresses: List[str], 
                                  days_back: float = 1.0) -> Dict:
        """Analyze multiple wallets concurrently - much faster than sequential"""
        
        print(f"Starting ASYNC analysis of {len(wallet_addresses)} wallets")
        
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
        ) as client:
            
            # Get block range
            start_block, end_block = await self._get_block_range_async(client, days_back)
            
            # Create tasks for all wallets
            tasks = []
            for address in wallet_addresses:
                task = self._analyze_single_wallet_async(client, address, start_block, end_block)
                tasks.append(task)
            
            # Run all wallet analyses concurrently
            print(f"Processing {len(tasks)} wallets concurrently...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            successful_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Wallet {wallet_addresses[i]} failed: {result}")
                else:
                    successful_results.extend(result)
            
            print(f"Async analysis complete: {len(successful_results)} purchases found")
            
            return {
                'total_purchases': len(successful_results),
                'successful_wallets': len([r for r in results if not isinstance(r, Exception)]),
                'failed_wallets': len([r for r in results if isinstance(r, Exception)]),
                'all_purchases': successful_results
            }
    
    async def _analyze_single_wallet_async(self, client: httpx.AsyncClient, 
                                         wallet_address: str, start_block: str, 
                                         end_block: str) -> List[Dict]:
        """Analyze single wallet async"""
        try:
            # Get outgoing and incoming transfers concurrently
            outgoing_task = self._get_transfers_async(
                client, wallet_address, start_block, end_block, "from"
            )
            incoming_task = self._get_transfers_async(
                client, wallet_address, start_block, end_block, "to"
            )
            
            outgoing_transfers, incoming_transfers = await asyncio.gather(
                outgoing_task, incoming_task
            )
            
            # Process transfers into purchases
            purchases = self._process_transfers_simple(
                outgoing_transfers, incoming_transfers, wallet_address
            )
            
            return purchases
            
        except Exception as e:
            logger.error(f"Single wallet analysis failed for {wallet_address}: {e}")
            return []
    
    async def _get_transfers_async(self, client: httpx.AsyncClient, 
                                 wallet_address: str, start_block: str, 
                                 end_block: str, direction: str) -> List[Dict]:
        """Get transfers async"""
        address_param = "fromAddress" if direction == "from" else "toAddress"
        
        payload = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [{
                address_param: wallet_address,
                "fromBlock": start_block,
                "toBlock": end_block,
                "category": ["external", "erc20"],
                "withMetadata": True,
                "excludeZeroValue": True,
                "maxCount": "0x32"  # 50 transfers
            }]
        }
        
        try:
            response = await client.post(
                self.alchemy_url,
                content=orjson.dumps(payload),
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            
            result = orjson.loads(response.content)
            return result.get("result", {}).get("transfers", [])
            
        except Exception as e:
            logger.error(f"Transfer request failed: {e}")
            return []
    
    def _process_transfers_simple(self, outgoing: List[Dict], 
                                incoming: List[Dict], wallet_address: str) -> List[Dict]:
        """Simple transfer processing"""
        purchases = []
        
        # Group by transaction hash
        tx_groups = {}
        
        # Process outgoing transfers
        for transfer in outgoing:
            tx_hash = transfer.get("hash")
            if tx_hash and self._is_purchase_candidate(transfer):
                if tx_hash not in tx_groups:
                    tx_groups[tx_hash] = {"outgoing": [], "incoming": []}
                tx_groups[tx_hash]["outgoing"].append(transfer)
        
        # Add incoming transfers
        for transfer in incoming:
            tx_hash = transfer.get("hash")
            if tx_hash in tx_groups:
                tx_groups[tx_hash]["incoming"].append(transfer)
        
        # Extract purchases
        for tx_hash, transfers in tx_groups.items():
            if transfers["outgoing"] and transfers["incoming"]:
                for outgoing in transfers["outgoing"]:
                    for incoming in transfers["incoming"]:
                        purchase = self._extract_purchase_simple(outgoing, incoming, wallet_address)
                        if purchase:
                            purchases.append(purchase)
        
        return purchases
    
    def _is_purchase_candidate(self, transfer: Dict) -> bool:
        """Simple check for purchase candidates"""
        asset = transfer.get("asset", "")
        value = transfer.get("value", 0)
        
        try:
            amount = float(value) if value else 0
        except (ValueError, TypeError):
            return False
        
        # Basic thresholds
        if asset == "ETH":
            return amount >= 0.001  # 0.001 ETH minimum
        else:
            return amount >= 1  # 1 token minimum
    
    def _extract_purchase_simple(self, outgoing: Dict, incoming: Dict, 
                               wallet_address: str) -> Dict:
        """Extract purchase data simply"""
        token_bought = incoming.get("asset")
        if not token_bought or token_bought in ["ETH", "WETH"]:
            return None
        
        try:
            amount_received = float(incoming.get("value", 0))
            amount_sold = float(outgoing.get("value", 0))
            
            if amount_received <= 0:
                return None
            
            # Calculate ETH spent
            token_sold = outgoing.get("asset", "ETH")
            if token_sold == "ETH":
                eth_spent = amount_sold
            else:
                eth_spent = amount_sold * 0.0005  # Rough estimate
            
            return {
                "transaction_hash": incoming.get("hash", ""),
                "token_bought": token_bought,
                "amount_received": amount_received,
                "eth_spent": eth_spent,
                "wallet_address": wallet_address,
                "block_number": int(incoming.get("blockNum", "0x0"), 16)
            }
            
        except (ValueError, TypeError):
            return None
    
    async def _get_block_range_async(self, client: httpx.AsyncClient, 
                                   days_back: float) -> tuple:
        """Get block range async"""
        payload = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "eth_blockNumber",
            "params": []
        }
        
        try:
            response = await client.post(
                self.alchemy_url,
                content=orjson.dumps(payload),
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            
            result = orjson.loads(response.content)
            current_block = int(result["result"], 16)
            
            # Calculate blocks back
            blocks_per_day = 43200 if self.network == "base" else 7200
            blocks_back = int(days_back * blocks_per_day)
            start_block = max(0, current_block - blocks_back)
            
            return hex(start_block), hex(current_block)
            
        except Exception as e:
            logger.error(f"Block range request failed: {e}")
            return "0x0", "0x0"

# Usage example:
async def test_async_performance():
    """Test the async tracker performance"""
    tracker = SimpleAsyncTracker("base")
    
    # Test with a few wallets
    test_wallets = [
        "0x3837dCc83fdfb8ecee7F019B7BE3B0A9C3fAd4ab",
        "0x9e5e999c4506EA58E433898A6E8f5251db5a33bE",
        "0xf58C18BD3CeB788544bBBf1DACbE8F0857Da568e"
    ]
    
    import time
    start_time = time.time()
    
    results = await tracker.analyze_wallets_batch(test_wallets, days_back=0.1)
    
    end_time = time.time()
    
    print(f"Async analysis took {end_time - start_time:.2f} seconds")
    print(f"Found {results['total_purchases']} purchases")
    
    return results

if __name__ == "__main__":
    asyncio.run(test_async_performance())
