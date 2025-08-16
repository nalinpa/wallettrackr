import atexit
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, jsonify, render_template_string, request, send_from_directory, session, redirect, url_for, render_template, flash
from flask_cors import CORS
from api_routes import api_bp
from auto_monitor import monitor_bp
from config.settings import settings, flask_config, LoggingConfig
import logging
import os

def create_app():
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Configure CORS
    CORS(app, origins=['http://localhost:3000'] if settings.environment == 'development' else [])
    
    # Flask configuration from settings
    app.secret_key = flask_config.secret_key
    app.config.update({
        'DEBUG': flask_config.debug,
        'PERMANENT_SESSION_LIFETIME': timedelta(hours=flask_config.session_timeout_hours),
        'SESSION_COOKIE_SECURE': settings.environment == 'production',
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SAMESITE': 'Lax'
    })
    
    # Setup logging
    configure_logging(app)
    
    # Register blueprints
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(monitor_bp, url_prefix='/api/monitor')
    
    # Register routes
    register_routes(app)
    register_error_handlers(app)
    register_template_filters(app)
    register_context_processors(app)
    
    def cleanup_connections():
        """Cleanup all httpx connections on shutdown"""
        try:
            # Import here to avoid circular imports
            from tracker.buy_tracker import ComprehensiveBuyTracker
            from tracker.sell_tracker import ComprehensiveSellTracker
            
            # You could maintain a global registry, but for now just log
            print("🔧 Application shutdown - httpx connections will auto-cleanup")
        except Exception as e:
            print(f"Error during connection cleanup: {e}")
    
    atexit.register(cleanup_connections)
    
    return app

