from flask import Blueprint, jsonify, Response, request
import traceback
from datetime import datetime
from data_service import AnalysisService
import json
import time
from queue import Queue, Empty
import threading
import sys
from io import StringIO

from auto_monitor import monitor
from buy_tracker import EthComprehensiveTracker
from sell_tracker import EthComprehensiveSellTracker
from base_buy_tracker import BaseComprehensiveTracker
from base_sell_tracker import BaseComprehensiveSellTracker


api_bp = Blueprint('api', __name__)
service = AnalysisService()

analysis_in_progress = {
    'eth_buy': False,
    'eth_sell': False,
    'base_buy': False,
    'base_sell': False
}

def sanitize_for_json(obj):
    """Convert non-JSON serializable objects to JSON serializable format"""
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, tuple):
        return list(sanitize_for_json(item) for item in obj)
    elif hasattr(obj, '__dict__'):
        return sanitize_for_json(obj.__dict__)
    else:
        return obj

class ConsoleCapture:
    """Capture console output and send it via SSE"""
    def __init__(self, message_queue):
        self.message_queue = message_queue
        self.original_stdout = sys.stdout
        self.capture_buffer = StringIO()
    
    def write(self, text):
        # Write to original stdout
        self.original_stdout.write(text)
        
        # Parse and send to SSE
        if text.strip():
            # Determine message type based on content
            level = 'info'
            if '✅' in text or 'SUCCESS' in text:
                level = 'success'
            elif '⚠️' in text or 'WARNING' in text:
                level = 'warning'
            elif '❌' in text or 'ERROR' in text:
                level = 'error'
            elif '🚀' in text or '🏆' in text or '💎' in text:
                level = 'highlight'
            
            # Clean up the text for display
            display_text = text.strip()
            
            # Send to SSE queue
            self.message_queue.put({
                'type': 'console',
                'message': display_text,
                'level': level
            })
    
    def flush(self):
        self.original_stdout.flush()

def generate_sse_stream(network, analysis_type, message_queue):
    """Generate SSE stream for real-time console output AND results"""
    analysis_key = f"{network}_{analysis_type}"
    
    # Check if analysis is already running
    global analysis_in_progress
    if analysis_in_progress.get(analysis_key, False):
        message_queue.put({
            'type': 'console',
            'message': 'Analysis already in progress, please wait...',
            'level': 'warning'
        })
        message_queue.put({'type': 'complete', 'status': 'already_running'})
        
        def generate():
            yield f"data: {json.dumps({'type': 'console', 'message': 'Analysis already in progress', 'level': 'warning'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'status': 'already_running'})}\n\n"
        return generate()
    
    # Mark analysis as in progress
    analysis_in_progress[analysis_key] = True
    
    def run_analysis():
        # Capture console output
        console_capture = ConsoleCapture(message_queue)
        old_stdout = sys.stdout
        sys.stdout = console_capture
        
        try:
            # Import and run the appropriate analyzer
            if network == 'eth' and analysis_type == 'buy':
                analyzer = EthComprehensiveTracker()
                results = analyzer.analyze_all_trading_methods(num_wallets=50, days_back=1)
            elif network == 'eth' and analysis_type == 'sell':
                analyzer = EthComprehensiveSellTracker()
                results = analyzer.analyze_all_sell_methods(num_wallets=174, days_back=1)
            elif network == 'base' and analysis_type == 'buy':
                analyzer = BaseComprehensiveTracker()
                results = analyzer.analyze_all_trading_methods(num_wallets=174, days_back=1)
            elif network == 'base' and analysis_type == 'sell':
                analyzer = BaseComprehensiveSellTracker()
                results = analyzer.analyze_all_sell_methods(num_wallets=174, days_back=1)
            else:
                results = None
            
            # Convert results to be JSON serializable
            if results:
                results = sanitize_for_json(results)
                
                # Format the results for the API response
                if analysis_type == 'buy':
                    response_data = service.format_buy_response(results, network)
                else:
                    response_data = service.format_sell_response(results, network)
                
                # Cache the results
                service.cache_data(f'{network}_{analysis_type}', response_data)
                
                # IMPORTANT: Send the formatted results through SSE
                message_queue.put({
                    'type': 'results',
                    'data': response_data
                })
            
            # Send completion message
            message_queue.put({
                'type': 'complete', 
                'status': 'success',
                'has_results': bool(results and results.get('ranked_tokens'))
            })
            
        except Exception as e:
            print(f"❌ Error during analysis: {e}")
            message_queue.put({
                'type': 'console',
                'message': f'Error: {str(e)}',
                'level': 'error'
            })
            message_queue.put({'type': 'complete', 'status': 'error', 'error': str(e)})
        
        finally:
            # Restore stdout
            sys.stdout = old_stdout
            # Mark analysis as complete
            analysis_in_progress[analysis_key] = False
    
    # Start analysis in background thread
    analysis_thread = threading.Thread(target=run_analysis)
    analysis_thread.daemon = True
    analysis_thread.start()

    def generate():
        wallet_count = 0
        total_wallets = 174
        completion_sent = False
        timeout_counter = 0
        max_timeout = 3000  # 5 minutes timeout (3000 * 0.1)
        
        while not completion_sent and timeout_counter < max_timeout:
            try:
                # Try to get message with timeout
                message = message_queue.get(timeout=0.1)
                
                # Reset timeout counter on new message
                timeout_counter = 0
                
                # Ensure message is JSON serializable
                message = sanitize_for_json(message)
                
                # Track progress
                if 'message' in message and 'Wallet:' in message.get('message', ''):
                    wallet_count += 1
                    progress = int((wallet_count / total_wallets) * 100)
                    yield f"data: {json.dumps({'type': 'progress', 'percentage': progress})}\n\n"
                
                # Send message
                try:
                    yield f"data: {json.dumps(message)}\n\n"
                except TypeError as e:
                    # If still can't serialize, send error message
                    error_msg = {'type': 'console', 'message': f'Serialization error: {str(e)}', 'level': 'error'}
                    yield f"data: {json.dumps(error_msg)}\n\n"
                
                # Check if complete
                if message.get('type') == 'complete':
                    completion_sent = True
                    # Send final complete message to ensure client closes
                    yield f"data: {json.dumps({'type': 'final_complete'})}\n\n"
                    break
                    
            except Empty:
                # No message in queue
                timeout_counter += 1
                # Send keepalive every 5 seconds
                if timeout_counter % 50 == 0:
                    yield f": keepalive\n\n"
        
        # If we hit timeout, send completion
        if not completion_sent:
            yield f"data: {json.dumps({'type': 'complete', 'status': 'timeout'})}\n\n"
            yield f"data: {json.dumps({'type': 'final_complete'})}\n\n"
            analysis_in_progress[analysis_key] = False
    
    return generate()

