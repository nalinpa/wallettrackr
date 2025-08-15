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

# Enhanced imports with Web3 support and fallbacks
try:
    from tracker.buy_tracker import Web3EnhancedBuyTracker as EnhancedBuyTracker
    from tracker.sell_tracker import Web3EnhancedSellTracker as EnhancedSellTracker
    from tracker.web3_utils import Web3Manager, test_all_web3_connections, get_web3_for_network
    WEB3_AVAILABLE = True
except ImportError as e:
    from tracker.buy_tracker import ComprehensiveBuyTracker as EnhancedBuyTracker
    from tracker.sell_tracker import ComprehensiveSellTracker as EnhancedSellTracker
    WEB3_AVAILABLE = False

# Legacy imports for fallback compatibility
from tracker.tracker_utils import BaseTracker, NetworkSpecificMixins

api_bp = Blueprint('api', __name__)
service = AnalysisService()

# Configure logger
logger = logging.getLogger(__name__)

# Global analysis tracking
analysis_in_progress = {
    'eth_buy': False,
    'eth_sell': False,
    'base_buy': False,
    'base_sell': False
}

# Global Web3 manager (if available)
web3_manager = None
if WEB3_AVAILABLE:
    try:
        web3_manager = Web3Manager()
        logger.info("🚀 Web3 Manager initialized successfully")
    except Exception as e:
        logger.warning(f"⚠️  Web3 Manager initialization failed: {e}")
        WEB3_AVAILABLE = False

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
    """Enhanced get analysis parameters with Web3 support"""
    try:
        # Try to get from request context
        num_wallets = request.args.get('wallets', 173, type=int)
        days_back = request.args.get('days', None, type=int)
        network = request.args.get('network', 'base')
        enhanced = request.args.get('enhanced', 'auto')  # auto, true, false
    except RuntimeError:
        # Outside request context, use defaults
        num_wallets = 173
        days_back = None
        network = 'base'
        enhanced = 'auto'
    
    # Set default days_back based on network from settings
    if days_back is None:
        try:
            network_config = settings.get_network_config(network)
            days_back = network_config['default_days_back']
        except Exception:
            # Fallback if network config fails
            if network == 'base':
                days_back = analysis_config.default_days_back_base
            else:
                days_back = analysis_config.default_days_back_eth
    
    days_back = min(days_back, analysis_config.max_days_back)
    
    # Determine if enhanced analysis should be used
    use_enhanced = False
    if enhanced == 'auto':
        use_enhanced = WEB3_AVAILABLE  # Use Web3 if available
    elif enhanced == 'true':
        use_enhanced = WEB3_AVAILABLE  # Force Web3 if available
    else:
        use_enhanced = False  # Force standard
    
    logger.info(f"Analysis params: network={network}, wallets={num_wallets}, days={days_back}, enhanced={use_enhanced}")
    
    return num_wallets, days_back, network, use_enhanced

def should_exclude_token(token_symbol):
    """Check if token should be excluded based on settings"""
    if not token_symbol:
        return False
    return token_symbol.upper() in [t.upper() for t in analysis_config.excluded_tokens]

def get_tracker_instance(network: str, analysis_type: str, enhanced: bool = None):
    """Get the appropriate tracker instance (enhanced or standard)"""
    if enhanced is None:
        enhanced = WEB3_AVAILABLE
    
    try:
        if analysis_type == 'buy':
            if enhanced and WEB3_AVAILABLE:
                # Try to use Web3 enhanced tracker
                return EnhancedBuyTracker(network), True
            else:
                # Use standard tracker
                from tracker.buy_tracker import ComprehensiveBuyTracker
                return ComprehensiveBuyTracker(network), False
        else:  # sell
            if enhanced and WEB3_AVAILABLE:
                # Try to use Web3 enhanced tracker
                return EnhancedSellTracker(network), True
            else:
                # Use standard tracker
                from tracker.sell_tracker import ComprehensiveSellTracker
                return ComprehensiveSellTracker(network), False
    except Exception as e:
        logger.warning(f"Failed to create enhanced tracker, falling back to standard: {e}")
        # Fallback to standard trackers
        if analysis_type == 'buy':
            from tracker.buy_tracker import ComprehensiveBuyTracker
            return ComprehensiveBuyTracker(network), False
        else:
            from tracker.sell_tracker import ComprehensiveSellTracker
            return ComprehensiveSellTracker(network), False

class EnhancedConsoleCapture:
    """Enhanced console capture that actually works"""
    
    def __init__(self, message_queue):
        self.message_queue = message_queue
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.original_print = print
        self.is_active = True
        
        # Override the global print function
        import builtins
        builtins.print = self.captured_print
    
    def captured_print(self, *args, **kwargs):
        """Capture print statements and send to SSE"""
        # Call original print for server logs
        try:
            self.original_print(*args, **kwargs)
        except Exception:
            pass
        
        # Capture for SSE
        if self.is_active and args:
            try:
                message = ' '.join(str(arg) for arg in args)
                if message.strip():
                    self._send_to_sse(message.strip())
            except Exception:
                pass
    
    def write(self, text):
        """Capture stdout/stderr writes"""
        try:
            # Always write to original for server logs
            self.original_stdout.write(text)
            self.original_stdout.flush()
            
            # Send to SSE if active
            if self.is_active and text.strip():
                self._send_to_sse(text.strip())
        except Exception:
            pass
    
    def _send_to_sse(self, text):
        """Send text to SSE with proper formatting"""
        try:
            # Determine message level with Web3 awareness
            level = self._determine_level(text)
            
            # Clean text
            display_text = self._clean_text(text)
            
            # Send to SSE queue
            message = {
                'type': 'console',
                'message': display_text,
                'level': level,
                'timestamp': time.time()
            }
            
            # Non-blocking put
            try:
                self.message_queue.put_nowait(message)
            except Exception:
                # If queue full, skip rather than block
                pass
                
        except Exception:
            # Don't crash analysis for SSE issues
            pass
    
    def _determine_level(self, text):
        """Determine log level from text content with Web3 awareness"""
        try:
            text_lower = text.lower()
            
            # Web3 enhanced indicators
            if any(indicator in text for indicator in ['🧠', '⚡', 'sophistication', 'Web3']):
                return 'highlight'
            elif any(indicator in text for indicator in ['✅', 'SUCCESS', '🚀', '💰', '🪙']):
                return 'success'
            elif any(indicator in text for indicator in ['⚠️', 'WARNING', 'WARN', 'fallback']):
                return 'warning'
            elif any(indicator in text for indicator in ['❌', 'ERROR', 'FAILED', 'Exception']):
                return 'error'
            elif any(indicator in text for indicator in ['🏆', '💎', '🔵', 'BOUGHT', 'SOLD']):
                return 'highlight'
            else:
                return 'info'
        except Exception:
            return 'info'
    
    def _clean_text(self, text):
        """Clean text for display"""
        try:
            cleaned = ' '.join(text.split())
            if len(cleaned) > 150:
                cleaned = cleaned[:147] + "..."
            return cleaned
        except Exception:
            return str(text)[:150]
    
    def flush(self):
        """Flush original streams"""
        try:
            self.original_stdout.flush()
        except Exception:
            pass
    
    def close(self):
        """Cleanup and restore original print"""
        try:
            self.is_active = False
            import builtins
            builtins.print = self.original_print
        except Exception:
            pass