def configure_logging(app):
    """Configure application logging"""
    if LoggingConfig.log_to_file:
        from logging.handlers import RotatingFileHandler
        import os
        
        # Ensure log directory exists
        log_dir = os.path.dirname(LoggingConfig.log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        file_handler = RotatingFileHandler(
            LoggingConfig.log_file_path,
            maxBytes=LoggingConfig.max_log_file_size_mb * 1024 * 1024,
            backupCount=LoggingConfig.backup_count
        )
        file_handler.setFormatter(logging.Formatter(LoggingConfig.format))
        file_handler.setLevel(getattr(logging, LoggingConfig.level.value))
        app.logger.addHandler(file_handler)
    
    app.logger.setLevel(getattr(logging, LoggingConfig.level.value))

def register_context_processors(app):
    """Register template context processors"""
    @app.context_processor
    def inject_common_vars():
        """Inject common variables into all templates"""
        return {
            'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'request': request,
            'app_version': getattr(settings, 'version', '1.0.0'),
            'environment': settings.environment,
            'require_password': flask_config.require_password
        }

def require_password(f):
    """Password protection decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if flask_config.require_password:
            if not session.get('authenticated'):
                app.logger.info(f"Unauthenticated access attempt to {request.endpoint}")
                return redirect(url_for('login'))
            
            # Check session timeout
            if 'login_time' in session:
                login_time = datetime.fromisoformat(session['login_time'])
                if datetime.now() - login_time > timedelta(hours=flask_config.session_timeout_hours):
                    session.clear()
                    flash('Session expired. Please log in again.', 'warning')
                    return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function

def register_routes(app):
    """Register application routes"""
    
    # Authentication routes
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if not flask_config.require_password:
            return redirect(url_for('index'))
            
        if request.method == 'POST':
            password = request.form.get('password')
            if password == flask_config.app_password:
                session.permanent = True
                session['authenticated'] = True
                session['login_time'] = datetime.now().isoformat()
                app.logger.info("Successful login")
                flash('Successfully logged in!', 'success')
                
                # Redirect to originally requested page or dashboard
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('index'))
            else:
                app.logger.warning("Failed login attempt")
                flash('Invalid password', 'error')
        
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.clear()
        app.logger.info("User logged out")
        flash('You have been logged out.', 'info')
        return redirect(url_for('login'))

    # Main application routes
    @app.route('/')
    @require_password
    def index():
        """Main dashboard page"""
        return render_template('dashboard.html')

    @app.route('/token')
    @require_password
    def token_page():
        """Token details page"""
        return render_template('token.html')

    @app.route('/monitor')
    @require_password
    def monitor_page():
        """Monitor control page"""
        return render_template('monitor.html')

    # API endpoints
    @app.route('/api/status')
    def api_status():
        """API status endpoint"""
        try:
            from data_service import AnalysisService
            service = AnalysisService()
            cache_status = service.get_cache_status()
            
            return jsonify({
                "status": "online",
                "environment": settings.environment,
                "version": getattr(settings, 'version', '1.0.0'),
                "cached_data": cache_status,
                "last_updated": service.get_last_updated(),
                "supported_networks": [network.value for network in settings.monitor.supported_networks],
                "endpoints": [
                    "/api/eth/buy", "/api/eth/sell",
                    "/api/base/buy", "/api/base/sell",
                    "/api/eth/buy/stream", "/api/eth/sell/stream",
                    "/api/base/buy/stream", "/api/base/sell/stream"
                ]
            })
        except Exception as e:
            app.logger.error(f"Status endpoint error: {e}")
            return jsonify({
                "status": "error",
                "message": "Service unavailable"
            }), 500

    @app.route('/api/refresh-data', methods=['POST'])
    @require_password
    def refresh_data():
        """Refresh data endpoint"""
        try:
            app.logger.info("Data refresh initiated by user")
            # Add actual refresh logic here
            return jsonify({
                "status": "success", 
                "message": "Data refresh initiated",
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            app.logger.error(f"Data refresh error: {e}")
            return jsonify({
                "status": "error",
                "message": "Failed to refresh data"
            }), 500

    @app.route('/api/export-data', methods=['GET'])
    @require_password
    def export_data():
        """Export data endpoint"""
        try:
            # Add actual export logic here
            return jsonify({
                "status": "success", 
                "message": "Export ready",
                "download_url": "/api/download/data.json"
            })
        except Exception as e:
            app.logger.error(f"Data export error: {e}")
            return jsonify({
                "status": "error",
                "message": "Failed to export data"
            }), 500

    @app.route('/api/settings', methods=['GET', 'POST'])
    @require_password
    def api_settings():
        """Settings API endpoint"""
        if request.method == 'POST':
            try:
                # Handle settings update (be careful with security)
                app.logger.info("Settings update requested")
                return jsonify({
                    "status": "success", 
                    "message": "Settings updated"
                })
            except Exception as e:
                app.logger.error(f"Settings update error: {e}")
                return jsonify({
                    "status": "error",
                    "message": "Failed to update settings"
                }), 500
        else:
            # Return safe settings (no sensitive data)
            return jsonify({
                "status": "success",
                "settings": {
                    "environment": settings.environment,
                    "networks": [net.value for net in settings.monitor.supported_networks],
                    "analysis": {
                        "default_wallet_count": settings.analysis.default_wallet_count,
                        "max_wallet_count": settings.analysis.max_wallet_count,
                        "max_days_back": settings.analysis.max_days_back
                    },
                    "monitor": {
                        "default_interval": settings.monitor.default_check_interval_minutes,
                        "alert_thresholds": settings.monitor.alert_thresholds
                    }
                }
            })

    # Static file routes
    @app.route('/static/<path:filename>')
    def static_files(filename):
        """Serve static files"""
        return send_from_directory('static', filename)

    @app.route('/manifest.json')
    def manifest():
        """Serve PWA manifest"""
        return send_from_directory('static', 'manifest.json', mimetype='application/json')

    @app.route('/sw.js')
    def service_worker():
        """Serve service worker"""
        return send_from_directory('static', 'sw.js', mimetype='application/javascript')

    @app.route('/pwa.js')
    def pwa_script():
        """Serve PWA script"""
        return send_from_directory('static', 'pwa.js', mimetype='application/javascript')

    @app.route('/offline')
    def offline():
        """Offline fallback page"""
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Crypto Alpha - Offline</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #2d1b69 100%);
                    color: white;
                    text-align: center;
                    padding: 50px 20px;
                    margin: 0;
                    min-height: 100vh;
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                }
                .offline-content {
                    max-width: 400px;
                    background: rgba(255,255,255,0.1);
                    padding: 40px;
                    border-radius: 15px;
                    backdrop-filter: blur(10px);
                }
                h1 { margin-bottom: 20px; }
                p { margin-bottom: 30px; opacity: 0.9; }
                button {
                    background: linear-gradient(135deg, #667eea, #764ba2);
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 8px;
                    cursor: pointer;
                    font-size: 16px;
                }
            </style>
        </head>
        <body>
            <div class="offline-content">
                <h1>🔌 You're Offline</h1>
                <p>No internet connection detected. Some features may not be available.</p>
                <button onclick="window.location.reload()">Try Again</button>
            </div>
        </body>
        </html>
        ''')

def register_error_handlers(app):
    """Register error handlers"""
    
    @app.errorhandler(404)
    def not_found_error(error):
        app.logger.warning(f"404 error: {request.url}")
        return render_template('error.html', 
                             title="Page Not Found",
                             message="The page you're looking for doesn't exist.",
                             error_code="404",
                             back_url=url_for('index'),
                             back_text="Back to Dashboard"), 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"500 error: {error}")
        return render_template('error.html',
                             title="Internal Server Error",
                             message="Something went wrong on our end. Please try again later.",
                             error_code="500",
                             back_url=url_for('index'),
                             back_text="Back to Dashboard"), 500

    @app.errorhandler(Exception)
    def handle_exception(e):
        app.logger.error(f"Unhandled exception: {e}")
        return render_template('error.html',
                             title="Application Error",
                             message="An unexpected error occurred.",
                             details=str(e) if flask_config.debug else None,
                             back_url=url_for('index'),
                             back_text="Back to Dashboard"), 500

def register_template_filters(app):
    """Register Jinja2 template filters"""
    
    @app.template_filter('datetime')
    def datetime_filter(timestamp):
        """Format datetime for templates"""
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                return timestamp
        return timestamp.strftime('%Y-%m-%d %H:%M:%S') if timestamp else ''

    @app.template_filter('timeago')
    def timeago_filter(timestamp):
        """Human readable time ago"""
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                return timestamp
        
        if not timestamp:
            return ''
            
        now = datetime.now()
        diff = now - timestamp
        
        if diff.days > 0:
            return f"{diff.days} days ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hours ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minutes ago"
        else:
            return "Just now"

    @app.template_filter('currency')
    def currency_filter(value, symbol='$'):
        """Format currency values"""
        if value is None:
            return f'{symbol}0.00'
        try:
            return f'{symbol}{float(value):,.2f}'
        except (ValueError, TypeError):
            return f'{symbol}0.00'

# Create the app instance
app = create_app()

if __name__ == '__main__':
    print("🚀 Starting Crypto Alpha Analysis API...")
    print(f"Environment: {settings.environment}")
    print(f"Debug mode: {flask_config.debug}")
    print(f"Password required: {flask_config.require_password}")
    print(f"Supported networks: {[net.value for net in settings.monitor.supported_networks]}")
    print(f"Log level: {LoggingConfig.level.value}")
    
    if flask_config.require_password and not flask_config.app_password:
        print("⚠️  Warning: Password protection is enabled but APP_PASSWORD is not set!")
    
    print("\n✅ Starting Flask server...")
    
    app.run(
        debug=flask_config.debug,
        host=flask_config.host,
        port=flask_config.port
    )