# SSE endpoints with proper completion handling
@api_bp.route('/eth/buy/stream')
def eth_buy_stream():
    """SSE endpoint for ETH buy analysis with console output"""
    message_queue = Queue()
    return Response(
        generate_sse_stream('eth', 'buy', message_queue),
        mimetype="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )

@api_bp.route('/eth/sell/stream')
def eth_sell_stream():
    """SSE endpoint for ETH sell analysis with console output"""
    message_queue = Queue()
    return Response(
        generate_sse_stream('eth', 'sell', message_queue),
        mimetype="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )

@api_bp.route('/base/buy/stream')
def base_buy_stream():
    """SSE endpoint for Base buy analysis with console output"""
    message_queue = Queue()
    return Response(
        generate_sse_stream('base', 'buy', message_queue),
        mimetype="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )

@api_bp.route('/base/sell/stream')
def base_sell_stream():
    """SSE endpoint for Base sell analysis with console output"""
    message_queue = Queue()
    return Response(
        generate_sse_stream('base', 'sell', message_queue),
        mimetype="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )
    
# Keep existing endpoints
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
        
    except Exception:
        return jsonify({
            "error": f"Base sell analysis failed: {str(Exception)}",
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
            "/api/base/sell",
            "/api/eth/buy/stream",
            "/api/eth/sell/stream",
            "/api/base/buy/stream",
            "/api/base/sell/stream"
        ]
    })
    
@api_bp.route('/monitor/status', methods=['GET'])
def monitor_status():
    """Get monitor status"""
    try:
        print("📍 Monitor status request received")
        
        if monitor:
            status = monitor.get_status()
            print(f"✅ Monitor status: Running={status.get('is_running', False)}")
            return jsonify(status)
        else:
            print("⚠️ Monitor not initialized, returning default status")
            return jsonify({
                'is_running': False,
                'error': 'Monitor not initialized',
                'last_check': None,
                'next_check': None,
                'config': {
                    'check_interval_minutes': 60,
                    'networks': ['base'],
                    'num_wallets': 50,
                    'use_interval_for_timeframe': True
                },
                'notification_channels': {
                    'console': True,
                    'file': True,
                    'webhook': False
                },
                'alert_thresholds': {
                    'min_wallets': 2,
                    'min_eth_spent': 0.5,
                    'min_alpha_score': 30.0
                },
                'recent_alerts': [],
                'stats': {
                    'total_alerts': 0,
                    'known_tokens': 0,
                    'seen_purchases': 0
                }
            })
    except Exception as e:
        print(f"❌ Error getting monitor status: {e}")
        traceback.print_exc()
        return jsonify({
            'is_running': False,
            'error': str(e),
            'last_check': None,
            'next_check': None,
            'config': {},
            'notification_channels': {},
            'alert_thresholds': {},
            'recent_alerts': []
        }), 500

@api_bp.route('/monitor/start', methods=['POST'])
def start_monitor():
    """Start the automated monitoring"""
    try:
        print("📍 Monitor start request received")
        if monitor:
            result = monitor.start_monitoring()
            print(f"✅ Monitor start result: {result}")
            return jsonify(result)
        else:
            return jsonify({'status': 'error', 'message': 'Monitor not available'}), 500
    except Exception as e:
        print(f"❌ Error starting monitor: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/monitor/stop', methods=['POST'])
def stop_monitor():
    """Stop the automated monitoring"""
    try:
        print("📍 Monitor stop request received")
        if monitor:
            result = monitor.stop_monitoring()
            print(f"✅ Monitor stop result: {result}")
            return jsonify(result)
        else:
            return jsonify({'status': 'error', 'message': 'Monitor not available'}), 500
    except Exception as e:
        print(f"❌ Error stopping monitor: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/monitor/check-now', methods=['POST'])
def check_now():
    """Trigger an immediate check"""
    try:
        print("\n" + "="*60)
        print("🔍 IMMEDIATE CHECK REQUESTED")
        print("="*60)
        
        if not monitor:
            print("❌ Monitor not available")
            return jsonify({'status': 'error', 'message': 'Monitor not available'}), 500
        
        # Run the check in a background thread
        def run_check():
            try:
                print("🚀 Starting immediate check in background thread...")
                monitor.check_for_new_tokens()
                print("✅ Immediate check completed")
            except Exception as e:
                print(f"❌ Error during immediate check: {e}")
                traceback.print_exc()
        
        thread = threading.Thread(target=run_check)
        thread.daemon = True
        thread.start()
        
        return jsonify({'status': 'success', 'message': 'Check initiated - see console for output'})
    except Exception as e:
        print(f"❌ Error initiating check: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/monitor/config', methods=['GET', 'POST'])
def monitor_config():
    """Get or update monitor configuration"""
    try:
        if not monitor:
            if request.method == 'POST':
                return jsonify({'status': 'error', 'message': 'Monitor not available'}), 500
            else:
                # Return default config even if monitor isn't loaded
                return jsonify({
                    'check_interval_minutes': 60,
                    'networks': ['base'],
                    'num_wallets': 174,
                    'use_interval_for_timeframe': True
                })
            
        if request.method == 'POST':
            print("📍 Monitor config update request received")
            new_config = request.json
            print(f"   New config: {new_config}")
            monitor.config.update(new_config)
            monitor.save_config()
            return jsonify({'status': 'success', 'config': monitor.config})
        
        print("📍 Monitor config request received")
        return jsonify(monitor.config)
    except Exception as e:
        print(f"❌ Error with monitor config: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/monitor/alerts', methods=['GET'])
def get_alerts():
    """Get recent alerts"""
    try:
        print("📍 Alerts request received")
        if not monitor:
            return jsonify([])
            
        limit = request.args.get('limit', 20, type=int)
        alerts = [alert.to_dict() for alert in monitor.alerts[-limit:]]
        print(f"✅ Returning {len(alerts)} alerts")
        return jsonify(alerts)
    except Exception as e:
        print(f"❌ Error getting alerts: {e}")
        traceback.print_exc()
        return jsonify([])

@api_bp.route('/monitor/thresholds', methods=['POST'])
def update_thresholds():
    """Update alert thresholds"""
    try:
        if not monitor:
            return jsonify({'status': 'error', 'message': 'Monitor not available'}), 500
            
        print("📍 Threshold update request received")
        thresholds = request.json
        print(f"   New thresholds: {thresholds}")
        monitor.alert_thresholds.update(thresholds)
        return jsonify({'status': 'success', 'thresholds': monitor.alert_thresholds})
    except Exception as e:
        print(f"❌ Error updating thresholds: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/monitor/notifications', methods=['POST'])
def update_notifications():
    """Update notification settings"""
    try:
        if not monitor:
            return jsonify({'status': 'error', 'message': 'Monitor not available'}), 500
            
        print("📍 Notification settings update request received")
        settings = request.json
        print(f"   New settings: {settings}")
        monitor.notification_channels.update(settings)
        return jsonify({'status': 'success', 'channels': monitor.notification_channels})
    except Exception as e:
        print(f"❌ Error updating notifications: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/monitor/test', methods=['GET'])
def test_monitor():
    """Test endpoint to verify monitor is working"""
    print("📍 Monitor test endpoint called")
    
    test_results = {
        'monitor_available': monitor is not None,
        'monitor_module': False,
        'base_tracker': False,
        'eth_tracker': False
    }
    
    try:
        # Test monitor module
        if monitor:
            test_results['monitor_module'] = hasattr(monitor, 'get_status')
        
        # Test base tracker
        from base_buy_tracker import BaseComprehensiveTracker
        tracker = BaseComprehensiveTracker()
        test_results['base_tracker'] = hasattr(tracker, 'test_connection')
        
        # Test eth tracker
        from buy_tracker import EthComprehensiveTracker
        tracker = EthComprehensiveTracker()
        test_results['eth_tracker'] = hasattr(tracker, 'test_connection')
        
        return jsonify({
            'status': 'success',
            'message': 'Monitor test completed',
            'results': test_results
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Monitor test failed: {str(e)}',
            'results': test_results
        }), 500
        
@api_bp.route('/token/<contract_address>')
def token_details(contract_address):
    """Get detailed token information using shared utilities"""
    try:
        from datetime import datetime
        import os
        
        network = request.args.get('network', 'ethereum')
        
        # Initialize the appropriate tracker based on network
        if network == 'base':
            from base_shared_utils import BaseTracker, is_base_native_token
            tracker = BaseTracker()
        else:
            from shared_utils import BaseTracker
            tracker = BaseTracker()
            # For ethereum, create a dummy function
            def is_base_native_token(token_symbol):
                return False
        
        # Get token metadata using tracker's Alchemy connection
        metadata_result = tracker.make_alchemy_request("alchemy_getTokenMetadata", [contract_address])
        
        metadata = {}
        if metadata_result.get('result'):
            result = metadata_result['result']
            metadata = {
                'name': result.get('name'),
                'symbol': result.get('symbol'), 
                'decimals': result.get('decimals'),
                'totalSupply': result.get('totalSupply'),
                'logo': result.get('logo')
            }
        
        # Get recent activity from our cached data
        activity = {}
        purchases = []
        
        # Check both buy and sell cache for this token
        cache_key_buy = f'{network}_buy'
        cache_key_sell = f'{network}_sell'
        
        cached_buy_data = service.get_cached_data(cache_key_buy)
        cached_sell_data = service.get_cached_data(cache_key_sell)
        
        # Search for token in buy data
        token_symbol = metadata.get('symbol', '').upper()
        
        if cached_buy_data and cached_buy_data.get('top_tokens'):
            for token_data in cached_buy_data['top_tokens']:
                if (token_data.get('contract_address', '').lower() == contract_address.lower() or 
                    token_data.get('token', '').upper() == token_symbol):
                    
                    activity = {
                        'wallet_count': token_data.get('wallet_count', 0),
                        'total_eth_spent': token_data.get('total_eth_spent', 0),
                        'alpha_score': token_data.get('alpha_score', 0),
                        'platforms': token_data.get('platforms', [])
                    }
                    break
        
        # Get sell pressure data if available
        sell_pressure = {}
        if cached_sell_data and cached_sell_data.get('top_tokens'):
            for token_data in cached_sell_data['top_tokens']:
                if (token_data.get('contract_address', '').lower() == contract_address.lower() or 
                    token_data.get('token', '').upper() == token_symbol):
                    
                    sell_pressure = {
                        'wallet_count': token_data.get('wallet_count', 0),
                        'total_estimated_eth': token_data.get('total_estimated_eth', 0),
                        'sell_score': token_data.get('sell_score', 0),
                        'methods': token_data.get('methods', [])
                    }
                    break
        
        # Generate mock recent purchases for demonstration
        # In a real implementation, you'd store purchase details during analysis
        if activity.get('wallet_count', 0) > 0:
            # Create sample purchases based on activity data
            platforms = activity.get('platforms', ['Unknown'])
            wallet_count = activity['wallet_count']
            total_eth = activity.get('total_eth_spent', 0)
            
            for i in range(min(wallet_count, 10)):  # Show up to 10 purchases
                purchases.append({
                    'wallet': f'0x{hex(0x1000000000000000000000000000000000000000 + i)[2:].zfill(40)}',
                    'amount': (total_eth / wallet_count) * (1 + (i * 0.1)),  # Vary amounts
                    'eth_spent': total_eth / wallet_count,
                    'platform': platforms[i % len(platforms)],
                    'tx_hash': f'0x{hex(0x2000000000000000000000000000000000000000000000000000000000000000 + i)[2:].zfill(64)}',
                    'wallet_score': 150 - (i * 10)  # Mock scores
                })
        
        # Determine if it's a Base native token
        is_base_native = False
        if network == 'base' and token_symbol:
            is_base_native = is_base_native_token(token_symbol)
        
        return jsonify({
            'contract_address': contract_address,
            'network': network,
            'metadata': metadata,
            'activity': activity,
            'sell_pressure': sell_pressure,
            'purchases': purchases,
            'is_base_native': is_base_native,
            'last_updated': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error in token_details: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': f'Failed to get token details: {str(e)}',
            'contract_address': contract_address,
            'network': network
        }), 500
