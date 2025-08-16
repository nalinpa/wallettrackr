#!/usr/bin/env python3
"""
Test orjson performance with real crypto data
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.json_utils import benchmark_json_performance, orjson_dumps_str, orjson_loads
from data_service import AnalysisService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_orjson_with_real_data():
    """Test orjson performance with actual crypto analysis data"""
    
    # Create sample data similar to your analysis results
    sample_data = {
        "status": "success",
        "network": "base",
        "analysis_type": "buy",
        "total_purchases": 1247,
        "unique_tokens": 156,
        "total_eth_spent": 234.5678,
        "total_usd_spent": 469135.6,
        "top_tokens": [
            {
                "rank": i,
                "token": f"TOKEN_{i}",
                "alpha_score": 89.5 - (i * 0.5),
                "wallet_count": 45 - i,
                "total_eth_spent": 12.3456 - (i * 0.1),
                "platforms": ["Uniswap", "Aerodrome", "BaseSwap"],
                "contract_address": f"0x{'1234567890abcdef' * 2}{i:08x}",
                "avg_wallet_score": 150.0 - (i * 2),
                "meets_alert_threshold": i < 5,
                "is_base_native": i % 3 == 0,
                "web3_analysis": {
                    "gas_efficiency": 85.5 + (i % 15),
                    "method_used": "swapExactTokensForETH" if i % 2 == 0 else "exactInputSingle",
                    "sophistication_score": 75.0 + (i % 25),
                    "complexity_score": 0.7 + (i % 3) * 0.1
                }
            }
            for i in range(50)  # 50 tokens
        ],
        "platform_summary": {
            "Uniswap": 456,
            "Aerodrome": 378,
            "BaseSwap": 234,
            "1inch": 156,
            "Unknown": 23
        },
        "web3_analysis": {
            "total_transactions_analyzed": 1247,
            "sophisticated_transactions": 892,
            "method_distribution": {
                "swapExactTokensForETH": 456,
                "exactInputSingle": 378,
                "swapExactETHForTokens": 234,
                "transfer": 123,
                "unknown": 56
            },
            "gas_efficiency_avg": 82.5,
            "avg_sophistication": 76.8
        },
        "config_info": {
            "excluded_tokens_count": 15,
            "min_eth_value": 0.001,
            "environment": "production"
        },
        "last_updated": "2025-01-16T10:30:45.123456",
        "cache_metadata": {
            "size_estimate": 125000,
            "token_count": 156,
            "network": "base"
        }
    }
    
    print("🧪 Testing orjson Performance with Crypto Analysis Data")
    print("="*60)
    
    # Test different data sizes
    test_cases = [
        ("Small (10 tokens)", {**sample_data, "top_tokens": sample_data["top_tokens"][:10]}),
        ("Medium (25 tokens)", {**sample_data, "top_tokens": sample_data["top_tokens"][:25]}),
        ("Large (50 tokens)", sample_data),
        ("Extra Large (100 tokens)", {**sample_data, "top_tokens": sample_data["top_tokens"] * 2})
    ]
    
    for test_name, test_data in test_cases:
        print(f"\n📊 {test_name}")
        print("-" * 40)
        
        metrics = benchmark_json_performance(test_data, iterations=500)
        
        print(f"Serialization:")
        print(f"  orjson:     {metrics['orjson_serialize_ms']:.2f}ms")
        print(f"  json:       {metrics['json_serialize_ms']:.2f}ms")
        print(f"  Speedup:    {metrics['serialize_speedup']:.1f}x")
        
        print(f"Round-trip:")
        print(f"  orjson:     {metrics['orjson_roundtrip_ms']:.2f}ms")
        print(f"  json:       {metrics['json_roundtrip_ms']:.2f}ms")
        print(f"  Speedup:    {metrics['roundtrip_speedup']:.1f}x")
        
        print(f"Size:")
        print(f"  orjson:     {metrics['serialized_size_orjson']:,} bytes")
        print(f"  json:       {metrics['serialized_size_json']:,} bytes")
        size_ratio = metrics['serialized_size_json'] / metrics['serialized_size_orjson']
        print(f"  Ratio:      {size_ratio:.2f}x")
    
    # Test with cache service
    print(f"\n🔧 Testing with AnalysisService Cache")
    print("-" * 40)
    
    service = AnalysisService()
    service.cache_config['benchmark_performance'] = True
    
    # Cache the data
    service.cache_data('base_buy', sample_data)
    
    # Retrieve the data
    cached_data = service.get_cached_data('base_buy')
    
    if cached_data:
        print("✅ Cache test successful with orjson")
        print(f"   Cached tokens: {cached_data.get('unique_tokens', 0)}")
        print(f"   Data integrity: {'✅' if cached_data['total_purchases'] == sample_data['total_purchases'] else '❌'}")
    else:
        print("❌ Cache test failed")

if __name__ == "__main__":
    test_orjson_with_real_data()