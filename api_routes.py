from flask import Blueprint, jsonify, Response, request
import traceback
from datetime import datetime
from data_service import AnalysisService
import time
from queue import Queue, Empty
import threading
import sys
from io import StringIO
import logging

# Import settings
from config.settings import settings, analysis_config, monitor_config, alchemy_config
from auto_monitor import monitor

# Enhanced imports with orjson support
try:
    from utils.json_utils import orjson_dumps_str, orjson_loads, sanitize_for_orjson, benchmark_json_performance
    from utils.performance import monitor_json_performance
    ORJSON_AVAILABLE = True
    print("✅ orjson integration enabled")
except ImportError as e:
    print(f"⚠️  orjson not available: {e}")
    ORJSON_AVAILABLE = False
    # Fallback functions
    import json
    def orjson_dumps_str(obj, **kwargs):
        return json.dumps(obj, default=str)
    def orjson_loads(data):
        return json.loads(data)
    def sanitize_for_orjson(obj):
        return sanitize_for_json(obj)
    def benchmark_json_performance(data, iterations=100):
        return {"serialize_speedup": 1.0, "roundtrip_speedup": 1.0}
    def monitor_json_performance(func):
        return func

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
    """Enhanced sanitization using orjson utilities with fallback"""
    if ORJSON_AVAILABLE:
        return sanitize_for_orjson(obj)
    else:
        # Original fallback implementation
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
    """Enhanced console capture that actually works with orjson support"""
    
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
        """Send text to SSE with proper formatting and orjson support"""
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
            
            # Sanitize for orjson
            if ORJSON_AVAILABLE:
                message = sanitize_for_orjson(message)
            
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
    """Enhanced SSE stream generator with Web3 support and orjson optimization"""
    analysis_key = f"{network}_{analysis_type}"

    # Check if analysis is already running
    global analysis_in_progress
    if analysis_in_progress.get(analysis_key, False):
        def already_running_generator():
            message = {'type': 'console', 'message': 'Analysis already in progress, please wait...', 'level': 'warning'}
            if ORJSON_AVAILABLE:
                yield f"data: {orjson_dumps_str(message)}\n\n"
            else:
                import json
                yield f"data: {json.dumps(message)}\n\n"
            
            complete_message = {'type': 'complete', 'status': 'already_running'}
            if ORJSON_AVAILABLE:
                yield f"data: {orjson_dumps_str(complete_message)}\n\n"
            else:
                yield f"data: {json.dumps(complete_message)}\n\n"
        return already_running_generator()
    
    # Mark analysis as in progress
    analysis_in_progress[analysis_key] = True
    
    def run_analysis():
        """Run the enhanced analysis in a separate thread with orjson support"""
        console_capture = None
        try:
            # Determine if we should use enhanced analysis
            enhanced_analysis = params.get('enhanced', WEB3_AVAILABLE) if params else WEB3_AVAILABLE
            
            # Send immediate feedback with Web3 status
            start_message = {
                'type': 'console',
                'level': 'success' if enhanced_analysis and WEB3_AVAILABLE else 'info'
            }
            
            if enhanced_analysis and WEB3_AVAILABLE:
                start_message['message'] = f'🚀⚡ Enhanced Web3 analysis started for {network} {analysis_type}'
            else:
                start_message['message'] = f'🔄📡 Standard analysis started for {network} {analysis_type}'
            
            if ORJSON_AVAILABLE:
                start_message = sanitize_for_orjson(start_message)
            
            message_queue.put(start_message)
            
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
            
            config_message = {
                'type': 'console',
                'message': f'⚙️ Configuration: {num_wallets} wallets, {days_back} days | Web3: {"✅" if enhanced_analysis else "❌"} | orjson: {"✅" if ORJSON_AVAILABLE else "❌"}',
                'level': 'info'
            }
            
            if ORJSON_AVAILABLE:
                config_message = sanitize_for_orjson(config_message)
            
            message_queue.put(config_message)
            
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
            
            tracker_message = {
                'type': 'console',
                'level': 'highlight' if is_enhanced else 'info'
            }
            
            if is_enhanced:
                tracker_message['message'] = f'🧠 Using Web3-Enhanced {analysis_type.title()} Tracker'
            else:
                tracker_message['message'] = f'📡 Using Standard {analysis_type.title()} Tracker'
            
            if ORJSON_AVAILABLE:
                tracker_message = sanitize_for_orjson(tracker_message)
            
            message_queue.put(tracker_message)
            
            # Run the analysis
            start_time = time.time()
            
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
            
            analysis_time = time.time() - start_time
            
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
                # Benchmark orjson performance for large datasets
                if ORJSON_AVAILABLE and len(str(results)) > 50000:
                    perf_metrics = benchmark_json_performance(results, iterations=10)
                    perf_message = {
                        'type': 'console',
                        'message': f'📊 JSON Performance: orjson {perf_metrics["serialize_speedup"]:.1f}x faster',
                        'level': 'highlight'
                    }
                    message_queue.put(sanitize_for_orjson(perf_message))
                
                results = sanitize_for_json(results)
                
                # Format the results for the API response
                if analysis_type == 'buy':
                    response_data = service.format_buy_response(results, network)
                else:
                    response_data = service.format_sell_response(results, network)
                
                # Add Web3 enhancement status
                response_data['web3_enhanced'] = is_enhanced
                response_data['orjson_enabled'] = ORJSON_AVAILABLE
                response_data['analysis_time_seconds'] = round(analysis_time, 2)
                
                if is_enhanced and results.get('web3_analysis'):
                    response_data['web3_analysis'] = results['web3_analysis']
                
                # Cache the results with enhanced flag
                cache_key_mapping = {
                    'eth': 'ethereum',
                    'base': 'base'
                }
                actual_network = cache_key_mapping.get(network, network)
                cache_key = f'{actual_network}_{analysis_type}'
                service.cache_data(cache_key, response_data)
                
                # Send the formatted results through SSE
                results_message = {
                    'type': 'results',
                    'data': response_data
                }
                
                if ORJSON_AVAILABLE:
                    results_message = sanitize_for_orjson(results_message)
                
                message_queue.put(results_message)
                
                # Send Web3 insights if available
                if is_enhanced and results.get('web3_analysis'):
                    web3_data = results['web3_analysis']
                    if analysis_type == 'buy':
                        if web3_data.get('total_transactions_analyzed', 0) > 0:
                            sophisticated_pct = (web3_data.get('sophisticated_transactions', 0) / web3_data['total_transactions_analyzed']) * 100
                            insight_message = {
                                'type': 'console',
                                'message': f'🧠 Web3 Insights: {sophisticated_pct:.1f}% sophisticated trades, {web3_data.get("gas_efficiency_avg", 0):.1f}% avg gas efficiency',
                                'level': 'highlight'
                            }
                            if ORJSON_AVAILABLE:
                                insight_message = sanitize_for_orjson(insight_message)
                            message_queue.put(insight_message)
                    else:  # sell
                        if web3_data.get('total_transactions_analyzed', 0) > 0:
                            sophisticated_pct = (web3_data.get('sophisticated_sells', 0) / web3_data['total_transactions_analyzed']) * 100
                            panic_sells = web3_data.get('panic_sells', 0)
                            strategic_sells = web3_data.get('strategic_sells', 0)
                            insight_message = {
                                'type': 'console',
                                'message': f'🧠 Sell Insights: {sophisticated_pct:.1f}% sophisticated, {panic_sells} panic, {strategic_sells} strategic',
                                'level': 'highlight'
                            }
                            if ORJSON_AVAILABLE:
                                insight_message = sanitize_for_orjson(insight_message)
                            message_queue.put(insight_message)
            
            # Send completion message with Web3 status
            completion_message = {
                'type': 'complete', 
                'status': 'success',
                'has_results': bool(results and results.get('ranked_tokens')),
                'web3_enhanced': is_enhanced,
                'orjson_enabled': ORJSON_AVAILABLE,
                'analysis_time_seconds': round(analysis_time, 2),
                'config_used': {
                    'num_wallets': num_wallets,
                    'days_back': days_back,
                    'min_eth_value': min_eth_value,
                    'excluded_tokens_count': len(analysis_config.excluded_tokens),
                    'enhanced_analysis': is_enhanced
                }
            }
            
            if ORJSON_AVAILABLE:
                completion_message = sanitize_for_orjson(completion_message)
            
            message_queue.put(completion_message)
            
        except Exception as e:
            logger.error(f"Analysis error: {e}", exc_info=True)
            # Send detailed error info via SSE
            error_message = {
                'type': 'console',
                'message': f'❌ Detailed error: {str(e)}',
                'level': 'error'
            }
            
            if ORJSON_AVAILABLE:
                error_message = sanitize_for_orjson(error_message)
            
            message_queue.put(error_message)
            
            # Send traceback lines
            try:
                tb_lines = traceback.format_exc().split('\n')[-5:]  # Last 5 lines
                for line in tb_lines:
                    if line.strip():
                        tb_message = {
                            'type': 'console',
                            'message': f'🔍 {line.strip()}',
                            'level': 'error'
                        }
                        if ORJSON_AVAILABLE:
                            tb_message = sanitize_for_orjson(tb_message)
                        message_queue.put(tb_message)
            except Exception:
                pass
            
            error_console_message = {
                'type': 'console',
                'message': f'Error: {str(e)}',
                'level': 'error'
            }
            
            complete_error_message = {
                'type': 'complete', 
                'status': 'error', 
                'error': str(e)
            }
            
            if ORJSON_AVAILABLE:
                error_console_message = sanitize_for_orjson(error_console_message)
                complete_error_message = sanitize_for_orjson(complete_error_message)
            
            message_queue.put(error_console_message)
            message_queue.put(complete_error_message)
        
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
        """Generate SSE messages with Web3 awareness and orjson optimization"""
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
                    progress_message = {'type': 'progress', 'percentage': progress}
                    if ORJSON_AVAILABLE:
                        yield f"data: {orjson_dumps_str(progress_message)}\n\n"
                    else:
                        import json
                        yield f"data: {json.dumps(progress_message)}\n\n"
                
                # Send message with orjson optimization
                try:
                    if ORJSON_AVAILABLE:
                        yield f"data: {orjson_dumps_str(message)}\n\n"
                    else:
                        import json
                        yield f"data: {json.dumps(message, default=str)}\n\n"
                except Exception as e:
                    # If serialization fails, send error message
                    error_msg = {'type': 'console', 'message': f'Serialization error: {str(e)}', 'level': 'error'}
                    if ORJSON_AVAILABLE:
                        yield f"data: {orjson_dumps_str(error_msg)}\n\n"
                    else:
                        import json
                        yield f"data: {json.dumps(error_msg)}\n\n"
                
                # Check if complete
                if message.get('type') == 'complete':
                    completion_sent = True
                    # Send final complete message to ensure client closes
                    final_message = {'type': 'final_complete'}
                    if ORJSON_AVAILABLE:
                        yield f"data: {orjson_dumps_str(final_message)}\n\n"
                    else:
                        import json
                        yield f"data: {json.dumps(final_message)}\n\n"
                    break
                    
            except Empty:
                # No message in queue
                timeout_counter += 1
                # Send keepalive every 5 seconds
                if timeout_counter % 50 == 0:
                    yield f": keepalive\n\n"
        
        # If we hit timeout, send completion
        if not completion_sent:
            timeout_message = {'type': 'complete', 'status': 'timeout'}
            final_message = {'type': 'final_complete'}
            
            if ORJSON_AVAILABLE:
                yield f"data: {orjson_dumps_str(timeout_message)}\n\n"
                yield f"data: {orjson_dumps_str(final_message)}\n\n"
            else:
                import json
                yield f"data: {json.dumps(timeout_message)}\n\n"
                yield f"data: {json.dumps(final_message)}\n\n"
            
            analysis_in_progress[analysis_key] = False
    
    return generate()

