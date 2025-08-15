#!/usr/bin/env python3
"""
Test with realistic analysis parameters
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tracker.buy_tracker import ComprehensiveBuyTracker
import time
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_realistic_analysis():
    """Test with realistic parameters"""
    print("🧪 Testing realistic analysis parameters...")
    
    # More realistic parameters
    network = "base"
    num_wallets = 25     # Manageable size for testing
    days_back = 1        # 3 days of data (more realistic)
    
    print(f"\n🎯 Testing {network.upper()} buy analysis:")
    print(f"   📊 Wallets: {num_wallets}")
    print(f"   ⏰ Days back: {days_back} days")
    print(f"   🔍 Looking for: Recent real trading activity")
    
    try:
        tracker = ComprehensiveBuyTracker(network)
        
        if not tracker.test_connection():
            print(f"❌ Failed to connect to {network}")
            return
        
        print(f"\n🚀 Starting realistic analysis...")
        start_time = time.time()
        
        # Run analysis with realistic parameters
        results = tracker.analyze_all_trading_methods(
            num_wallets=num_wallets,
            days_back=days_back,
            max_wallets_for_sse=False
        )
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Show detailed results
        print(f"\n📊 Realistic Analysis Results:")
        print(f"   ⏱️  Total time: {total_time:.1f} seconds")
        print(f"   ⚡ Wallets per second: {num_wallets/total_time:.2f}")
        print(f"   📈 Time per wallet: {total_time/num_wallets:.1f}s")
        
        if results:
            total_purchases = results.get('total_purchases', 0)
            unique_tokens = results.get('unique_tokens', 0)
            total_eth = results.get('total_eth_spent', 0)
            
            print(f"   💰 Total purchases: {total_purchases}")
            print(f"   🪙 Unique tokens: {unique_tokens}")
            print(f"   💎 Total ETH: {total_eth:.4f}")
            
            if total_purchases > 0:
                print(f"   📊 Avg purchases per wallet: {total_purchases/num_wallets:.1f}")
                print(f"   💰 Avg ETH per purchase: {total_eth/total_purchases:.4f}")
            
            # Show top tokens with more details
            top_tokens = results.get('ranked_tokens', [])[:5]
            if top_tokens:
                print(f"\n🏆 Top {len(top_tokens)} Tokens Found:")
                for i, (token, data, score) in enumerate(top_tokens, 1):
                    wallets = len(data.get('wallets', []))
                    eth = data.get('total_eth_spent', 0)
                    platforms = list(data.get('platforms', []))[:2]  # Show top 2 platforms
                    
                    platform_str = ", ".join(platforms) if platforms else "Unknown"
                    print(f"      {i}. {token}")
                    print(f"         💰 {wallets} wallets, {eth:.4f} ETH, α={score:.1f}")
                    print(f"         🏪 Platforms: {platform_str}")
            
            # Platform analysis
            platform_summary = results.get('platform_summary', {})
            if platform_summary:
                print(f"\n🏪 Platform Distribution:")
                for platform, count in sorted(platform_summary.items(), key=lambda x: x[1], reverse=True):
                    percentage = (count / total_purchases) * 100 if total_purchases > 0 else 0
                    print(f"      {platform}: {count} ({percentage:.1f}%)")
        else:
            print(f"   ℹ️  No significant activity found in {days_back} days")
        
        # Performance projections
        print(f"\n📈 Performance Projections:")
        time_per_wallet = total_time / num_wallets
        
        # Estimate for full analysis
        full_173_time = time_per_wallet * 173
        print(f"   🎯 Estimated 173 wallets: {full_173_time:.0f} seconds ({full_173_time/60:.1f} minutes)")
        
        # Compare with old requests method
        old_estimated_time = 300  # 5 minutes was typical before
        improvement = old_estimated_time / full_173_time if full_173_time > 0 else 1
        print(f"   📉 vs old requests method: ~{improvement:.1f}x faster")
        
        # httpx specific metrics
        total_api_calls = num_wallets * 3  # ~3 calls per wallet (block range + 2 transfers)
        calls_per_second = total_api_calls / total_time
        print(f"   ⚡ API calls efficiency: {total_api_calls} calls in {total_time:.1f}s = {calls_per_second:.1f} calls/sec")
        
        tracker.close_connections()
        
    except Exception as e:
        print(f"❌ Error during realistic analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_realistic_analysis()