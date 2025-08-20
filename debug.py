#!/usr/bin/env python3
"""
Debug API Response - Check what data is being returned
"""

import asyncio
import json
import httpx

async def debug_api_response():
    """Test the API and show exactly what data is being returned"""
    
    print("🔍 DEBUGGING API RESPONSE")
    print("=" * 50)
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Test the enhanced buy endpoint
            url = "http://localhost:8001/api/base/buy?wallets=50&days=0.5"
            print(f"📡 Calling: {url}")
            
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                print(f"✅ Status: {response.status_code}")
                print(f"📊 Analysis Type: {data.get('analysis_type', 'unknown')}")
                print(f"🪙 Total Purchases: {data.get('total_purchases', 0)}")
                print(f"🔢 Unique Tokens: {data.get('unique_tokens', 0)}")
                
                # Check top tokens structure
                top_tokens = data.get('top_tokens', [])
                print(f"\n🏆 TOP TOKENS ({len(top_tokens)} found):")
                
                for i, token in enumerate(top_tokens[:3]):  # Show first 3
                    print(f"\n  Token #{i+1}:")
                    print(f"    Name: {token.get('token', 'NO_NAME')}")
                    print(f"    Alpha Score: {token.get('enhanced_alpha_score', 'NO_SCORE')}")
                    print(f"    Contract: {token.get('contract_address', 'NO_CONTRACT')}")
                    print(f"    Wallet Count: {token.get('wallet_count', 0)}")
                    print(f"    ETH Spent: {token.get('total_eth_spent', 0)}")
                    
                    # Check if enhanced scoring exists
                    enhanced_scoring = token.get('enhanced_scoring', {})
                    if enhanced_scoring:
                        print(f"    Enhanced Scoring: ✅")
                        print(f"      Volume Score: {enhanced_scoring.get('volume_score', 'MISSING')}")
                        print(f"      Diversity Score: {enhanced_scoring.get('diversity_score', 'MISSING')}")
                    else:
                        print(f"    Enhanced Scoring: ❌ MISSING")
                    
                    # Check risk analysis
                    risk_analysis = token.get('risk_analysis', {})
                    if risk_analysis:
                        print(f"    Risk Analysis: ✅")
                        print(f"      Risk Level: {risk_analysis.get('risk_level', 'MISSING')}")
                    else:
                        print(f"    Risk Analysis: ❌ MISSING")
                
                # Check enhanced analytics section
                enhanced_analytics = data.get('enhanced_analytics', {})
                print(f"\n📈 Enhanced Analytics:")
                print(f"    Pandas Enabled: {enhanced_analytics.get('pandas_enabled', False)}")
                print(f"    NumPy Enabled: {enhanced_analytics.get('numpy_enabled', False)}")
                print(f"    NumPy Operations: {enhanced_analytics.get('numpy_operations', 0)}")
                
                # Save full response for inspection
                with open('debug_response.json', 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                print(f"\n💾 Full response saved to: debug_response.json")
                
                return data
                
            else:
                print(f"❌ API Error: {response.status_code}")
                print(f"Response: {response.text}")
                return None
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

async def debug_direct_analyzer():
    """Test the analyzer directly to see raw data"""
    
    print("\n🔬 DEBUGGING DIRECT ANALYZER")
    print("=" * 50)
    
    try:
        from core.analysis.buy_analyzer import BuyAnalyzer
        
        async with BuyAnalyzer("base") as analyzer:
            print("📊 Running direct analysis...")
            result = await analyzer.analyze_wallets_concurrent(50, 0.5)
            
            print(f"✅ Analysis complete")
            print(f"📈 Transactions: {result.total_transactions}")
            print(f"🪙 Unique Tokens: {result.unique_tokens}")
            
            if result.ranked_tokens:
                print(f"\n🏆 TOP TOKENS (Raw Data):")
                
                for i, (token_name, token_data, score) in enumerate(result.ranked_tokens[:3]):
                    print(f"\n  Token #{i+1}:")
                    print(f"    Name: {token_name}")
                    print(f"    Score: {score}")
                    print(f"    Data Keys: {list(token_data.keys())}")
                    print(f"    Contract Address: {token_data.get('contract_address', 'MISSING')}")
                    print(f"    Total ETH: {token_data.get('total_eth_spent', 'MISSING')}")
                    print(f"    Wallet Count: {token_data.get('wallet_count', 'MISSING')}")
                    
                    # Check if the enhanced score components exist
                    enhanced_fields = [
                        'enhanced_alpha_score', 'volume_score', 'diversity_score', 
                        'quality_score', 'momentum_score', 'percentile_rank'
                    ]
                    
                    print(f"    Enhanced Fields:")
                    for field in enhanced_fields:
                        value = token_data.get(field, 'MISSING')
                        status = "✅" if value != 'MISSING' else "❌"
                        print(f"      {field}: {value} {status}")
            
            return result
            
    except Exception as e:
        print(f"❌ Direct analyzer error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # Run both tests
    asyncio.run(debug_api_response())
    asyncio.run(debug_direct_analyzer())