# SSE endpoints with enhanced Web3 support and orjson optimization
@api_bp.route('/eth/buy/stream')
def eth_buy_stream():
    """Enhanced SSE endpoint for ETH buy analysis with orjson optimization"""
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
    """Enhanced SSE endpoint for ETH sell analysis with orjson optimization"""
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
    """Enhanced SSE endpoint for Base buy analysis with orjson optimization"""
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
    """Enhanced SSE endpoint for Base sell analysis with orjson optimization"""
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

# Enhanced regular analysis endpoints with orjson performance monitoring
@api_bp.route('/eth/buy')
@monitor_json_performance
def eth_buy_analysis():
    """Enhanced ETH mainnet buy analysis with orjson optimization"""
    try:
        num_wallets, days_back, network, enhanced = get_analysis_params()
        network_config = settings.get_network_config('ethereum')
        
        logger.info(f"ETH buy analysis: {num_wallets} wallets, {days_back} days, enhanced={enhanced}, orjson={ORJSON_AVAILABLE}")
        
        # Get appropriate tracker
        analyzer, is_enhanced = get_tracker_instance("ethereum", "buy", enhanced)
        
        if not analyzer.test_connection():
            logger.error("ETH connection test failed")
            return jsonify({"error": "Connection failed"}), 500
        
        start_time = time.time()
        results = analyzer.analyze_all_trading_methods(
            num_wallets=num_wallets, 
            days_back=days_back,
            max_wallets_for_sse=False
        )
        analysis_time = time.time() - start_time
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant ETH buy activity found",
                "total_purchases": 0,
                "unique_tokens": 0,
                "total_eth_spent": 0,
                "web3_enhanced": is_enhanced,
                "orjson_enabled": ORJSON_AVAILABLE,
                "analysis_time_seconds": round(analysis_time, 2),
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
        
        # Benchmark orjson performance for large datasets
        if ORJSON_AVAILABLE and len(str(results)) > 50000:
            perf_metrics = benchmark_json_performance(results, iterations=10)
            logger.info(f"ETH buy JSON performance: orjson {perf_metrics['serialize_speedup']:.1f}x faster")
        
        response_data = service.format_buy_response(results, "ethereum")
        
        # Add Web3 and orjson enhancements
        response_data['web3_enhanced'] = is_enhanced
        response_data['orjson_enabled'] = ORJSON_AVAILABLE
        response_data['analysis_time_seconds'] = round(analysis_time, 2)
        
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
        
        cache_key = 'ethereum_buy'
        service.cache_data(cache_key, response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"ETH buy analysis failed: {e}", exc_info=True)
        return jsonify({
            "error": f"ETH buy analysis failed: {str(e)}",
            "web3_enhanced": False,
            "orjson_enabled": ORJSON_AVAILABLE,
            "traceback": traceback.format_exc() if settings.flask.debug else None
        }), 500

