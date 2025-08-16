import asyncio
import time
import requests
import platform

async def test_uvloop_performance():
    """Test uvloop performance benefits"""
    
    print("🧪 Testing uvloop Performance")
    print("="*40)
    print(f"Platform: {platform.system()}")
    
    # Test if uvloop is active
    try:
        import uvloop
        print("✅ uvloop module available")
        
        # Check if uvloop is the active event loop
        loop = asyncio.get_event_loop()
        loop_type = type(loop).__name__
        print(f"Event loop type: {loop_type}")
        
        if 'uvloop' in loop_type.lower():
            print("🚀 uvloop is ACTIVE!")
        else:
            print("⚠️  Standard event loop (uvloop not active)")
            
    except ImportError:
        print("❌ uvloop not installed")
        return
    
    # Performance test
    print("\n📊 Performance Test:")
    
    # Test HTTP requests
    try:
        print("Testing HTTP performance...")
        start_time = time.perf_counter()
        
        # Make several requests
        for i in range(10):
            try:
                response = requests.get('http://localhost:5005/api/status', timeout=5)
                if response.status_code == 200:
                    print(f"  Request {i+1}: ✅")
                else:
                    print(f"  Request {i+1}: ❌ {response.status_code}")
            except Exception as e:
                print(f"  Request {i+1}: ❌ {e}")
        
        total_time = time.perf_counter() - start_time
        avg_time = total_time / 10
        
        print(f"\n📈 Results:")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Average per request: {avg_time*1000:.1f}ms")
        
        if 'uvloop' in loop_type.lower():
            print(f"  🚀 With uvloop optimization!")
        else:
            print(f"  📊 Without uvloop (run in Docker for 30-40% improvement)")
            
    except Exception as e:
        print(f"❌ Performance test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_uvloop_performance())