def generate_sse_stream(network, analysis_type, message_queue, params=None):
    """Enhanced SSE stream generator with Web3 support"""
    analysis_key = f"{network}_{analysis_type}"

    # Check if analysis is already running
    global analysis_in_progress
    if analysis_in_progress.get(analysis_key, False):
        def already_running_generator():
            yield f"data: {json.dumps({'type': 'console', 'message': 'Analysis already in progress, please wait...', 'level': 'warning'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'status': 'already_running'})}\n\n"
        return already_running_generator()
    
    # Mark analysis as in progress
    analysis_in_progress[analysis_key] = True
    
    def run_analysis():
        """Run the enhanced analysis in a separate thread"""
        console_capture = None
        try:
            # Determine if we should use enhanced analysis
            enhanced_analysis = params.get('enhanced', WEB3_AVAILABLE) if params else WEB3_AVAILABLE
            
            # Send immediate feedback with Web3 status
            if enhanced_analysis and WEB3_AVAILABLE:
                message_queue.put({
                    'type': 'console',
                    'message': f'🚀⚡ Enhanced Web3 analysis started for {network} {analysis_type}',
                    'level': 'success'
                })
            else:
                message_queue.put({
                    'type': 'console',
                    'message': f'🔄📡 Standard analysis started for {network} {analysis_type}',
                    'level': 'info'
                })
            
            # Get parameters
            if params:
                num_wallets, days_back = params['num_wallets'], params['days_back']
            else:
                # Use defaults from settings
                num_wallets = 173
                if network == 'base':
                    days_back = analysis_config.default_days_back_base
                else:
                    days_back = analysis_config.default_days_back_eth
            
            message_queue.put({
                'type': 'console',
                'message': f'⚙️ Configuration: {num_wallets} wallets, {days_back} days | Web3: {"✅" if enhanced_analysis else "❌"}',
                'level': 'info'
            })
            
            # Setup console capture
            console_capture = EnhancedConsoleCapture(message_queue)
            
            # Get network config
            try:
                network_config = settings.get_network_config(network)
                min_eth_value = network_config['min_eth_value']
            except Exception:
                min_eth_value = analysis_config.min_eth_value
            
            logger.info(f"Starting {network} {analysis_type} analysis with {num_wallets} wallets, {days_back} days back, min ETH: {min_eth_value}")
            
            # Get the appropriate tracker (enhanced or standard)
            analyzer, is_enhanced = get_tracker_instance(network, analysis_type, enhanced_analysis)
            
            if is_enhanced:
                message_queue.put({
                    'type': 'console',
                    'message': f'🧠 Using Web3-Enhanced {analysis_type.title()} Tracker',
                    'level': 'highlight'
                })
            else:
                message_queue.put({
                    'type': 'console',
                    'message': f'📡 Using Standard {analysis_type.title()} Tracker',
                    'level': 'info'
                })
            
            # Run the analysis
            if analysis_type == 'buy':
                results = analyzer.analyze_all_trading_methods(
                    num_wallets=num_wallets, 
                    days_back=days_back,
                    max_wallets_for_sse=False
                )
            else:  # sell
                results = analyzer.analyze_all_sell_methods(
                    num_wallets=num_wallets, 
                    days_back=days_back,
                    max_wallets_for_sse=False
                )
            
            # Filter excluded tokens if results exist
            if results and results.get('ranked_tokens'):
                filtered_tokens = []
                for token_tuple in results['ranked_tokens']:
                    try:
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
                    except Exception as e:
                        logger.warning(f"Error processing token tuple {token_tuple}: {e}")
                        # Keep the token if we can't process it
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
                
                # Add Web3 enhancement status
                response_data['web3_enhanced'] = is_enhanced
                if is_enhanced and results.get('web3_analysis'):
                    response_data['web3_analysis'] = results['web3_analysis']
                
                # Cache the results with enhanced flag
                cache_key = f'{network}_{analysis_type}'
                service.cache_data(cache_key, response_data)
                
                # Send the formatted results through SSE
                message_queue.put({
                    'type': 'results',
                    'data': response_data
                })
                
                # Send Web3 insights if available
                if is_enhanced and results.get('web3_analysis'):
                    web3_data = results['web3_analysis']
                    if analysis_type == 'buy':
                        if web3_data.get('total_transactions_analyzed', 0) > 0:
                            sophisticated_pct = (web3_data.get('sophisticated_transactions', 0) / web3_data['total_transactions_analyzed']) * 100
                            message_queue.put({
                                'type': 'console',
                                'message': f'🧠 Web3 Insights: {sophisticated_pct:.1f}% sophisticated trades, {web3_data.get("gas_efficiency_avg", 0):.1f}% avg gas efficiency',
                                'level': 'highlight'
                            })
                    else:  # sell
                        if web3_data.get('total_transactions_analyzed', 0) > 0:
                            sophisticated_pct = (web3_data.get('sophisticated_sells', 0) / web3_data['total_transactions_analyzed']) * 100
                            panic_sells = web3_data.get('panic_sells', 0)
                            strategic_sells = web3_data.get('strategic_sells', 0)
                            message_queue.put({
                                'type': 'console',
                                'message': f'🧠 Sell Insights: {sophisticated_pct:.1f}% sophisticated, {panic_sells} panic, {strategic_sells} strategic',
                                'level': 'highlight'
                            })
            
            # Send completion message with Web3 status
            message_queue.put({
                'type': 'complete', 
                'status': 'success',
                'has_results': bool(results and results.get('ranked_tokens')),
                'web3_enhanced': is_enhanced,
                'config_used': {
                    'num_wallets': num_wallets,
                    'days_back': days_back,
                    'min_eth_value': min_eth_value,
                    'excluded_tokens_count': len(analysis_config.excluded_tokens),
                    'enhanced_analysis': is_enhanced
                }
            })
            
        except Exception as e:
            logger.error(f"Analysis error: {e}", exc_info=True)
            # Send detailed error info via SSE
            message_queue.put({
                'type': 'console',
                'message': f'❌ Detailed error: {str(e)}',
                'level': 'error'
            })
            
            # Send traceback lines
            try:
                tb_lines = traceback.format_exc().split('\n')[-5:]  # Last 5 lines
                for line in tb_lines:
                    if line.strip():
                        message_queue.put({
                            'type': 'console',
                            'message': f'🔍 {line.strip()}',
                            'level': 'error'
                        })
            except Exception:
                pass
            
            message_queue.put({
                'type': 'console',
                'message': f'Error: {str(e)}',
                'level': 'error'
            })
            message_queue.put({'type': 'complete', 'status': 'error', 'error': str(e)})
        
        finally:
            # Cleanup
            if console_capture:
                console_capture.close()
            # Mark analysis as complete
            analysis_in_progress[analysis_key] = False
    
    # Start analysis in background thread
    analysis_thread = threading.Thread(target=run_analysis)
    analysis_thread.daemon = True
    analysis_thread.start()

    def generate():
        """Generate SSE messages with Web3 awareness"""
        # Get expected wallet count from parameters or defaults
        if params:
            num_wallets = params['num_wallets']
        else:
            num_wallets = 173
            
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