@api_bp.route('/eth/sell')
@monitor_json_performance
def eth_sell_analysis():
    """Enhanced ETH mainnet sell analysis with orjson optimization"""
    try:
        num_wallets, days_back, network, enhanced = get_analysis_params()
        
        logger.info(f"ETH sell analysis: {num_wallets} wallets, {days_back} days, enhanced={enhanced}, orjson={ORJSON_AVAILABLE}")
        
        # Get appropriate tracker
        analyzer, is_enhanced = get_tracker_instance("ethereum", "sell", enhanced)
        
        if not analyzer.test_connection():
            return jsonify({"error": "Connection failed"}), 500
        
        start_time = time.time()
        results = analyzer.analyze_all_sell_methods(
            num_wallets=num_wallets, 
            days_back=days_back,
            max_wallets_for_sse=False
        )
        analysis_time = time.time() - start_time
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant ETH sell pressure detected",
                "total_sells": 0,
                "unique_tokens": 0,
                "total_estimated_eth": 0,
                "web3_enhanced": is_enhanced,
                "orjson_enabled": ORJSON_AVAILABLE,
                "analysis_time_seconds": round(analysis_time, 2)
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
        
        # Benchmark orjson performance
        if ORJSON_AVAILABLE and len(str(results)) > 50000:
            perf_metrics = benchmark_json_performance(results, iterations=10)
            logger.info(f"ETH sell JSON performance: orjson {perf_metrics['serialize_speedup']:.1f}x faster")
        
        response_data = service.format_sell_response(results, "ethereum")
        
        # Add Web3 and orjson enhancements
        response_data['web3_enhanced'] = is_enhanced
        response_data['orjson_enabled'] = ORJSON_AVAILABLE
        response_data['analysis_time_seconds'] = round(analysis_time, 2)
        
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
        
        cache_key = 'ethereum_sell'
        service.cache_data(cache_key, response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"ETH sell analysis failed: {e}", exc_info=True)
        return jsonify({
            "error": f"ETH sell analysis failed: {str(e)}",
            "web3_enhanced": False,
            "orjson_enabled": ORJSON_AVAILABLE,
            "traceback": traceback.format_exc() if settings.flask.debug else None
        }), 500

