from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import requests
import os
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')

# Configuration
FASTAPI_BASE_URL = os.environ.get('FASTAPI_BASE_URL', 'http://localhost:8001')
FLASK_PORT = int(os.environ.get('FLASK_PORT', 5000))
REQUIRE_AUTH = os.environ.get('REQUIRE_AUTH', 'true').lower() == 'true'
AUTH_PASSWORD = os.environ.get('AUTH_PASSWORD', 'your-password')

def make_api_request(endpoint, method='GET', data=None, timeout=30):
    """Make request to FastAPI backend"""
    try:
        url = f"{FASTAPI_BASE_URL}{endpoint}"
        
        if method == 'GET':
            response = requests.get(url, timeout=timeout)
        elif method == 'POST':
            response = requests.post(url, json=data, timeout=timeout)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"API request failed: {response.status_code} - {response.text}")
            return {"error": f"API request failed: {response.status_code}"}
            
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {str(e)}")
        return {"error": f"Failed to connect to API: {str(e)}"}

def requires_auth(f):
    """Authentication decorator"""
    def decorated_function(*args, **kwargs):
        if REQUIRE_AUTH and not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.context_processor
def inject_globals():
    """Inject global variables into templates"""
    return {
        'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'fastapi_url': FASTAPI_BASE_URL
    }

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if not REQUIRE_AUTH:
        session['authenticated'] = True
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        if password == AUTH_PASSWORD:
            session['authenticated'] = True
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout"""
    session.pop('authenticated', None)
    flash('Logged out successfully', 'info')
    return redirect(url_for('login'))

@app.route('/')
@requires_auth
def index():
    """Dashboard page"""
    return render_template('dashboard.html')

@app.route('/monitor')
@requires_auth
def monitor_page():
    """Monitor page"""
    return render_template('monitor.html')

@app.route('/token')
@requires_auth
def token_details():
    """Token details page"""
    contract = request.args.get('contract')
    token = request.args.get('token') 
    network = request.args.get('network', 'ethereum')
    
    if not contract and not token:
        return render_template('error.html', 
                             title="Missing Parameters",
                             message="Token contract address or symbol is required",
                             error_code="400")
    
    return render_template('token.html')

# API proxy routes to FastAPI backend
@app.route('/api/status')
@requires_auth
def api_status():
    """Get API status from FastAPI"""
    data = make_api_request('/health')
    return jsonify(data)

@app.route('/api/<network>/<analysis_type>')
@requires_auth
def api_analysis(network, analysis_type):
    """Proxy analysis requests to FastAPI"""
    # Get query parameters
    wallets = request.args.get('wallets', 173)
    days = request.args.get('days', 1.0)
    enhanced = request.args.get('enhanced', 'true')
    
    endpoint = f"/api/{network}/{analysis_type}?wallets={wallets}&days={days}&enhanced={enhanced}"
    data = make_api_request(endpoint)
    return jsonify(data)

@app.route('/api/<network>/<analysis_type>/stream')
@requires_auth 
def api_stream(network, analysis_type):
    """Proxy streaming requests to FastAPI"""
    import requests
    
    # Get query parameters
    wallets = request.args.get('wallets', 173)
    days = request.args.get('days', 1.0)
    
    def generate():
        try:
            url = f"{FASTAPI_BASE_URL}/api/{network}/{analysis_type}/stream"
            params = {'wallets': wallets, 'days': days}
            
            with requests.get(url, params=params, stream=True, timeout=120) as response:
                for line in response.iter_lines():
                    if line:
                        yield line.decode('utf-8') + '\n'
        except Exception as e:
            yield f"data: {{'type': 'error', 'error': '{str(e)}'}}\n\n"
    
    return app.response_class(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/monitor/<action>', methods=['GET', 'POST'])
@requires_auth
def api_monitor(action):
    """Proxy monitor requests to FastAPI"""
    if request.method == 'POST':
        data = make_api_request(f'/api/monitor/{action}', method='POST', data=request.get_json())
    else:
        data = make_api_request(f'/api/monitor/{action}')
    
    return jsonify(data)

@app.route('/api/token/<contract>')
@requires_auth
def api_token_details(contract):
    """Get token details from FastAPI"""
    network = request.args.get('network', 'ethereum')
    endpoint = f"/api/token/{contract}?network={network}"
    data = make_api_request(endpoint)
    return jsonify(data)

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('error.html',
                         title="Page Not Found",
                         message="The page you're looking for doesn't exist",
                         error_code="404"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html',
                         title="Internal Server Error", 
                         message="Something went wrong on our end",
                         error_code="500"), 500

@app.errorhandler(503)
def service_unavailable(error):
    return render_template('error.html',
                         title="Service Unavailable",
                         message="The analysis service is currently unavailable",
                         error_code="503"), 503

# Static file handlers for PWA
@app.route('/manifest.json')
def manifest():
    """PWA manifest"""
    return {
        "name": "Crypto Alpha Analysis",
        "short_name": "CryptoAlpha",
        "description": "Real-time smart wallet tracking and alpha token discovery",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f0f23",
        "theme_color": "#667eea",
        "icons": [
            {
                "src": "/static/icons/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "/static/icons/icon-512x512.png", 
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    }

@app.route('/sw.js')
def service_worker():
    """Service worker for PWA"""
    return app.send_static_file('sw.js')

if __name__ == '__main__':
    # Check if FastAPI backend is available
    try:
        health_check = make_api_request('/health')
        if 'error' in health_check:
            logger.warning("FastAPI backend not available. Some features may not work.")
        else:
            logger.info("✅ FastAPI backend connection successful")
    except Exception as e:
        logger.warning(f"Cannot connect to FastAPI backend: {e}")
    
    logger.info(f"🚀 Starting Flask frontend on port {FLASK_PORT}")
    logger.info(f"🔗 Connecting to FastAPI backend at {FASTAPI_BASE_URL}")
    logger.info(f"🔐 Authentication: {'Enabled' if REQUIRE_AUTH else 'Disabled'}")
    
    app.run(
        host='0.0.0.0',
        port=FLASK_PORT,
        debug=True
    )