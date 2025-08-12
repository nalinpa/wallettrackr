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
import logging

# Import settings
from config.settings import settings, analysis_config, monitor_config, alchemy_config
from auto_monitor import monitor
from tracker.tracker_utils import BaseTracker, NetworkSpecificMixins
from tracker.buy_tracker import ComprehensiveBuyTracker
from tracker.sell_tracker import ComprehensiveSellTracker


api_bp = Blueprint('api', __name__)
service = AnalysisService()

# Configure logger
logger = logging.getLogger(__name__)

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

def get_analysis_params():
    """Get analysis parameters from request or use defaults from settings"""
    try:
        # Try to get from request context
        num_wallets = request.args.get('wallets', analysis_config.default_wallet_count, type=int)
        days_back = request.args.get('days', None, type=int)
        network = request.args.get('network', 'base')
    except RuntimeError:
        # Outside request context, use defaults
        num_wallets = analysis_config.default_wallet_count
        days_back = None
        network = 'base'
    
    # Apply limits from settings
    num_wallets = min(num_wallets, analysis_config.max_wallet_count)
    
    # Set default days_back based on network from settings
    if days_back is None:
        try:
            network_config = settings.get_network_config(network)
            days_back = network_config['default_days_back']
        except:
            # Fallback if network config fails
            if network == 'base':
                days_back = analysis_config.default_days_back_base
            else:
                days_back = analysis_config.default_days_back_eth
    
    days_back = min(days_back, analysis_config.max_days_back)
    
    logger.info(f"Analysis params: network={network}, wallets={num_wallets}, days={days_back}")
    
    return num_wallets, days_back, network

def should_exclude_token(token_symbol):
    """Check if token should be excluded based on settings"""
    return token_symbol.upper() in [t.upper() for t in analysis_config.excluded_tokens]

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