@api_bp.route('/base/buy')
@monitor_json_performance
def base_buy_analysis():
    """Enhanced Base network buy analysis with orjson optimization"""
    try:
        num_wallets, days_back, network, enhanced = get_analysis_params()
        network_config = settings.get_network_config('base')
        
        logger.info(f"Base buy analysis: {num_wallets} wallets, {days_back} days, enhanced={enhanced}, orjson={ORJSON_AVAILABLE}")

        # Get appropriate tracker
        analyzer, is_enhanced = get_tracker_instance("base", "buy", enhanced)

        if not analyzer.test_connection():
            return jsonify({"error": "Base connection failed"}), 500
        
        start_time = time.time()
        results = analyzer.analyze_all_trading_methods(
            num_wallets=num_wallets, 
            days_back=days_back,
            max_wallets_for_sse=False
        )
        analysis_time = time.time() - start_time
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant Base buy activity found",
                "total_purchases": 0,
                "unique_tokens": 0,
                "total_eth_spent": 0,
                "web3_enhanced": is_enhanced,
                "orjson_enabled": ORJSON_AVAILABLE,
                "analysis_time_seconds": round(analysis_time, 2),
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
        
        # Benchmark orjson performance
        if ORJSON_AVAILABLE and len(str(results)) > 50000:
            perf_metrics = benchmark_json_performance(results, iterations=10)
            logger.info(f"Base buy JSON performance: orjson {perf_metrics['serialize_speedup']:.1f}x faster")
        
        response_data = service.format_buy_response(results, "base")
        
        # Add Web3 and orjson enhancements
        response_data['web3_enhanced'] = is_enhanced
        response_data['orjson_enabled'] = ORJSON_AVAILABLE
        response_data['analysis_time_seconds'] = round(analysis_time, 2)
        
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
            "orjson_enabled": ORJSON_AVAILABLE,
            "traceback": traceback.format_exc() if settings.flask.debug else None
        }), 500