# SSE endpoints with enhanced Web3 support
@api_bp.route('/eth/buy/stream')
def eth_buy_stream():
    """Enhanced SSE endpoint for ETH buy analysis"""
    try:
        message_queue = Queue()
        
        # Get parameters from request context before passing to generator
        try:
            num_wallets, days_back, network, enhanced = get_analysis_params()
            params = {
                'num_wallets': num_wallets, 
                'days_back': days_back,
                'enhanced': enhanced
            }
        except Exception:
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
    except Exception as e:
        logger.error(f"Error in eth_buy_stream: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@api_bp.route('/eth/sell/stream')
def eth_sell_stream():
    """Enhanced SSE endpoint for ETH sell analysis"""
    try:
        message_queue = Queue()
        
        # Get parameters from request context before passing to generator
        try:
            num_wallets, days_back, network, enhanced = get_analysis_params()
            params = {
                'num_wallets': num_wallets, 
                'days_back': days_back,
                'enhanced': enhanced
            }
        except Exception:
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
    except Exception as e:
        logger.error(f"Error in eth_sell_stream: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@api_bp.route('/base/buy/stream')
def base_buy_stream():
    """Enhanced SSE endpoint for Base buy analysis"""
    try:
        message_queue = Queue()
        
        # Get parameters from request context before passing to generator
        try:
            num_wallets, days_back, network, enhanced = get_analysis_params()
            params = {
                'num_wallets': num_wallets, 
                'days_back': days_back,
                'enhanced': enhanced
            }
        except Exception:
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
    except Exception as e:
        logger.error(f"Error in base_buy_stream: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@api_bp.route('/base/sell/stream')
def base_sell_stream():
    """Enhanced SSE endpoint for Base sell analysis"""
    try:
        message_queue = Queue()
        
        # Get parameters from request context before passing to generator
        try:
            num_wallets, days_back, network, enhanced = get_analysis_params()
            params = {
                'num_wallets': num_wallets, 
                'days_back': days_back,
                'enhanced': enhanced
            }
        except Exception:
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
    except Exception as e:
        logger.error(f"Error in base_sell_stream: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# Enhanced regular analysis endpoints
@api_bp.route('/eth/buy')
def eth_buy_analysis():
    """Enhanced ETH mainnet buy analysis"""
    try:
        num_wallets, days_back, network, enhanced = get_analysis_params()
        network_config = settings.get_network_config('ethereum')
        
        logger.info(f"ETH buy analysis: {num_wallets} wallets, {days_back} days, enhanced={enhanced}")
        
        # Get appropriate tracker
        analyzer, is_enhanced = get_tracker_instance("ethereum", "buy", enhanced)
        
        if not analyzer.test_connection():
            logger.error("ETH connection test failed")
            return jsonify({"error": "Connection failed"}), 500
        
        results = analyzer.analyze_all_trading_methods(
            num_wallets=num_wallets, 
            days_back=days_back,
            max_wallets_for_sse=False
        )
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant ETH buy activity found",
                "total_purchases": 0,
                "unique_tokens": 0,
                "total_eth_spent": 0,
                "web3_enhanced": is_enhanced,
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
                try:
                    # ranked_tokens is a list of tuples: (token, data, alpha_score)
                    if isinstance(token_tuple, tuple) and len(token_tuple) >= 3:
                        token_symbol = token_tuple[0]  # First element is the token symbol
                        if not should_exclude_token(token_symbol):
                            filtered_tokens.append(token_tuple)
                    else:
                        # Fallback for unexpected format
                        filtered_tokens.append(token_tuple)
                except Exception as e:
                    logger.warning(f"Error processing token tuple: {e}")
                    filtered_tokens.append(token_tuple)
            results['ranked_tokens'] = filtered_tokens
        
        response_data = service.format_buy_response(results, "ethereum")
        
        # Add Web3 enhancements
        response_data['web3_enhanced'] = is_enhanced
        if is_enhanced and results.get('web3_analysis'):
            response_data['web3_analysis'] = results['web3_analysis']
            
            # Add sophistication insights
            web3_data = results['web3_analysis']
            if web3_data.get('total_transactions_analyzed', 0) > 0:
                sophisticated_pct = (web3_data.get('sophisticated_transactions', 0) / web3_data['total_transactions_analyzed']) * 100
                response_data['sophistication_insights'] = {
                    'sophisticated_percentage': round(sophisticated_pct, 1),
                    'average_gas_efficiency': round(web3_data.get('gas_efficiency_avg', 0), 1),
                    'method_diversity': len(web3_data.get('method_distribution', {})),
                    'top_methods': list(web3_data.get('method_distribution', {}).keys())[:3]
                }
        
        cache_key = 'eth_buy'
        service.cache_data(cache_key, response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"ETH buy analysis failed: {e}", exc_info=True)
        return jsonify({
            "error": f"ETH buy analysis failed: {str(e)}",
            "web3_enhanced": False,
            "traceback": traceback.format_exc() if settings.flask.debug else None
        }), 500

@api_bp.route('/eth/sell')
def eth_sell_analysis():
    """Enhanced ETH mainnet sell analysis"""
    try:
        num_wallets, days_back, network, enhanced = get_analysis_params()
        
        logger.info(f"ETH sell analysis: {num_wallets} wallets, {days_back} days, enhanced={enhanced}")
        
        # Get appropriate tracker
        analyzer, is_enhanced = get_tracker_instance("ethereum", "sell", enhanced)
        
        if not analyzer.test_connection():
            return jsonify({"error": "Connection failed"}), 500
        
        results = analyzer.analyze_all_sell_methods(
            num_wallets=num_wallets, 
            days_back=days_back,
            max_wallets_for_sse=False
        )
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant ETH sell pressure detected",
                "total_sells": 0,
                "unique_tokens": 0,
                "total_estimated_eth": 0,
                "web3_enhanced": is_enhanced
            })
        
        # Filter excluded tokens
        if results.get('ranked_tokens'):
            filtered_tokens = []
            for token_tuple in results['ranked_tokens']:
                try:
                    # ranked_tokens is a list of tuples: (token, data, sell_score)
                    if isinstance(token_tuple, tuple) and len(token_tuple) >= 3:
                        token_symbol = token_tuple[0]  # First element is the token symbol
                        if not should_exclude_token(token_symbol):
                            filtered_tokens.append(token_tuple)
                    else:
                        # Fallback for unexpected format
                        filtered_tokens.append(token_tuple)
                except Exception as e:
                    logger.warning(f"Error processing token tuple: {e}")
                    filtered_tokens.append(token_tuple)
            results['ranked_tokens'] = filtered_tokens
        
        response_data = service.format_sell_response(results, "ethereum")
        
        # Add Web3 enhancements
        response_data['web3_enhanced'] = is_enhanced
        if is_enhanced and results.get('web3_analysis'):
            response_data['web3_analysis'] = results['web3_analysis']
            
            # Add sell pressure insights
            web3_data = results['web3_analysis']
            if web3_data.get('total_transactions_analyzed', 0) > 0:
                sophisticated_pct = (web3_data.get('sophisticated_sells', 0) / web3_data['total_transactions_analyzed']) * 100
                panic_sells = web3_data.get('panic_sells', 0)
                strategic_sells = web3_data.get('strategic_sells', 0)
                confidence_ratio = strategic_sells / (strategic_sells + panic_sells) if (strategic_sells + panic_sells) > 0 else 0
                
                response_data['sell_pressure_insights'] = {
                    'sophisticated_percentage': round(sophisticated_pct, 1),
                    'panic_sells': panic_sells,
                    'strategic_sells': strategic_sells,
                    'pressure_confidence': round(confidence_ratio, 2),
                    'average_gas_efficiency': round(web3_data.get('avg_gas_efficiency', 0), 1),
                    'top_sell_methods': list(web3_data.get('method_distribution', {}).keys())[:3]
                }
        
        cache_key = 'eth_sell'
        service.cache_data(cache_key, response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"ETH sell analysis failed: {e}", exc_info=True)
        return jsonify({
            "error": f"ETH sell analysis failed: {str(e)}",
            "web3_enhanced": False,
            "traceback": traceback.format_exc() if settings.flask.debug else None
        }), 500

@api_bp.route('/base/buy')
def base_buy_analysis():
    """Enhanced Base network buy analysis"""
    try:
        num_wallets, days_back, network, enhanced = get_analysis_params()
        network_config = settings.get_network_config('base')
        
        logger.info(f"Base buy analysis: {num_wallets} wallets, {days_back} days, enhanced={enhanced}")

        # Get appropriate tracker
        analyzer, is_enhanced = get_tracker_instance("base", "buy", enhanced)

        if not analyzer.test_connection():
            return jsonify({"error": "Base connection failed"}), 500
        
        results = analyzer.analyze_all_trading_methods(
            num_wallets=num_wallets, 
            days_back=days_back,
            max_wallets_for_sse=False
        )
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant Base buy activity found",
                "total_purchases": 0,
                "unique_tokens": 0,
                "total_eth_spent": 0,
                "web3_enhanced": is_enhanced,
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
                try:
                    # ranked_tokens is a list of tuples: (token, data, alpha_score)
                    if isinstance(token_tuple, tuple) and len(token_tuple) >= 3:
                        token_symbol = token_tuple[0]  # First element is the token symbol
                        if not should_exclude_token(token_symbol):
                            filtered_tokens.append(token_tuple)
                    else:
                        # Fallback for unexpected format
                        filtered_tokens.append(token_tuple)
                except Exception as e:
                    logger.warning(f"Error processing token tuple: {e}")
                    filtered_tokens.append(token_tuple)
            results['ranked_tokens'] = filtered_tokens
        
        response_data = service.format_buy_response(results, "base")
        
        # Add Web3 enhancements
        response_data['web3_enhanced'] = is_enhanced
        if is_enhanced and results.get('web3_analysis'):
            response_data['web3_analysis'] = results['web3_analysis']
            
            # Add sophistication insights
            web3_data = results['web3_analysis']
            if web3_data.get('total_transactions_analyzed', 0) > 0:
                sophisticated_pct = (web3_data.get('sophisticated_transactions', 0) / web3_data['total_transactions_analyzed']) * 100
                response_data['sophistication_insights'] = {
                    'sophisticated_percentage': round(sophisticated_pct, 1),
                    'average_gas_efficiency': round(web3_data.get('gas_efficiency_avg', 0), 1),
                    'method_diversity': len(web3_data.get('method_distribution', {})),
                    'top_methods': list(web3_data.get('method_distribution', {}).keys())[:3]
                }
        
        cache_key = 'base_buy'
        service.cache_data(cache_key, response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Base buy analysis failed: {e}", exc_info=True)
        return jsonify({
            "error": f"Base buy analysis failed: {str(e)}",
            "web3_enhanced": False,
            "traceback": traceback.format_exc() if settings.flask.debug else None
        }), 500

@api_bp.route('/base/sell')
def base_sell_analysis():
    """Enhanced Base network sell analysis"""
    try:
        num_wallets, days_back, network, enhanced = get_analysis_params()

        logger.info(f"Base sell analysis: {num_wallets} wallets, {days_back} days, enhanced={enhanced}")

        # Get appropriate tracker
        analyzer, is_enhanced = get_tracker_instance("base", "sell", enhanced)

        if not analyzer.test_connection():
            return jsonify({"error": "Base connection failed"}), 500
        
        results = analyzer.analyze_all_sell_methods(
            num_wallets=num_wallets, 
            days_back=days_back,
            max_wallets_for_sse=False
        )
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant Base sell pressure detected",
                "total_sells": 0,
                "unique_tokens": 0,
                "total_estimated_eth": 0,
                "web3_enhanced": is_enhanced
            })
        
        # Filter excluded tokens
        if results.get('ranked_tokens'):
            filtered_tokens = []
            for token_tuple in results['ranked_tokens']:
                try:
                    # ranked_tokens is a list of tuples: (token, data, sell_score)
                    if isinstance(token_tuple, tuple) and len(token_tuple) >= 3:
                        token_symbol = token_tuple[0]  # First element is the token symbol
                        if not should_exclude_token(token_symbol):
                            filtered_tokens.append(token_tuple)
                    else:
                        # Fallback for unexpected format
                        filtered_tokens.append(token_tuple)
                except Exception as e:
                    logger.warning(f"Error processing token tuple: {e}")
                    filtered_tokens.append(token_tuple)
            results['ranked_tokens'] = filtered_tokens
        
        response_data = service.format_sell_response(results, "base")
        
        # Add Web3 enhancements
        response_data['web3_enhanced'] = is_enhanced
        if is_enhanced and results.get('web3_analysis'):
            response_data['web3_analysis'] = results['web3_analysis']
            
            # Add sell pressure insights
            web3_data = results['web3_analysis']
            if web3_data.get('total_transactions_analyzed', 0) > 0:
                sophisticated_pct = (web3_data.get('sophisticated_sells', 0) / web3_data['total_transactions_analyzed']) * 100
                panic_sells = web3_data.get('panic_sells', 0)
                strategic_sells = web3_data.get('strategic_sells', 0)
                confidence_ratio = strategic_sells / (strategic_sells + panic_sells) if (strategic_sells + panic_sells) > 0 else 0
                
                response_data['sell_pressure_insights'] = {
                    'sophisticated_percentage': round(sophisticated_pct, 1),
                    'panic_sells': panic_sells,
                    'strategic_sells': strategic_sells,
                    'pressure_confidence': round(confidence_ratio, 2),
                    'average_gas_efficiency': round(web3_data.get('avg_gas_efficiency', 0), 1),
                    'top_sell_methods': list(web3_data.get('method_distribution', {}).keys())[:3]
                }
        
        cache_key = 'base_sell'
        service.cache_data(cache_key, response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Base sell analysis failed: {e}", exc_info=True)
        return jsonify({
            "error": f"Base sell analysis failed: {str(e)}",
            "web3_enhanced": False,
            "traceback": traceback.format_exc() if settings.flask.debug else None
        }), 500

# Enhanced status endpoint with Web3 info
@api_bp.route('/status')
def api_status():
    """Enhanced API status with Web3 information"""
    try:
        cache_status = service.get_cache_status()
        
        # Get Web3 status
        web3_status = {
            'available': WEB3_AVAILABLE,
            'manager_initialized': web3_manager is not None,
            'network_connections': {},
            'features': []
        }
        
        if WEB3_AVAILABLE and web3_manager:
            try:
                connection_results = test_all_web3_connections()
                web3_status['network_connections'] = connection_results
                web3_status['features'] = [
                    'Enhanced transaction analysis',
                    'Sophistication scoring',
                    'Gas efficiency tracking',
                    'Method detection',
                    'Sell pressure analysis'
                ]
            except Exception as e:
                web3_status['error'] = str(e)
        
        return jsonify({
            "status": "online",
            "environment": settings.environment,
            "cached_data": cache_status,
            "last_updated": service.get_last_updated(),
            "supported_networks": [net.value for net in settings.monitor.supported_networks],
            "web3_status": web3_status,
            "config": {
                "analysis": {
                    "default_wallet_count": 173,
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
                "/api/base/buy/stream", "/api/base/sell/stream",
                "/api/web3/status", "/api/web3/analyze-address/<address>",
                "/api/web3/transaction/<tx_hash>"
            ]
        })
    except Exception as e:
        logger.error(f"Error in api_status: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# Web3 specific endpoints
@api_bp.route('/web3/status')
def web3_status():
    """Get Web3 integration status"""
    try:
        # Test if Web3 is available
        try:
            from web3 import Web3
            web3_available = True
            web3_version = Web3.__version__
        except ImportError:
            web3_available = False
            web3_version = None
        
        if not web3_available:
            return jsonify({
                'status': 'unavailable',
                'web3_available': False,
                'message': 'Web3 not installed. Install with: pip install web3'
            })
        
        # Test connections
        connection_results = test_all_web3_connections()
        
        # Get current block numbers
        block_numbers = {}
        for network, connected in connection_results.items():
            if connected:
                try:
                    w3 = get_web3_for_network(network)
                    block_numbers[network] = w3.eth.block_number
                except Exception as e:
                    block_numbers[network] = f"Error: {str(e)}"
            else:
                block_numbers[network] = "Not connected"
        
        return jsonify({
            'status': 'available',
            'web3_available': True,
            'web3_version': web3_version,
            'network_connections': connection_results,
            'current_blocks': block_numbers,
            'total_networks': len(connection_results),
            'connected_networks': sum(1 for connected in connection_results.values() if connected),
            'features_enabled': {
                'enhanced_transaction_analysis': True,
                'sophistication_scoring': True,
                'gas_efficiency_tracking': True,
                'method_detection': True,
                'contract_analysis': True,
                'sell_pressure_analysis': True
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting Web3 status: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'web3_available': False,
            'error': str(e)
        }), 500

@api_bp.route('/web3/analyze-address/<address>')
def analyze_address_web3(address):
    """Analyze an address using Web3 capabilities"""
    try:
        network = request.args.get('network', 'ethereum')
        
        # Validate network
        supported_networks = [net.value for net in settings.monitor.supported_networks]
        if network not in supported_networks:
            return jsonify({
                'error': f'Network {network} not supported. Supported: {supported_networks}'
            }), 400
        
        # Check if Web3 is available
        if not WEB3_AVAILABLE:
            return jsonify({
                'error': 'Web3 not available. Enhanced address analysis requires Web3.',
                'address': address,
                'network': network
            }), 400
        
        try:
            from tracker.web3_utils import Web3EnhancedTracker
            # Analyze address
            tracker = Web3EnhancedTracker(network)
            analysis = tracker.analyze_wallet_sophistication(address)
            
            if not analysis:
                return jsonify({
                    'error': 'Failed to analyze address',
                    'address': address,
                    'network': network
                }), 500
            
            # Get additional Web3 details
            w3 = get_web3_for_network(network)
            balance_wei = w3.eth.get_balance(address)
            balance_eth = float(w3.from_wei(balance_wei, 'ether'))
            tx_count = w3.eth.get_transaction_count(address)
            
            # Check if it's a contract
            code = w3.eth.get_code(address)
            is_contract = len(code) > 0
            
            enhanced_analysis = {
                'address': address,
                'network': network,
                'web3_analysis': analysis,
                'basic_info': {
                    'balance_eth': balance_eth,
                    'balance_wei': str(balance_wei),
                    'transaction_count': tx_count,
                    'is_contract': is_contract,
                    'code_size_bytes': len(code) if is_contract else 0
                },
                'analysis_timestamp': datetime.now().isoformat(),
                'web3_enhanced': True
            }
            
            return jsonify(enhanced_analysis)
            
        except Exception as e:
            logger.error(f"Error in Web3 address analysis: {e}", exc_info=True)
            return jsonify({
                'error': f'Analysis failed: {str(e)}',
                'address': address,
                'network': network
            }), 500
        
    except Exception as e:
        logger.error(f"Error in Web3 address analysis: {e}", exc_info=True)
        return jsonify({
            'error': f'Analysis failed: {str(e)}',
            'address': address,
            'network': network
        }), 500

@api_bp.route('/web3/transaction/<tx_hash>')
def analyze_transaction_web3(tx_hash):
    """Analyze a transaction using Web3"""
    try:
        network = request.args.get('network', 'ethereum')
        
        # Check if Web3 is available
        if not WEB3_AVAILABLE:
            return jsonify({
                'error': 'Web3 not available. Enhanced transaction analysis requires Web3.',
                'transaction_hash': tx_hash,
                'network': network
            }), 400
        
        try:
            from tracker.web3_utils import EnhancedTransactionAnalyzer, Web3Manager
            
            # Analyze transaction
            web3_manager = Web3Manager()
            analyzer = EnhancedTransactionAnalyzer(network, web3_manager)
            
            analysis = analyzer.get_transaction_details(tx_hash)
            
            if not analysis:
                return jsonify({
                    'error': 'Transaction not found or analysis failed',
                    'transaction_hash': tx_hash,
                    'network': network
                }), 404
            
            return jsonify({
                'transaction_hash': tx_hash,
                'network': network,
                'analysis': analysis,
                'analysis_timestamp': datetime.now().isoformat(),
                'web3_enhanced': True
            })
            
        except Exception as e:
            logger.error(f"Error in Web3 transaction analysis: {e}", exc_info=True)
            return jsonify({
                'error': f'Transaction analysis failed: {str(e)}',
                'transaction_hash': tx_hash,
                'network': network
            }), 500
        
    except Exception as e:
        logger.error(f"Error in Web3 transaction analysis: {e}", exc_info=True)
        return jsonify({
            'error': f'Transaction analysis failed: {str(e)}',
            'transaction_hash': tx_hash,
            'network': network
        }), 500

# All your existing monitor endpoints remain exactly the same
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
                    'num_wallets': 173,
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
                    'num_wallets': 173,
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
    try:
        logger.info("Monitor test endpoint called")
        
        test_results = {
            'monitor_available': monitor is not None,
            'monitor_module': False,
            'base_tracker': False,
            'eth_tracker': False,
            'settings_loaded': True,
            'alchemy_config': bool(alchemy_config.api_key),
            'web3_available': WEB3_AVAILABLE
        }
        
        # Test monitor module
        if monitor:
            test_results['monitor_module'] = hasattr(monitor, 'get_status')
        
        # Test base tracker (using enhanced if available)
        try:
            tracker, is_enhanced = get_tracker_instance("base", "buy")
            test_results['base_tracker'] = hasattr(tracker, 'test_connection')
            test_results['base_tracker_enhanced'] = is_enhanced
        except Exception as e:
            logger.warning(f"Base tracker test failed: {e}")
        
        # Test eth tracker (using enhanced if available)
        try:
            tracker, is_enhanced = get_tracker_instance("ethereum", "buy")
            test_results['eth_tracker'] = hasattr(tracker, 'test_connection')
            test_results['eth_tracker_enhanced'] = is_enhanced
        except Exception as e:
            logger.warning(f"ETH tracker test failed: {e}")
        
        return jsonify({
            'status': 'success',
            'message': 'Monitor test completed',
            'results': test_results,
            'settings_info': {
                'environment': settings.environment,
                'supported_networks': [net.value for net in settings.monitor.supported_networks],
                'default_wallet_count': 173,
                'excluded_tokens_count': len(analysis_config.excluded_tokens),
                'web3_features_enabled': WEB3_AVAILABLE
            }
        })
        
    except Exception as e:
        logger.error(f"Monitor test failed: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Monitor test failed: {str(e)}',
            'results': test_results if 'test_results' in locals() else {}
        }), 500

# All your existing config and utility endpoints remain the same
@api_bp.route('/config', methods=['GET'])
def get_api_config():
    """Get current API configuration (safe, non-sensitive data only)"""
    try:
        return jsonify({
            'status': 'success',
            'config': {
                'environment': settings.environment,
                'web3_available': WEB3_AVAILABLE,
                'analysis': {
                    'default_wallet_count': 173,
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
            if not data:
                return jsonify({
                    'status': 'error',
                    'message': 'No JSON data provided'
                }), 400
                
            action = data.get('action')  # 'add', 'remove', 'replace'
            tokens = data.get('tokens', [])
            
            if not action:
                return jsonify({
                    'status': 'error',
                    'message': 'Action is required'
                }), 400
            
            if action == 'add':
                for token in tokens:
                    if token and token.upper() not in [t.upper() for t in analysis_config.excluded_tokens]:
                        analysis_config.excluded_tokens.append(token.upper())
                        
            elif action == 'remove':
                analysis_config.excluded_tokens = [
                    t for t in analysis_config.excluded_tokens 
                    if t.upper() not in [token.upper() for token in tokens if token]
                ]
                
            elif action == 'replace':
                analysis_config.excluded_tokens = [token.upper() for token in tokens if token]
                
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
                    'alchemy_url_configured': bool(network_config.get('alchemy_url')),
                    'web3_enhanced': WEB3_AVAILABLE
                }
            except Exception as e:
                networks_info[network.value] = {
                    'supported': False,
                    'error': str(e)
                }
        
        return jsonify({
            'status': 'success',
            'networks': networks_info,
            'default_networks': [net.value for net in monitor_config.default_networks],
            'web3_available': WEB3_AVAILABLE
        })
        
    except Exception as e:
        logger.error(f"Error getting networks info: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Failed to get networks info: {str(e)}'
        }), 500
        
@api_bp.route('/token/<contract_address>')
def token_details(contract_address):
    """Enhanced token details with Web3 capabilities"""
    try:
        from datetime import datetime
        
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
        
        # Use enhanced tracker if available
        tracker, is_enhanced = get_tracker_instance(network, "buy")
        
        is_base_native_token = (
            NetworkSpecificMixins.BaseMixin.is_base_native_token 
            if network == 'base' 
            else lambda x: False
        )
        
        # Get token metadata using tracker's connection
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
        
        # Enhanced contract analysis if Web3 is available
        web3_analysis = {}
        if WEB3_AVAILABLE and is_enhanced:
            try:
                from tracker.web3_utils import Web3EnhancedTracker
                web3_tracker = Web3EnhancedTracker(network)
                web3_analysis = web3_tracker.tx_analyzer.analyze_address_activity(contract_address)
            except Exception as e:
                logger.debug(f"Web3 contract analysis failed: {e}")
        
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
        
        response = {
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
            'web3_enhanced': is_enhanced,
            'last_updated': datetime.now().isoformat()
        }
        
        # Add Web3 analysis if available
        if web3_analysis:
            response['web3_analysis'] = web3_analysis
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in token_details: {e}", exc_info=True)
        return jsonify({
            'error': f'Failed to get token details: {str(e)}',
            'contract_address': contract_address,
            'network': network,
            'traceback': traceback.format_exc() if settings.flask.debug else None
        }), 500

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
                'monitor_available': monitor is not None,
                'web3_available': WEB3_AVAILABLE
            }
        }
        
        # Check if any critical components are failing
        warnings = []
        if not alchemy_config.api_key:
            warnings.append('Alchemy API key not configured')
        if not WEB3_AVAILABLE:
            warnings.append('Web3 not available - enhanced features disabled')
        
        if warnings:
            health_status['status'] = 'degraded'
            health_status['warnings'] = warnings
        
        return jsonify(health_status)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@api_bp.route('/test/sse')
def test_sse():
    """Enhanced SSE test with Web3 indicators"""
    def test_generator():
        import time
        
        messages = [
            {'type': 'console', 'message': '🚀 Enhanced SSE Test started', 'level': 'info'},
            {'type': 'console', 'message': f'⚡ Web3 Available: {"✅" if WEB3_AVAILABLE else "❌"}', 'level': 'highlight'},
            {'type': 'console', 'message': '📊 Message 1/5', 'level': 'info'},
            {'type': 'progress', 'percentage': 20},
            {'type': 'console', 'message': '📊 Message 2/5', 'level': 'success'},
            {'type': 'progress', 'percentage': 40},
            {'type': 'console', 'message': '🧠 Web3 Enhanced Message 3/5', 'level': 'highlight'},
            {'type': 'progress', 'percentage': 60},
            {'type': 'console', 'message': '📊 Message 4/5', 'level': 'warning'},
            {'type': 'progress', 'percentage': 80},
            {'type': 'console', 'message': '✅ Message 5/5 - Enhanced test complete!', 'level': 'success'},
            {'type': 'progress', 'percentage': 100},
            {'type': 'complete', 'status': 'success', 'web3_enhanced': WEB3_AVAILABLE},
            {'type': 'final_complete'}
        ]
        
        for i, message in enumerate(messages):
            try:
                yield f"data: {json.dumps(message)}\n\n"
                time.sleep(0.5)  # 500ms delay
            except Exception as e:
                logger.error(f"Error in test_sse generator: {e}")
                break
    
    return Response(
        test_generator(),
        mimetype="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )

@api_bp.route('/debug/analysis/<network>/<analysis_type>')
def debug_analysis(network, analysis_type):
    """Enhanced debug endpoint with Web3 awareness"""
    try:
        debug_info = []
        
        debug_info.append("🔍 Enhanced Debug Analysis Started")
        debug_info.append(f"Network: {network}, Type: {analysis_type}")
        debug_info.append(f"Web3 Available: {'✅' if WEB3_AVAILABLE else '❌'}")
        
        # Step 1: Create analyzer (enhanced if available)
        debug_info.append("📋 Step 1: Creating enhanced analyzer...")
        
        try:
            analyzer, is_enhanced = get_tracker_instance(network, analysis_type)
            debug_info.append(f"✅ {'Enhanced' if is_enhanced else 'Standard'} analyzer created successfully")
        except Exception as e:
            debug_info.append(f"❌ Analyzer creation failed: {e}")
            return jsonify({"debug_info": debug_info})
        
        # Step 2: Test connection
        debug_info.append("📋 Step 2: Testing connection...")
        if analyzer.test_connection():
            debug_info.append("✅ Connection test passed")
        else:
            debug_info.append("❌ Connection test failed")
            return jsonify({"debug_info": debug_info})
        
        # Step 3: Get wallets
        debug_info.append("📋 Step 3: Getting top 5 wallets...")
        try:
            top_wallets = analyzer.get_top_wallets(5)
            debug_info.append(f"✅ Retrieved {len(top_wallets)} wallets")
            
            if top_wallets:
                debug_info.append(f"First wallet: {top_wallets[0].get('address', 'No address')[:10]}...")
                
                # Web3 specific wallet info
                if is_enhanced and top_wallets[0].get('web3_analysis'):
                    sophistication = top_wallets[0]['web3_analysis'].get('sophistication_score', 0)
                    debug_info.append(f"🧠 Wallet sophistication: {sophistication}")
            
        except Exception as e:
            debug_info.append(f"❌ Wallet retrieval failed: {e}")
            return jsonify({"debug_info": debug_info})
        
        # Step 4: Test single wallet analysis
        if top_wallets:
            debug_info.append("📋 Step 4: Testing single wallet analysis...")
            try:
                wallet_address = top_wallets[0]['address']
                debug_info.append(f"Testing wallet: {wallet_address[:10]}...")
                
                # Test with very short timeframe
                if analysis_type == 'buy':
                    purchases = analyzer.analyze_wallet_purchases(wallet_address, 0.1)  # 2.4 hours
                    debug_info.append(f"✅ Found {len(purchases)} purchases")
                    
                    # Web3 enhanced purchase info
                    if is_enhanced and purchases:
                        enhanced_count = len([p for p in purchases if p.get('web3_analysis')])
                        debug_info.append(f"🧠 Enhanced purchases: {enhanced_count}")
                else:
                    sells = analyzer.analyze_wallet_sells(wallet_address, 0.1)  # 2.4 hours
                    debug_info.append(f"✅ Found {len(sells)} sells")
                    
                    # Web3 enhanced sell info
                    if is_enhanced and sells:
                        enhanced_count = len([s for s in sells if s.get('web3_analysis')])
                        debug_info.append(f"🧠 Enhanced sells: {enhanced_count}")
                
            except Exception as e:
                debug_info.append(f"❌ Single wallet analysis failed: {e}")
                import traceback
                debug_info.append(f"Traceback: {traceback.format_exc()}")
        
        debug_info.append("🎉 Enhanced debug analysis completed successfully!")
        
        return jsonify({
            "status": "success",
            "debug_info": debug_info,
            "total_wallets": len(top_wallets) if 'top_wallets' in locals() else 0,
            "web3_enhanced": is_enhanced if 'is_enhanced' in locals() else False
        })
        
    except Exception as e:
        return jsonify({
            "status": "error", 
            "error": str(e),
            "debug_info": debug_info if 'debug_info' in locals() else [],
            "web3_available": WEB3_AVAILABLE
        })

@api_bp.route('/debug/console')
def debug_console():
    """Test console output capture with Web3 indicators"""
    def test_generator():
        # Test various types of output
        yield f"data: {json.dumps({'type': 'console', 'message': '🚀 Testing enhanced console capture...', 'level': 'info'})}\n\n"
        
        # Test print statements
        try:
            print("📊 This is a print statement test")
            logger.info("📋 This is a logger info test")
            logger.warning("⚠️ This is a logger warning test")
            logger.error("❌ This is a logger error test")
            
            # Test with Web3 and emojis
            print("✅ Print with success emoji")
            print("🔍 Analysis progress: 50%")
            print("💰 ETH spent: 1.2345")
            if WEB3_AVAILABLE:
                print("🧠 Web3 sophistication scoring enabled")
                print("⚡ Enhanced transaction analysis active")
        except Exception as e:
            logger.error(f"Error in console test: {e}")
        
        yield f"data: {json.dumps({'type': 'console', 'message': '🎉 Enhanced console test complete!', 'level': 'success'})}\n\n"
        yield f"data: {json.dumps({'type': 'complete', 'status': 'success', 'web3_enhanced': WEB3_AVAILABLE})}\n\n"
    
    return Response(
        test_generator(),
        mimetype="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )

# Error handlers remain the same
@api_bp.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found',
        'error': '404 Not Found'
    }), 404

@api_bp.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors"""
    return jsonify({
        'status': 'error',
        'message': 'Method not allowed',
        'error': '405 Method Not Allowed'
    }), 405

@api_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}", exc_info=True)
    return jsonify({
        'status': 'error',
        'message': 'Internal server error',
        'error': '500 Internal Server Error'
    }), 500

@api_bp.errorhandler(Exception)
def handle_exception(error):
    """Handle all other exceptions"""
    logger.error(f"Unhandled exception: {error}", exc_info=True)
    return jsonify({
        'status': 'error',
        'message': 'An unexpected error occurred',
        'error': str(error)
    }), 500