def generate_sse_stream(network, analysis_type, message_queue, params=None):
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
            # Use passed parameters or get defaults (not from request context)
            if params:
                num_wallets, days_back = params['num_wallets'], params['days_back']
            else:
                # Use defaults from settings
                num_wallets = analysis_config.default_wallet_count
                if network == 'base':
                    days_back = analysis_config.default_days_back_base
                else:
                    days_back = analysis_config.default_days_back_eth
            
            # Get network config
            try:
                network_config = settings.get_network_config(network)
                min_eth_value = network_config['min_eth_value']
            except:
                min_eth_value = analysis_config.min_eth_value
            
            logger.info(f"Starting {network} {analysis_type} analysis with {num_wallets} wallets, {days_back} days back, min ETH: {min_eth_value}")
            
            # Import and run the appropriate analyzer
            if network == 'eth' and analysis_type == 'buy':
                analyzer = ComprehensiveBuyTracker()
                results = analyzer.analyze_all_trading_methods(
                    num_wallets=num_wallets, 
                    days_back=days_back
                )
            elif network == 'eth' and analysis_type == 'sell':
                analyzer = ComprehensiveSellTracker("ethereum")
                results = analyzer.analyze_all_sell_methods(
                    num_wallets=num_wallets, 
                    days_back=days_back
                )
            elif network == 'base' and analysis_type == 'buy':
                analyzer = ComprehensiveBuyTracker("base")
                results = analyzer.analyze_all_trading_methods(
                    num_wallets=num_wallets, 
                    days_back=days_back
                )
            elif network == 'base' and analysis_type == 'sell':
                analyzer = ComprehensiveSellTracker("base")
                results = analyzer.analyze_all_sell_methods(
                    num_wallets=num_wallets, 
                    days_back=days_back
                )
            else:
                results = None
            
            # Filter excluded tokens if results exist
            if results and results.get('ranked_tokens'):
                filtered_tokens = []
                for token_tuple in results['ranked_tokens']:
                    # ranked_tokens is a list of tuples: (token, data, alpha_score)
                    if isinstance(token_tuple, tuple) and len(token_tuple) >= 3:
                        token_symbol = token_tuple[0]  # First element is the token symbol
                        if not should_exclude_token(token_symbol):
                            filtered_tokens.append(token_tuple)
                        else:
                            logger.debug(f"Excluding token {token_symbol} based on settings")
                    else:
                        # Fallback for unexpected format
                        filtered_tokens.append(token_tuple)
                
                results['ranked_tokens'] = filtered_tokens
                logger.info(f"Filtered to {len(filtered_tokens)} tokens after excluding configured tokens")
            
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
                
                # Send the formatted results through SSE
                message_queue.put({
                    'type': 'results',
                    'data': response_data
                })
            
            # Send completion message
            message_queue.put({
                'type': 'complete', 
                'status': 'success',
                'has_results': bool(results and results.get('ranked_tokens')),
                'config_used': {
                    'num_wallets': num_wallets,
                    'days_back': days_back,
                    'min_eth_value': min_eth_value,
                    'excluded_tokens_count': len(analysis_config.excluded_tokens)
                }
            })
            
        except Exception as e:
            logger.error(f"Analysis error: {e}", exc_info=True)
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
        # Get expected wallet count from parameters or defaults
        if params:
            num_wallets = params['num_wallets']
        else:
            num_wallets = analysis_config.default_wallet_count
            
        wallet_count = 0
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
                
                # Track progress based on settings
                if 'message' in message and 'Wallet:' in message.get('message', ''):
                    wallet_count += 1
                    progress = int((wallet_count / num_wallets) * 100)
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
    
    # Get parameters from request context before passing to generator
    try:
        num_wallets, days_back, _ = get_analysis_params()
        params = {'num_wallets': num_wallets, 'days_back': days_back}
    except:
        params = None
    
    return Response(
        generate_sse_stream('eth', 'buy', message_queue, params),
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
    
    # Get parameters from request context before passing to generator
    try:
        num_wallets, days_back, _ = get_analysis_params()
        params = {'num_wallets': num_wallets, 'days_back': days_back}
    except:
        params = None
    
    return Response(
        generate_sse_stream('eth', 'sell', message_queue, params),
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
    
    # Get parameters from request context before passing to generator
    try:
        num_wallets, days_back, _ = get_analysis_params()
        params = {'num_wallets': num_wallets, 'days_back': days_back}
    except:
        params = None
    
    return Response(
        generate_sse_stream('base', 'buy', message_queue, params),
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
    
    # Get parameters from request context before passing to generator
    try:
        num_wallets, days_back, _ = get_analysis_params()
        params = {'num_wallets': num_wallets, 'days_back': days_back}
    except:
        params = None
    
    return Response(
        generate_sse_stream('base', 'sell', message_queue, params),
        mimetype="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )
    
# Keep existing endpoints but enhance with settings
@api_bp.route('/eth/buy')
def eth_buy_analysis():
    """ETH mainnet buy analysis"""
    try:
        num_wallets, days_back, _ = get_analysis_params()
        network_config = settings.get_network_config('ethereum')
        
        logger.info(f"ETH buy analysis: {num_wallets} wallets, {days_back} days")
        
        from tracker.buy_tracker import EthComprehensiveTracker
        analyzer = EthComprehensiveTracker()
        
        if not analyzer.test_connection():
            logger.error("ETH connection test failed")
            return jsonify({"error": "Connection failed"}), 500
        
        results = analyzer.analyze_all_trading_methods(
            num_wallets=num_wallets, 
            days_back=days_back
        )
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant ETH buy activity found",
                "total_purchases": 0,
                "unique_tokens": 0,
                "total_eth_spent": 0,
                "config": {
                    "num_wallets": num_wallets,
                    "days_back": days_back,
                    "min_eth_value": network_config['min_eth_value']
                }
            })
        
        # Filter excluded tokens
        if results.get('ranked_tokens'):
            filtered_tokens = []
            for token_tuple in results['ranked_tokens']:
                # ranked_tokens is a list of tuples: (token, data, alpha_score)
                if isinstance(token_tuple, tuple) and len(token_tuple) >= 3:
                    token_symbol = token_tuple[0]  # First element is the token symbol
                    if not should_exclude_token(token_symbol):
                        filtered_tokens.append(token_tuple)
                else:
                    # Fallback for unexpected format
                    filtered_tokens.append(token_tuple)
            results['ranked_tokens'] = filtered_tokens
        
        response_data = service.format_buy_response(results, "ethereum")
        service.cache_data('eth_buy', response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"ETH buy analysis failed: {e}", exc_info=True)
        return jsonify({
            "error": f"ETH buy analysis failed: {str(e)}",
            "traceback": traceback.format_exc() if settings.flask.debug else None
        }), 500

@api_bp.route('/eth/sell')
def eth_sell_analysis():
    """ETH mainnet sell analysis"""
    try:
        num_wallets, days_back, _ = get_analysis_params()
        
        from tracker.sell_tracker import EthComprehensiveSellTracker
        analyzer = EthComprehensiveSellTracker("ethereum")
        
        if not analyzer.test_connection():
            return jsonify({"error": "Connection failed"}), 500
        
        results = analyzer.analyze_all_sell_methods(
            num_wallets=num_wallets, 
            days_back=days_back
        )
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant ETH sell pressure detected",
                "total_sells": 0,
                "unique_tokens": 0,
                "total_estimated_eth": 0
            })
        
        # Filter excluded tokens
        if results.get('ranked_tokens'):
            filtered_tokens = []
            for token_tuple in results['ranked_tokens']:
                # ranked_tokens is a list of tuples: (token, data, alpha_score)
                if isinstance(token_tuple, tuple) and len(token_tuple) >= 3:
                    token_symbol = token_tuple[0]  # First element is the token symbol
                    if not should_exclude_token(token_symbol):
                        filtered_tokens.append(token_tuple)
                else:
                    # Fallback for unexpected format
                    filtered_tokens.append(token_tuple)
            results['ranked_tokens'] = filtered_tokens
        
        response_data = service.format_sell_response(results, "ethereum")
        service.cache_data('eth_sell', response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"ETH sell analysis failed: {e}", exc_info=True)
        return jsonify({
            "error": f"ETH sell analysis failed: {str(e)}",
            "traceback": traceback.format_exc() if settings.flask.debug else None
        }), 500

