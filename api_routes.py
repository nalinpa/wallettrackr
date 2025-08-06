from flask import Blueprint, jsonify
import traceback
from datetime import datetime
from data_service import AnalysisService

api_bp = Blueprint('api', __name__)
service = AnalysisService()

@api_bp.route('/eth/buy')
def eth_buy_analysis():
    """ETH mainnet buy analysis"""
    try:
        # Import the ETH buy analyzer
        from buy_tracker import EthComprehensiveTracker
        analyzer = EthComprehensiveTracker()
        
        if not analyzer.test_connection():
            return jsonify({"error": "Connection failed"}), 500
        
        results = analyzer.analyze_all_trading_methods(num_wallets=174, days_back=1)
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant ETH buy activity found",
                "total_purchases": 0,
                "unique_tokens": 0,
                "total_eth_spent": 0
            })
        
        response_data = service.format_buy_response(results, "ethereum")
        service.cache_data('eth_buy', response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            "error": f"ETH buy analysis failed: {str(e)}",
            "traceback": traceback.format_exc()
        }), 500

@api_bp.route('/eth/sell')
def eth_sell_analysis():
    """ETH mainnet sell analysis"""
    try:
        from sell_tracker import EthComprehensiveSellTracker
        analyzer = EthComprehensiveSellTracker()
        
        if not analyzer.test_connection():
            return jsonify({"error": "Connection failed"}), 500
        
        results = analyzer.analyze_all_sell_methods(num_wallets=174, days_back=1)
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant ETH sell pressure detected",
                "total_sells": 0,
                "unique_tokens": 0,
                "total_estimated_eth": 0
            })
        
        response_data = service.format_sell_response(results, "ethereum")
        service.cache_data('eth_sell', response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            "error": f"ETH sell analysis failed: {str(e)}",
            "traceback": traceback.format_exc()
        }), 500

@api_bp.route('/base/buy')
def base_buy_analysis():
    """Base network buy analysis"""
    try:
        from base_buy_tracker import BaseComprehensiveTracker
        analyzer = BaseComprehensiveTracker()
        
        if not analyzer.test_connection():
            return jsonify({"error": "Base connection failed"}), 500
        
        results = analyzer.analyze_all_trading_methods(num_wallets=174, days_back=1)
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant Base buy activity found",
                "total_purchases": 0,
                "unique_tokens": 0,
                "total_eth_spent": 0
            })
        
        response_data = service.format_buy_response(results, "base")
        service.cache_data('base_buy', response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            "error": f"Base buy analysis failed: {str(e)}",
            "traceback": traceback.format_exc()
        }), 500

@api_bp.route('/base/sell')
def base_sell_analysis():
    """Base network sell analysis"""
    try:
        from base_sell_tracker import BaseComprehensiveSellTracker
        analyzer = BaseComprehensiveSellTracker()
        
        if not analyzer.test_connection():
            return jsonify({"error": "Base connection failed"}), 500
        
        results = analyzer.analyze_all_sell_methods(num_wallets=174, days_back=1)
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant Base sell pressure detected",
                "total_sells": 0,
                "unique_tokens": 0,
                "total_estimated_eth": 0
            })
        
        response_data = service.format_sell_response(results, "base")
        service.cache_data('base_sell', response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            "error": f"Base sell analysis failed: {str(e)}",
            "traceback": traceback.format_exc()
        }), 500

@api_bp.route('/status')
def api_status():
    """API status and cached data"""
    cache_status = service.get_cache_status()
    
    return jsonify({
        "status": "online",
        "cached_data": cache_status,
        "last_updated": service.get_last_updated(),
        "endpoints": [
            "/api/eth/buy",
            "/api/eth/sell",
            "/api/base/buy",
            "/api/base/sell"
        ]
    })