@api_bp.route('/base/sell')
@monitor_json_performance
def base_sell_analysis():
    """Enhanced Base network sell analysis with orjson optimization"""
    try:
        num_wallets, days_back, network, enhanced = get_analysis_params()

        logger.info(f"Base sell analysis: {num_wallets} wallets, {days_back} days, enhanced={enhanced}, orjson={ORJSON_AVAILABLE}")

        # Get appropriate tracker
        analyzer, is_enhanced = get_tracker_instance("base", "sell", enhanced)

        if not analyzer.test_connection():
            return jsonify({"error": "Base connection failed"}), 500
        
        start_time = time.time()
        results = analyzer.analyze_all_sell_methods(
            num_wallets=num_wallets, 
            days_back=days_back,
            max_wallets_for_sse=False
        )
        analysis_time = time.time() - start_time
        
        if not results or not results.get("ranked_tokens"):
            return jsonify({
                "status": "no_data",
                "message": "No significant Base sell pressure detected",
                "total_sells": 0,
                "unique_tokens": 0,
                "total_estimated_eth": 0,
                "web3_enhanced": is_enhanced,
                "orjson_enabled": ORJSON_AVAILABLE,
                "analysis_time_seconds": round(analysis_time, 2)
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
        
        # Benchmark orjson performance
        if ORJSON_AVAILABLE and len(str(results)) > 50000:
            perf_metrics = benchmark_json_performance(results, iterations=10)
            logger.info(f"Base sell JSON performance: orjson {perf_metrics['serialize_speedup']:.1f}x faster")
        
        response_data = service.format_sell_response(results, "base")
        
        # Add Web3 and orjson enhancements
        response_data['web3_enhanced'] = is_enhanced
        response_data['orjson_enabled'] = ORJSON_AVAILABLE
        response_data['analysis_time_seconds'] = round(analysis_time, 2)
        
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
            "orjson_enabled": ORJSON_AVAILABLE,
            "traceback": traceback.format_exc() if settings.flask.debug else None
        }), 500

# Enhanced status endpoint with Web3 and orjson info
@api_bp.route('/status')
def api_status():
    """Enhanced API status with Web3 and orjson information"""
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
        
        # Get orjson status
        orjson_status = {
            'available': ORJSON_AVAILABLE,
            'performance_benefits': [
                '2-5x faster JSON serialization',
                'Reduced memory usage',
                'Optimized SSE streaming',
                'Enhanced cache operations'
            ] if ORJSON_AVAILABLE else []
        }
        
        # Test orjson performance with sample data
        if ORJSON_AVAILABLE:
            try:
                sample_data = {
                    'test': True,
                    'tokens': [{'name': f'TOKEN_{i}', 'score': i * 10} for i in range(50)],
                    'timestamp': datetime.now().isoformat()
                }
                perf_metrics = benchmark_json_performance(sample_data, iterations=100)
                orjson_status['performance_metrics'] = {
                    'serialize_speedup': round(perf_metrics['serialize_speedup'], 1),
                    'roundtrip_speedup': round(perf_metrics['roundtrip_speedup'], 1)
                }
            except Exception as e:
                orjson_status['benchmark_error'] = str(e)
        
        return jsonify({
            "status": "online",
            "environment": settings.environment,
            "cached_data": cache_status,
            "last_updated": service.get_last_updated(),
            "supported_networks": [net.value for net in settings.monitor.supported_networks],
            "web3_status": web3_status,
            "orjson_status": orjson_status,
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
                "/api/web3/transaction/<tx_hash>", "/api/orjson/benchmark"
            ]
        })
    except Exception as e:
        logger.error(f"Error in api_status: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# orjson specific endpoints
@api_bp.route('/orjson/benchmark')
def orjson_benchmark():
    """Benchmark orjson performance with crypto data"""
    try:
        if not ORJSON_AVAILABLE:
            return jsonify({
                'error': 'orjson not available',
                'message': 'Install orjson with: pip install orjson'
            }), 400
        
        # Create realistic crypto data for benchmarking
        sample_data = {
            "status": "success",
            "network": "benchmark",
            "analysis_type": "buy",
            "total_purchases": 1000,
            "unique_tokens": 100,
            "total_eth_spent": 500.123456789,
            "top_tokens": [
                {
                    "rank": i,
                    "token": f"TOKEN_{i}",
                    "alpha_score": 100.0 - (i * 0.5),
                    "wallet_count": 50 - i,
                    "total_eth_spent": 20.0 - (i * 0.1),
                    "platforms": ["Uniswap", "Aerodrome", "BaseSwap"],
                    "contract_address": f"0x{'1234567890abcdef' * 2}{i:08x}",
                    "web3_analysis": {
                        "gas_efficiency": 85.5 + (i % 15),
                        "method_used": "swapExactTokensForETH",
                        "sophistication_score": 75.0 + (i % 25)
                    }
                }
                for i in range(100)  # 100 tokens
            ],
            "timestamp": datetime.now().isoformat()
        }
        
        # Get performance metrics
        iterations = request.args.get('iterations', 1000, type=int)
        iterations = min(iterations, 5000)  # Cap at 5000 for safety
        
        perf_metrics = benchmark_json_performance(sample_data, iterations=iterations)
        
        return jsonify({
            'benchmark_results': perf_metrics,
            'test_data_size': len(str(sample_data)),
            'iterations': iterations,
            'orjson_available': True,
            'conclusions': {
                'serialization_improvement': f"{perf_metrics['serialize_speedup']:.1f}x faster",
                'roundtrip_improvement': f"{perf_metrics['roundtrip_speedup']:.1f}x faster",
                'recommended_for': 'Large dataset serialization, SSE streaming, cache operations'
            }
        })
        
    except Exception as e:
        logger.error(f"Error in orjson benchmark: {e}", exc_info=True)
        return jsonify({
            'error': f'Benchmark failed: {str(e)}',
            'orjson_available': ORJSON_AVAILABLE
        }), 500

# Web3 specific endpoints (enhanced with orjson)
@api_bp.route('/web3/status')
def web3_status():
    """Get Web3 integration status with orjson optimization"""
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
                'orjson_enabled': ORJSON_AVAILABLE,
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
        
        response_data = {
            'status': 'available',
            'web3_available': True,
            'web3_version': web3_version,
            'orjson_enabled': ORJSON_AVAILABLE,
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
                'sell_pressure_analysis': True,
                'orjson_optimization': ORJSON_AVAILABLE
            }
        }
        
        # Benchmark large response if orjson available
        if ORJSON_AVAILABLE and len(str(response_data)) > 1000:
            perf_metrics = benchmark_json_performance(response_data, iterations=50)
            response_data['performance_metrics'] = {
                'json_size_bytes': len(str(response_data)),
                'orjson_speedup': round(perf_metrics['serialize_speedup'], 1)
            }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error getting Web3 status: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'web3_available': False,
            'orjson_enabled': ORJSON_AVAILABLE,
            'error': str(e)
        }), 500