@api_bp.route('/base/buy')
def base_buy_analysis():
    """Base network buy analysis"""
    try:
        num_wallets, days_back, _ = get_analysis_params()
        network_config = settings.get_network_config('base')
        
        logger.info(f"Base buy analysis: {num_wallets} wallets, {days_back} days")

        analyzer = ComprehensiveBuyTracker()

        if not analyzer.test_connection():
            return jsonify({"error": "Base connection failed"}), 500
        
        results = analyzer.analyze_all_trading_methods(
            num_wallets=num_wallets, 
            days_back=days_back
        )
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant Base buy activity found",
                "total_purchases": 0,
                "unique_tokens": 0,
                "total_eth_spent": 0,
                "config": {
                    "num_wallets": num_wallets,
                    "days_back": days_back,
                    "min_eth_value": network_config['min_eth_value']
                }
            })
        
        # Filter excluded tokens
        if results.get('ranked_tokens'):
            filtered_tokens = []
            for token_tuple in results['ranked_tokens']:
                # ranked_tokens is a list of tuples: (token, data, alpha_score)
                if isinstance(token_tuple, tuple) and len(token_tuple) >= 3:
                    token_symbol = token_tuple[0]  # First element is the token symbol
                    if not should_exclude_token(token_symbol):
                        filtered_tokens.append(token_tuple)
                else:
                    # Fallback for unexpected format
                    filtered_tokens.append(token_tuple)
            results['ranked_tokens'] = filtered_tokens
        
        response_data = service.format_buy_response(results, "base")
        service.cache_data('base_buy', response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Base buy analysis failed: {e}", exc_info=True)
        return jsonify({
            "error": f"Base buy analysis failed: {str(e)}",
            "traceback": traceback.format_exc() if settings.flask.debug else None
        }), 500

@api_bp.route('/base/sell')
def base_sell_analysis():
    """Base network sell analysis"""
    try:
        num_wallets, days_back, _ = get_analysis_params()

        analyzer = ComprehensiveSellTracker("base")

        if not analyzer.test_connection():
            return jsonify({"error": "Base connection failed"}), 500
        
        results = analyzer.analyze_all_sell_methods(
            num_wallets=num_wallets, 
            days_back=days_back
        )
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant Base sell pressure detected",
                "total_sells": 0,
                "unique_tokens": 0,
                "total_estimated_eth": 0
            })
        
        # Filter excluded tokens
        if results.get('ranked_tokens'):
            filtered_tokens = []
            for token_tuple in results['ranked_tokens']:
                # ranked_tokens is a list of tuples: (token, data, alpha_score)
                if isinstance(token_tuple, tuple) and len(token_tuple) >= 3:
                    token_symbol = token_tuple[0]  # First element is the token symbol
                    if not should_exclude_token(token_symbol):
                        filtered_tokens.append(token_tuple)
                else:
                    # Fallback for unexpected format
                    filtered_tokens.append(token_tuple)
            results['ranked_tokens'] = filtered_tokens
        
        response_data = service.format_sell_response(results, "base")
        service.cache_data('base_sell', response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Base sell analysis failed: {e}", exc_info=True)
        return jsonify({
            "error": f"Base sell analysis failed: {str(e)}",
            "traceback": traceback.format_exc() if settings.flask.debug else None
        }), 500

@api_bp.route('/status')
def api_status():
    """API status and cached data"""
    cache_status = service.get_cache_status()
    
    return jsonify({
        "status": "online",
        "environment": settings.environment,
        "cached_data": cache_status,
        "last_updated": service.get_last_updated(),
        "supported_networks": [net.value for net in settings.monitor.supported_networks],
        "config": {
            "analysis": {
                "default_wallet_count": analysis_config.default_wallet_count,
                "max_wallet_count": analysis_config.max_wallet_count,
                "max_days_back": analysis_config.max_days_back,
                "excluded_tokens_count": len(analysis_config.excluded_tokens)
            },
            "monitor": {
                "default_interval": monitor_config.default_check_interval_minutes,
                "supported_networks": [net.value for net in monitor_config.supported_networks]
            }
        },
        "endpoints": [
            "/api/eth/buy", "/api/eth/sell",
            "/api/base/buy", "/api/base/sell",
            "/api/eth/buy/stream", "/api/eth/sell/stream",
            "/api/base/buy/stream", "/api/base/sell/stream"
        ]
    })
    
@api_bp.route('/monitor/status', methods=['GET'])
def monitor_status():
    """Get monitor status"""
    try:
        logger.info("Monitor status request received")
        
        if monitor:
            status = monitor.get_status()
            logger.info(f"Monitor status: Running={status.get('is_running', False)}")
            return jsonify(status)
        else:
            logger.warning("Monitor not initialized, returning default status")
            return jsonify({
                'is_running': False,
                'error': 'Monitor not initialized',
                'last_check': None,
                'next_check': None,
                'config': {
                    'check_interval_minutes': monitor_config.default_check_interval_minutes,
                    'networks': [net.value for net in monitor_config.default_networks],
                    'num_wallets': analysis_config.default_wallet_count,
                    'use_interval_for_timeframe': True
                },
                'notification_channels': {
                    'console': True,
                    'file': True,
                    'webhook': False
                },
                'alert_thresholds': monitor_config.alert_thresholds,
                'recent_alerts': [],
                'stats': {
                    'total_alerts': 0,
                    'known_tokens': 0,
                    'seen_purchases': 0
                }
            })
    except Exception as e:
        logger.error(f"Error getting monitor status: {e}", exc_info=True)
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

# Monitor endpoints with settings integration
@api_bp.route('/monitor/start', methods=['POST'])
def start_monitor():
    """Start the automated monitoring"""
    try:
        logger.info("Monitor start request received")
        if monitor:
            result = monitor.start_monitoring()
            logger.info(f"Monitor start result: {result}")
            return jsonify(result)
        else:
            return jsonify({'status': 'error', 'message': 'Monitor not available'}), 500
    except Exception as e:
        logger.error(f"Error starting monitor: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/monitor/stop', methods=['POST'])
def stop_monitor():
    """Stop the automated monitoring"""
    try:
        logger.info("Monitor stop request received")
        if monitor:
            result = monitor.stop_monitoring()
            logger.info(f"Monitor stop result: {result}")
            return jsonify(result)
        else:
            return jsonify({'status': 'error', 'message': 'Monitor not available'}), 500
    except Exception as e:
        logger.error(f"Error stopping monitor: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/monitor/check-now', methods=['POST'])
def check_now():
    """Trigger an immediate check"""
    try:
        logger.info("Immediate check requested")
        print("\n" + "="*60)
        print("🔍 IMMEDIATE CHECK REQUESTED")
        print("="*60)
        
        if not monitor:
            logger.error("Monitor not available")
            return jsonify({'status': 'error', 'message': 'Monitor not available'}), 500
        
        # Run the check in a background thread
        def run_check():
            try:
                print("🚀 Starting immediate check in background thread...")
                monitor.check_for_new_tokens()
                print("✅ Immediate check completed")
            except Exception as e:
                logger.error(f"Error during immediate check: {e}", exc_info=True)
        
        thread = threading.Thread(target=run_check)
        thread.daemon = True
        thread.start()
        
        return jsonify({'status': 'success', 'message': 'Check initiated - see console for output'})
    except Exception as e:
        logger.error(f"Error initiating check: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Keep all other monitor endpoints with proper logging...
@api_bp.route('/monitor/config', methods=['GET', 'POST'])
def monitor_config_endpoint():
    """Get or update monitor configuration"""
    try:
        if not monitor:
            if request.method == 'POST':
                return jsonify({'status': 'error', 'message': 'Monitor not available'}), 500
            else:
                # Return default config from settings
                return jsonify({
                    'check_interval_minutes': monitor_config.default_check_interval_minutes,
                    'networks': [net.value for net in monitor_config.default_networks],
                    'num_wallets': analysis_config.default_wallet_count,
                    'use_interval_for_timeframe': True,
                    'alert_thresholds': monitor_config.alert_thresholds
                })
            
        if request.method == 'POST':
            logger.info("Monitor config update request received")
            new_config = request.json
            logger.info(f"New config: {new_config}")
            
            # Validate config against settings limits
            if 'check_interval_minutes' in new_config:
                interval = new_config['check_interval_minutes']
                if interval < monitor_config.min_check_interval_minutes:
                    return jsonify({
                        'status': 'error', 
                        'message': f'Interval cannot be less than {monitor_config.min_check_interval_minutes} minutes'
                    }), 400
                if interval > monitor_config.max_check_interval_minutes:
                    return jsonify({
                        'status': 'error', 
                        'message': f'Interval cannot exceed {monitor_config.max_check_interval_minutes} minutes'
                    }), 400
            
            monitor.config.update(new_config)
            monitor.save_config()
            return jsonify({'status': 'success', 'config': monitor.config})
        
        logger.info("Monitor config request received")
        return jsonify(monitor.config)
    except Exception as e:
        logger.error(f"Error with monitor config: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Include all other existing monitor endpoints...
@api_bp.route('/monitor/alerts', methods=['GET'])
def get_alerts():
    """Get recent alerts"""
    try:
        logger.info("Alerts request received")
        if not monitor:
            return jsonify([])
            
        limit = request.args.get('limit', monitor_config.max_stored_alerts, type=int)
        limit = min(limit, monitor_config.max_stored_alerts)  # Enforce settings limit
        
        alerts = [alert.to_dict() for alert in monitor.alerts[-limit:]]
        logger.info(f"Returning {len(alerts)} alerts")
        return jsonify(alerts)
    except Exception as e:
        logger.error(f"Error getting alerts: {e}", exc_info=True)
        return jsonify([])

@api_bp.route('/monitor/thresholds', methods=['POST'])
def update_thresholds():
    """Update alert thresholds"""
    try:
        if not monitor:
            return jsonify({'status': 'error', 'message': 'Monitor not available'}), 500
            
        logger.info("Threshold update request received")
        thresholds = request.json
        logger.info(f"New thresholds: {thresholds}")
        
        # Validate thresholds against reasonable limits
        if 'min_wallets' in thresholds and thresholds['min_wallets'] < 1:
            return jsonify({'status': 'error', 'message': 'min_wallets must be at least 1'}), 400
        
        monitor.alert_thresholds.update(thresholds)
        return jsonify({'status': 'success', 'thresholds': monitor.alert_thresholds})
    except Exception as e:
        logger.error(f"Error updating thresholds: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/monitor/notifications', methods=['POST'])
def update_notifications():
    """Update notification settings"""
    try:
        if not monitor:
            return jsonify({'status': 'error', 'message': 'Monitor not available'}), 500
            
        logger.info("Notification settings update request received")
        notification_settings = request.json
        logger.info(f"New settings: {notification_settings}")
        monitor.notification_channels.update(notification_settings)
        return jsonify({'status': 'success', 'channels': monitor.notification_channels})
    except Exception as e:
        logger.error(f"Error updating notifications: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/monitor/test', methods=['GET'])
def test_monitor():
    """Test endpoint to verify monitor is working"""
    logger.info("Monitor test endpoint called")
    
    test_results = {
        'monitor_available': monitor is not None,
        'monitor_module': False,
        'base_tracker': False,
        'eth_tracker': False,
        'settings_loaded': True,
        'alchemy_config': bool(alchemy_config.api_key)
    }
    
    try:
        # Test monitor module
        if monitor:
            test_results['monitor_module'] = hasattr(monitor, 'get_status')
        
        tracker = ComprehensiveBuyTracker()
        test_results['base_tracker'] = hasattr(tracker, 'test_connection')
        
        # Test eth tracker
        from tracker.buy_tracker import EthComprehensiveTracker
        tracker = EthComprehensiveTracker()
        test_results['eth_tracker'] = hasattr(tracker, 'test_connection')
        
        return jsonify({
            'status': 'success',
            'message': 'Monitor test completed',
            'results': test_results,
            'settings_info': {
                'environment': settings.environment,
                'supported_networks': [net.value for net in settings.monitor.supported_networks],
                'default_wallet_count': analysis_config.default_wallet_count,
                'excluded_tokens_count': len(analysis_config.excluded_tokens)
            }
        })
        
    except Exception as e:
        logger.error(f"Monitor test failed: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Monitor test failed: {str(e)}',
            'results': test_results
        }), 500

@api_bp.route('/config', methods=['GET'])
def get_api_config():
    """Get current API configuration (safe, non-sensitive data only)"""
    try:
        return jsonify({
            'status': 'success',
            'config': {
                'environment': settings.environment,
                'analysis': {
                    'default_wallet_count': analysis_config.default_wallet_count,
                    'max_wallet_count': analysis_config.max_wallet_count,
                    'default_days_back_eth': analysis_config.default_days_back_eth,
                    'default_days_back_base': analysis_config.default_days_back_base,
                    'max_days_back': analysis_config.max_days_back,
                    'min_eth_value': analysis_config.min_eth_value,
                    'min_eth_value_base': analysis_config.min_eth_value_base,
                    'excluded_tokens_count': len(analysis_config.excluded_tokens),
                    'alpha_scoring': analysis_config.alpha_scoring
                },
                'monitor': {
                    'default_check_interval_minutes': monitor_config.default_check_interval_minutes,
                    'min_check_interval_minutes': monitor_config.min_check_interval_minutes,
                    'max_check_interval_minutes': monitor_config.max_check_interval_minutes,
                    'default_networks': [net.value for net in monitor_config.default_networks],
                    'supported_networks': [net.value for net in monitor_config.supported_networks],
                    'alert_thresholds': monitor_config.alert_thresholds,
                    'max_alerts_per_notification': monitor_config.max_alerts_per_notification,
                    'max_stored_alerts': monitor_config.max_stored_alerts
                },
                'alchemy': {
                    'rate_limit_per_second': alchemy_config.rate_limit_per_second,
                    'timeout_seconds': alchemy_config.timeout_seconds,
                    'max_retries': alchemy_config.max_retries,
                    'api_key_configured': bool(alchemy_config.api_key)
                }
            }
        })
    except Exception as e:
        logger.error(f"Error getting API config: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Failed to get configuration: {str(e)}'
        }), 500

@api_bp.route('/config/excluded-tokens', methods=['GET', 'POST'])
def manage_excluded_tokens():
    """Get or update excluded tokens list"""
    try:
        if request.method == 'GET':
            return jsonify({
                'status': 'success',
                'excluded_tokens': analysis_config.excluded_tokens,
                'count': len(analysis_config.excluded_tokens)
            })
        
        elif request.method == 'POST':
            data = request.json
            action = data.get('action')  # 'add', 'remove', 'replace'
            tokens = data.get('tokens', [])
            
            if action == 'add':
                for token in tokens:
                    if token.upper() not in [t.upper() for t in analysis_config.excluded_tokens]:
                        analysis_config.excluded_tokens.append(token.upper())
                        
            elif action == 'remove':
                analysis_config.excluded_tokens = [
                    t for t in analysis_config.excluded_tokens 
                    if t.upper() not in [token.upper() for token in tokens]
                ]
                
            elif action == 'replace':
                analysis_config.excluded_tokens = [token.upper() for token in tokens]
                
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Invalid action. Use "add", "remove", or "replace"'
                }), 400
            
            logger.info(f"Updated excluded tokens list: {action} - {tokens}")
            
            return jsonify({
                'status': 'success',
                'message': f'Successfully {action}ed tokens',
                'excluded_tokens': analysis_config.excluded_tokens,
                'count': len(analysis_config.excluded_tokens)
            })
            
    except Exception as e:
        logger.error(f"Error managing excluded tokens: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Failed to manage excluded tokens: {str(e)}'
        }), 500

@api_bp.route('/networks', methods=['GET'])
def get_networks():
    """Get supported networks and their configurations"""
    try:
        networks_info = {}
        
        for network in settings.monitor.supported_networks:
            try:
                network_config = settings.get_network_config(network.value)
                networks_info[network.value] = {
                    'supported': True,
                    'min_eth_value': network_config['min_eth_value'],
                    'default_days_back': network_config['default_days_back'],
                    'alchemy_url_configured': bool(network_config.get('alchemy_url'))
                }
            except Exception as e:
                networks_info[network.value] = {
                    'supported': False,
                    'error': str(e)
                }
        
        return jsonify({
            'status': 'success',
            'networks': networks_info,
            'default_networks': [net.value for net in monitor_config.default_networks]
        })
        
    except Exception as e:
        logger.error(f"Error getting networks info: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Failed to get networks info: {str(e)}'
        }), 500
        
@api_bp.route('/token/<contract_address>')
def token_details(contract_address):
    """Get detailed token information using shared utilities"""
    try:
        from datetime import datetime
        import os
        
        network = request.args.get('network', 'ethereum')
        
        # Validate network against settings
        supported_networks = [net.value for net in settings.monitor.supported_networks]
        if network not in supported_networks:
            return jsonify({
                'error': f'Network {network} not supported. Supported networks: {supported_networks}',
                'contract_address': contract_address,
                'network': network
            }), 400
        
        # Get network-specific configuration
        try:
            network_config = settings.get_network_config(network)
        except ValueError as e:
            return jsonify({
                'error': str(e),
                'contract_address': contract_address,
                'network': network
            }), 400
        
        tracker = BaseTracker(network)
        is_base_native_token = (
            NetworkSpecificMixins.BaseMixin.is_base_native_token 
            if network == 'base' 
            else lambda x: False
        )
        
        # Get token metadata using tracker's Alchemy connection
        try:
            metadata_result = tracker.make_alchemy_request("alchemy_getTokenMetadata", [contract_address])
        except Exception as e:
            logger.error(f"Failed to get token metadata: {e}")
            metadata_result = {}
        
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
        
        # Check if token should be excluded based on settings
        token_symbol = metadata.get('symbol', '')
        is_excluded = should_exclude_token(token_symbol)
        
        # Get recent activity from our cached data
        activity = {}
        purchases = []
        
        # Check both buy and sell cache for this token
        cache_key_buy = f'{network}_buy'
        cache_key_sell = f'{network}_sell'
        
        cached_buy_data = service.get_cached_data(cache_key_buy)
        cached_sell_data = service.get_cached_data(cache_key_sell)
        
        # Search for token in buy data
        if cached_buy_data and cached_buy_data.get('top_tokens'):
            for token_data in cached_buy_data['top_tokens']:
                if (token_data.get('contract_address', '').lower() == contract_address.lower() or 
                    token_data.get('token', '').upper() == token_symbol.upper()):
                    
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
                    token_data.get('token', '').upper() == token_symbol.upper()):
                    
                    sell_pressure = {
                        'wallet_count': token_data.get('wallet_count', 0),
                        'total_estimated_eth': token_data.get('total_estimated_eth', 0),
                        'sell_score': token_data.get('sell_score', 0),
                        'methods': token_data.get('methods', [])
                    }
                    break
        
        # Generate mock recent purchases for demonstration
        if activity.get('wallet_count', 0) > 0:
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
            'network_config': {
                'min_eth_value': network_config['min_eth_value'],
                'default_days_back': network_config['default_days_back']
            },
            'metadata': metadata,
            'activity': activity,
            'sell_pressure': sell_pressure,
            'purchases': purchases,
            'is_base_native': is_base_native,
            'is_excluded': is_excluded,
            'excluded_reason': 'Token symbol in excluded list' if is_excluded else None,
            'last_updated': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in token_details: {e}", exc_info=True)
        return jsonify({
            'error': f'Failed to get token details: {str(e)}',
            'contract_address': contract_address,
            'network': network,
            'traceback': traceback.format_exc() if settings.flask.debug else None
        }), 500

# Health check endpoint
@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for load balancers"""
    try:
        # Basic health checks
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'environment': settings.environment,
            'checks': {
                'settings_loaded': True,
                'alchemy_configured': bool(alchemy_config.api_key),
                'cache_service': hasattr(service, 'get_cache_status'),
                'monitor_available': monitor is not None
            }
        }
        
        # Check if any critical components are failing
        if not alchemy_config.api_key:
            health_status['status'] = 'degraded'
            health_status['warnings'] = ['Alchemy API key not configured']
        
        return jsonify(health_status)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500