#!/usr/bin/env python3
# startup_optimized.py - Start with optimizations enabled

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Enable optimizations
os.environ['ENABLE_HTTPX_OPTIMIZATION'] = '1'
os.environ['ENABLE_ORJSON_OPTIMIZATION'] = '1'

print("Starting Crypto Tracker with optimizations...")

# Import and run the app
if __name__ == '__main__':
    from app import app
    
    print("Optimizations loaded:")
    print("   - HTTPx connection pooling")
    print("   - orjson fast serialization") 
    print("   - Enhanced caching")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,  # Disable debug for better performance
        threaded=True
    )