@api_bp.route('/web3/analyze-address/<address>')
def analyze_address_web3(address):
    """Analyze an address using Web3 capabilities with orjson optimization"""
    try:
        network = request.args.get('network', 'ethereum')
        
        # Validate network
        supported_networks = [net.value for net in settings.monitor.supported_networks]
        if network not in supported_networks:
            return jsonify({
                'error': f'Network {network} not supported. Supported: {supported_networks}',
                'address': address,
                'network': network,
                'orjson_enabled': ORJSON_AVAILABLE
            }), 400
        
        # Check if Web3 is available
        if not WEB3_AVAILABLE:
            return jsonify({
                'error': 'Web3 not available. Enhanced address analysis requires Web3.',
                'address': address,
                'network': network,
                'orjson_enabled': ORJSON_AVAILABLE
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
                    'network': network,
                    'orjson_enabled': ORJSON_AVAILABLE
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
                'web3_enhanced': True,
                'orjson_enabled': ORJSON_AVAILABLE
            }
            
            # Benchmark orjson performance for complex analysis
            if ORJSON_AVAILABLE and len(str(enhanced_analysis)) > 2000:
                perf_metrics = benchmark_json_performance(enhanced_analysis, iterations=20)
                enhanced_analysis['performance_metrics'] = {
                    'json_size_bytes': len(str(enhanced_analysis)),
                    'orjson_speedup': round(perf_metrics['serialize_speedup'], 1)
                }
            
            return jsonify(enhanced_analysis)
            
        except Exception as e:
            logger.error(f"Error in Web3 address analysis: {e}", exc_info=True)
            return jsonify({
                'error': f'Analysis failed: {str(e)}',
                'address': address,
                'network': network,
                'orjson_enabled': ORJSON_AVAILABLE
            }), 500
        
    except Exception as e:
        logger.error(f"Error in Web3 address analysis: {e}", exc_info=True)
        return jsonify({
            'error': f'Analysis failed: {str(e)}',
            'address': address,
            'network': network,
            'orjson_enabled': ORJSON_AVAILABLE
        }), 500

@api_bp.route('/web3/transaction/<tx_hash>')
def analyze_transaction_web3(tx_hash):
    """Analyze a transaction using Web3 with orjson optimization"""
    try:
        network = request.args.get('network', 'ethereum')
        
        # Check if Web3 is available
        if not WEB3_AVAILABLE:
            return jsonify({
                'error': 'Web3 not available. Enhanced transaction analysis requires Web3.',
                'transaction_hash': tx_hash,
                'network': network,
                'orjson_enabled': ORJSON_AVAILABLE
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
                    'network': network,
                    'orjson_enabled': ORJSON_AVAILABLE
                }), 404
            
            response_data = {
                'transaction_hash': tx_hash,
                'network': network,
                'analysis': analysis,
                'analysis_timestamp': datetime.now().isoformat(),
                'web3_enhanced': True,
                'orjson_enabled': ORJSON_AVAILABLE
            }
            
            # Benchmark orjson performance for detailed transaction analysis
            if ORJSON_AVAILABLE and len(str(response_data)) > 1500:
                perf_metrics = benchmark_json_performance(response_data, iterations=20)
                response_data['performance_metrics'] = {
                    'json_size_bytes': len(str(response_data)),
                    'orjson_speedup': round(perf_metrics['serialize_speedup'], 1)
                }
            
            return jsonify(response_data)
            
        except Exception as e:
            logger.error(f"Error in Web3 transaction analysis: {e}", exc_info=True)
            return jsonify({
                'error': f'Transaction analysis failed: {str(e)}',
                'transaction_hash': tx_hash,
                'network': network,
                'orjson_enabled': ORJSON_AVAILABLE
            }), 500
        
    except Exception as e:
        logger.error(f"Error in Web3 transaction analysis: {e}", exc_info=True)
        return jsonify({
            'error': f'Transaction analysis failed: {str(e)}',
            'transaction_hash': tx_hash,
            'network': network,
            'orjson_enabled': ORJSON_AVAILABLE
        }), 500

# Monitor endpoints with orjson optimization
@api_bp.route('/monitor/status', methods=['GET'])
def monitor_status():
    """Get monitor status with orjson optimization"""
    try:
        logger.info("Monitor status request received")
        
        if monitor:
            status = monitor.get_status()
            logger.info(f"Monitor status: Running={status.get('is_running', False)}")
            
            # Add orjson status to monitor response
            if ORJSON_AVAILABLE:
                status['orjson_enabled'] = True
                if len(str(status)) > 2000:
                    perf_metrics = benchmark_json_performance(status, iterations=20)
                    status['performance_metrics'] = {
                        'orjson_speedup': round(perf_metrics['serialize_speedup'], 1)
                    }
            else:
                status['orjson_enabled'] = False
            
            return jsonify(status)
        else:
            logger.warning("Monitor not initialized, returning default status")
            return jsonify({
                'is_running': False,
                'error': 'Monitor not initialized',
                'last_check': None,
                'next_check': None,
                'orjson_enabled': ORJSON_AVAILABLE,
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
            'orjson_enabled': ORJSON_AVAILABLE,
            'config': {},
            'notification_channels': {},
            'alert_thresholds': {},
            'recent_alerts': []
        }), 500

# All other monitor endpoints with orjson status added
@api_bp.route('/monitor/start', methods=['POST'])
def start_monitor():
    """Start the automated monitoring"""
    try:
        logger.info("Monitor start request received")
        if monitor:
            result = monitor.start_monitoring()
            logger.info(f"Monitor start result: {result}")
            result['orjson_enabled'] = ORJSON_AVAILABLE
            return jsonify(result)
        else:
            return jsonify({
                'status': 'error', 
                'message': 'Monitor not available',
                'orjson_enabled': ORJSON_AVAILABLE
            }), 500
    except Exception as e:
        logger.error(f"Error starting monitor: {e}", exc_info=True)
        return jsonify({
            'status': 'error', 
            'message': str(e),
            'orjson_enabled': ORJSON_AVAILABLE
        }), 500

@api_bp.route('/monitor/stop', methods=['POST'])
def stop_monitor():
    """Stop the automated monitoring"""
    try:
        logger.info("Monitor stop request received")
        if monitor:
            result = monitor.stop_monitoring()
            logger.info(f"Monitor stop result: {result}")
            result['orjson_enabled'] = ORJSON_AVAILABLE
            return jsonify(result)
        else:
            return jsonify({
                'status': 'error', 
                'message': 'Monitor not available',
                'orjson_enabled': ORJSON_AVAILABLE
            }), 500
    except Exception as e:
        logger.error(f"Error stopping monitor: {e}", exc_info=True)
        return jsonify({
            'status': 'error', 
            'message': str(e),
            'orjson_enabled': ORJSON_AVAILABLE
        }), 500

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
            return jsonify({
                'status': 'error', 
                'message': 'Monitor not available',
                'orjson_enabled': ORJSON_AVAILABLE
            }), 500
        
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
        
        return jsonify({
            'status': 'success', 
            'message': 'Check initiated - see console for output',
            'orjson_enabled': ORJSON_AVAILABLE
        })
    except Exception as e:
        logger.error(f"Error initiating check: {e}", exc_info=True)
        return jsonify({
            'status': 'error', 
            'message': str(e),
            'orjson_enabled': ORJSON_AVAILABLE
        }), 500

# Remaining configuration endpoints
@api_bp.route('/config', methods=['GET'])
def get_api_config():
    """Get current API configuration with orjson optimization"""
    try:
        config_data = {
            'status': 'success',
            'config': {
                'environment': settings.environment,
                'web3_available': WEB3_AVAILABLE,
                'orjson_available': ORJSON_AVAILABLE,
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
                },
                'performance': {
                    'orjson_enabled': ORJSON_AVAILABLE,
                    'web3_enhanced': WEB3_AVAILABLE,
                    'expected_improvements': {
                        'json_serialization': '2-5x faster' if ORJSON_AVAILABLE else 'Standard',
                        'sse_streaming': 'Optimized' if ORJSON_AVAILABLE else 'Standard',
                        'cache_operations': 'Enhanced' if ORJSON_AVAILABLE else 'Standard'
                    }
                }
            }
        }
        
        # Benchmark performance for large config responses
        if ORJSON_AVAILABLE and len(str(config_data)) > 2000:
            perf_metrics = benchmark_json_performance(config_data, iterations=20)
            config_data['config']['performance']['benchmark_results'] = {
                'config_size_bytes': len(str(config_data)),
                'orjson_speedup': round(perf_metrics['serialize_speedup'], 1)
            }
        
        return jsonify(config_data)
    except Exception as e:
        logger.error(f"Error getting API config: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Failed to get configuration: {str(e)}',
            'orjson_enabled': ORJSON_AVAILABLE
        }), 500

