import asyncio
import time
from services.blockchain_services.service_container import ServiceContainer

async def test_performance():
    """Test performance"""
    print("🚀 PERFORMANCE TEST")
    print("=" * 60)
    
    async with ServiceContainer("base") as services:
        # Test database
        wallets = await services.database.get_top_wallets("base", 10)
        print(f"✅ Retrieved {len(wallets)} wallets")
        
        # Test alchemy
        start_block, end_block = await services.alchemy.get_block_range(0.1)
        print(f"✅ Block range: {start_block} to {end_block}")
        
        # Test batch transfers
        addresses = [w['address'] for w in wallets[:5]]
        transfers = await services.alchemy.get_transfers_batch(addresses, start_block, end_block)
        print(f"✅ Processed {len(addresses)} wallets")

if __name__ == "__main__":
    asyncio.run(test_performance())