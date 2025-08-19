#!/usr/bin/env python3
"""
Environment check script for the token page functionality
Run this to verify your setup before using the token page
"""

import os
import asyncio
import logging
import sys

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_environment():
    """Check environment variables and basic setup"""
    print("🔍 Checking environment setup...")
    
    # Check Python version
    print(f"Python version: {sys.version}")
    
    # Check environment variables
    env_vars = {
        'ALCHEMY_API_KEY': os.getenv('ALCHEMY_API_KEY'),
        'MONGO_URI': os.getenv('MONGO_URI', 'Not set'),
        'ENVIRONMENT': os.getenv('ENVIRONMENT', 'development')
    }
    
    print("\n📊 Environment Variables:")
    for key, value in env_vars.items():
        if value:
            if key == 'ALCHEMY_API_KEY':
                print(f"  {key}: {'*' * 20}...{value[-4:] if len(value) > 4 else '****'}")
            else:
                print(f"  {key}: {value}")
        else:
            print(f"  {key}: ❌ NOT SET")
    
    # Check required packages
    print("\n📦 Checking required packages:")
    required_packages = [
        'fastapi', 'httpx', 'orjson', 'motor', 'jinja2'
    ]
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"  {package}: ✅ Available")
        except ImportError:
            print(f"  {package}: ❌ Not installed")
    
    return env_vars['ALCHEMY_API_KEY'] is not None