# Health and debugging endpoints
@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for load balancers with orjson status"""
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
                'web3_available': WEB3_AVAILABLE,
                'orjson_available': ORJSON_AVAILABLE
            }
        }
        
        # Check if any critical components are failing
        warnings = []
        if not alchemy_config.api_key:
            warnings.append('Alchemy API key not configured')
        if not WEB3_AVAILABLE:
            warnings.append('Web3 not available - enhanced features disabled')
        if not ORJSON_AVAILABLE:
            warnings.append('orjson not available - JSON performance not optimized')
        
        if warnings:
            health_status['status'] = 'degraded'
            health_status['warnings'] = warnings
        
        # Performance info
        health_status['performance'] = {
            'json_optimization': 'orjson' if ORJSON_AVAILABLE else 'standard',
            'web3_features': 'enhanced' if WEB3_AVAILABLE else 'standard',
            'expected_performance': 'optimal' if (WEB3_AVAILABLE and ORJSON_AVAILABLE) else 'good'
        }
        
        return jsonify(health_status)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat(),
            'orjson_enabled': ORJSON_AVAILABLE
        }), 500

@api_bp.route('/test/sse')
def test_sse():
    """Enhanced SSE test with Web3 and orjson indicators"""
    def test_generator():
        import time
        
        messages = [
            {'type': 'console', 'message': '🚀 Enhanced SSE Test started', 'level': 'info'},
            {'type': 'console', 'message': f'⚡ Web3 Available: {"✅" if WEB3_AVAILABLE else "❌"}', 'level': 'highlight'},
            {'type': 'console', 'message': f'📊 orjson Available: {"✅" if ORJSON_AVAILABLE else "❌"}', 'level': 'highlight'},
            {'type': 'console', 'message': '📊 Message 1/5', 'level': 'info'},
            {'type': 'progress', 'percentage': 20},
            {'type': 'console', 'message': '📊 Message 2/5', 'level': 'success'},
            {'type': 'progress', 'percentage': 40},
            {'type': 'console', 'message': '🧠 Web3 Enhanced Message 3/5', 'level': 'highlight'},
            {'type': 'progress', 'percentage': 60},
            {'type': 'console', 'message': '⚡ orjson Optimized Message 4/5', 'level': 'warning'},
            {'type': 'progress', 'percentage': 80},
            {'type': 'console', 'message': '✅ Message 5/5 - Enhanced test complete!', 'level': 'success'},
            {'type': 'progress', 'percentage': 100},
            {'type': 'complete', 'status': 'success', 'web3_enhanced': WEB3_AVAILABLE, 'orjson_enabled': ORJSON_AVAILABLE},
            {'type': 'final_complete'}
        ]
        
        for i, message in enumerate(messages):
            try:
                # Sanitize for orjson
                if ORJSON_AVAILABLE:
                    message = sanitize_for_orjson(message)
                    json_str = orjson_dumps_str(message)
                else:
                    import json
                    json_str = json.dumps(message, default=str)
                
                yield f"data: {json_str}\n\n"
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

# Error handlers with orjson status
@api_bp.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found',
        'error': '404 Not Found',
        'orjson_enabled': ORJSON_AVAILABLE
    }), 404

@api_bp.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors"""
    return jsonify({
        'status': 'error',
        'message': 'Method not allowed',
        'error': '405 Method Not Allowed',
        'orjson_enabled': ORJSON_AVAILABLE
    }), 405

@api_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}", exc_info=True)
    return jsonify({
        'status': 'error',
        'message': 'Internal server error',
        'error': '500 Internal Server Error',
        'orjson_enabled': ORJSON_AVAILABLE
    }), 500

@api_bp.errorhandler(Exception)
def handle_exception(error):
    """Handle all other exceptions"""
    logger.error(f"Unhandled exception: {error}", exc_info=True)
    return jsonify({
        'status': 'error',
        'message': 'An unexpected error occurred',
        'error': str(error),
        'orjson_enabled': ORJSON_AVAILABLE
    }), 500