async def test_alchemy_connection():
    """Test direct Alchemy API connection"""
    api_key = os.getenv('ALCHEMY_API_KEY')
    if not api_key:
        print("❌ ALCHEMY_API_KEY not set, skipping Alchemy test")
        return False
    
    print("\n🔗 Testing Alchemy API connection...")
    
    try:
        import httpx
        import orjson
        
        # Test Ethereum connection
        eth_url = f"https://eth-mainnet.alchemyapi.io/v2/{api_key}"
        
        async with httpx.AsyncClient() as client:
            # Test basic connection with eth_blockNumber
            payload = {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "eth_blockNumber",
                "params": []
            }
            
            response = await client.post(
                eth_url,
                content=orjson.dumps(payload),
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                result = orjson.loads(response.content)
                if result.get("result"):
                    block_number = int(result["result"], 16)
                    print(f"  ✅ Ethereum connection OK - Current block: {block_number}")
                else:
                    print(f"  ❌ Ethereum connection failed - No result: {result}")
                    return False
            else:
                print(f"  ❌ Ethereum connection failed - HTTP {response.status_code}")
                return False
        
        # Test Base connection
        base_url = f"https://base-mainnet.g.alchemy.com/v2/{api_key}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                base_url,
                content=orjson.dumps(payload),
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                result = orjson.loads(response.content)
                if result.get("result"):
                    block_number = int(result["result"], 16)
                    print(f"  ✅ Base connection OK - Current block: {block_number}")
                else:
                    print(f"  ❌ Base connection failed - No result: {result}")
            else:
                print(f"  ❌ Base connection failed - HTTP {response.status_code}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Alchemy connection test failed: {e}")
        return False

async def test_token_metadata():
    """Test token metadata retrieval"""
    api_key = os.getenv('ALCHEMY_API_KEY')
    if not api_key:
        print("❌ ALCHEMY_API_KEY not set, skipping metadata test")
        return False
    
    print("\n🪙 Testing token metadata retrieval...")
    
    try:
        import httpx
        import orjson
        
        # Test with USDC (known good contract)
        test_contract = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
        eth_url = f"https://eth-mainnet.alchemyapi.io/v2/{api_key}"
        
        async with httpx.AsyncClient() as client:
            payload = {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "alchemy_getTokenMetadata",
                "params": [test_contract]
            }
            
            response = await client.post(
                eth_url,
                content=orjson.dumps(payload),
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                result = orjson.loads(response.content)
                if result.get("result"):
                    metadata = result["result"]
                    print(f"  ✅ USDC metadata: {metadata.get('symbol')} - {metadata.get('name')}")
                    
                    # Test with your contract
                    your_contract = "0xac743b05f5e590d9db6a4192e02457838e4af61e"
                    payload["params"] = [your_contract]
                    
                    response = await client.post(
                        eth_url,
                        content=orjson.dumps(payload),
                        headers={'Content-Type': 'application/json'}
                    )
                    
                    if response.status_code == 200:
                        result = orjson.loads(response.content)
                        if result.get("result"):
                            metadata = result["result"]
                            print(f"  ✅ Your token metadata: {metadata.get('symbol')} - {metadata.get('name')}")
                            return True
                        else:
                            print(f"  ⚠️ Your token has no metadata: {result}")
                            return True  # This is actually normal for some tokens
                    else:
                        print(f"  ❌ Failed to get your token metadata - HTTP {response.status_code}")
                        return False
                else:
                    print(f"  ❌ Failed to get USDC metadata: {result}")
                    return False
            else:
                print(f"  ❌ Metadata request failed - HTTP {response.status_code}")
                return False
                
    except Exception as e:
        print(f"  ❌ Token metadata test failed: {e}")
        return False

async def test_database_connection():
    """Test database connection"""
    print("\n💾 Testing database connection...")
    
    try:
        # Try to import and test database
        from services.database.database_client import DatabaseClient
        
        async with DatabaseClient() as db:
            count = await db.count_wallets()
            print(f"  ✅ Database connection OK - {count} wallets in database")
            return True
            
    except Exception as e:
        print(f"  ❌ Database connection failed: {e}")
        return False

async def test_service_container():
    """Test the service container initialization"""
    print("\n🔧 Testing ServiceContainer...")
    
    try:
        from services.service_container import ServiceContainer
        
        # Test Ethereum
        async with ServiceContainer("ethereum") as services:
            connections = await services.test_connections()
            print(f"  ✅ Ethereum ServiceContainer: {connections}")
        
        # Test Base
        async with ServiceContainer("base") as services:
            connections = await services.test_connections()
            print(f"  ✅ Base ServiceContainer: {connections}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ ServiceContainer test failed: {e}")
        import traceback
        print(f"  📝 Traceback: {traceback.format_exc()}")
        return False

def print_setup_instructions():
    """Print setup instructions if tests fail"""
    print("\n" + "="*50)
    print("🔧 SETUP INSTRUCTIONS")
    print("="*50)
    
    print("\n1. Set your Alchemy API key:")
    print("   export ALCHEMY_API_KEY='your_api_key_here'")
    
    print("\n2. Install required packages:")
    print("   pip install fastapi httpx orjson motor jinja2 uvicorn")
    
    print("\n3. Check your MongoDB connection:")
    print("   export MONGO_URI='mongodb://localhost:27017/crypto_tracker'")
    
    print("\n4. Verify your project structure:")
    print("   - services/service_container.py")
    print("   - services/database/database_client.py") 
    print("   - services/blockchain/alchemy_client.py")
    print("   - api/routes/token.py")
    print("   - templates/token.html")
    
    print("\n5. Test individual components:")
    print("   python check_env.py")
    
    print("\n6. Start your server:")
    print("   python main.py")
    
    print("\n7. Test endpoints:")
    print("   http://localhost:8001/api/token/test")
    print("   http://localhost:8001/api/token/test-alchemy")

async def run_all_tests():
    """Run all environment tests"""
    print("🚀 Starting environment check for Crypto Alpha Tracker...")
    print("="*60)
    
    # Basic environment check
    env_ok = check_environment()
    
    if not env_ok:
        print("\n❌ Environment check failed!")
        print_setup_instructions()
        return False
    
    # Test connections
    tests = [
        ("Alchemy API", test_alchemy_connection()),
        ("Token Metadata", test_token_metadata()),
        ("Database", test_database_connection()),
        ("Service Container", test_service_container())
    ]
    
    results = []
    for test_name, test_coro in tests:
        try:
            result = await test_coro
            results.append((test_name, result))
        except Exception as e:
            print(f"  ❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST RESULTS SUMMARY")
    print("="*60)
    
    passed = 0
    total = len(results)
    
    for test_name, passed_test in results:
        status = "✅ PASS" if passed_test else "❌ FAIL"
        print(f"  {test_name}: {status}")
        if passed_test:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Your environment is ready.")
        print("\nYou can now test your token page:")
        print("1. Start your server: python main.py")
        print("2. Visit: http://localhost:8001/api/token/test")
        print("3. Test token page: http://localhost:8001/token?contract=0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48&network=ethereum")
        return True
    else:
        print(f"\n⚠️ {total - passed} tests failed. Check the setup instructions above.")
        print_setup_instructions()
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(run_all_tests())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n👋 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test script crashed: {e}")
        import traceback
        print(traceback.format_exc())
        sys.exit(1)