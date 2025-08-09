from functools import wraps
from flask import Flask, jsonify, render_template_string, session, redirect, url_for, request
from flask_cors import CORS

from api_routes import api_bp
from templates import HTML_TEMPLATE
from auto_monitor import monitor_bp, monitor
from shared_utils import BaseTracker
import os
import logging

app = Flask(__name__)
CORS(app)

# Production-ready configuration
app.secret_key = os.getenv('SECRET_KEY', 'change-this-in-production')

# Configure logging for production
if os.getenv('FLASK_ENV') == 'production':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s'
    )
    app.logger.setLevel(logging.INFO)

# Register API blueprint
app.register_blueprint(api_bp, url_prefix='/api')

# Register Monitor blueprint
app.register_blueprint(monitor_bp, url_prefix='/api')

# Get password from environment variable
APP_PASSWORD = os.getenv('APP_PASSWORD', None)

def require_password(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if APP_PASSWORD and not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Load the monitor page template
def load_monitor_template():
    """Load monitor template from file or use embedded"""
    template_file = 'templates/monitor.html'
    if os.path.exists(template_file):
        with open(template_file, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    return None

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    try:
        # Test MongoDB connection
        tracker = BaseTracker()
        if tracker.test_connection():
            return jsonify({
                "status": "healthy",
                "database": "connected",
                "timestamp": "2024-01-01T00:00:00Z"
            })
        else:
            return jsonify({
                "status": "unhealthy", 
                "database": "disconnected"
            }), 503
    except Exception as e:
        app.logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 503

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == APP_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        else:
            error = 'Invalid password'
            app.logger.warning(f"Failed login attempt from {request.remote_addr}")
    else:
        error = None
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Login - Crypto Alpha Analysis</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #2d1b69 100%);
                    color: #e0e0e0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                }
                .login-box {
                    background: linear-gradient(145deg, #1e1e3a, #2a2a5a);
                    padding: 40px;
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
                    width: 90%;
                    max-width: 300px;
                }
                h2 {
                    text-align: center;
                    color: #ffa726;
                    margin-bottom: 30px;
                }
                input[type="password"] {
                    width: 100%;
                    padding: 12px;
                    background: rgba(255, 255, 255, 0.1);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 8px;
                    color: white;
                    font-size: 16px;
                    margin-bottom: 20px;
                    box-sizing: border-box;
                }
                button {
                    width: 100%;
                    padding: 12px;
                    background: linear-gradient(135deg, #667eea, #764ba2);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.3s ease;
                }
                button:hover {
                    background: linear-gradient(135deg, #764ba2, #667eea);
                    transform: translateY(-2px);
                }
                .error {
                    color: #ef5350;
                    text-align: center;
                    margin-bottom: 15px;
                    background: rgba(239, 83, 80, 0.1);
                    padding: 10px;
                    border-radius: 8px;
                }
                @media (max-width: 480px) {
                    .login-box {
                        padding: 30px 20px;
                    }
                }
            </style>
        </head>
        <body>
            <div class="login-box">
                <h2>🔐 Crypto Alpha Login</h2>
                {% if error %}
                    <div class="error">{{ error }}</div>
                {% endif %}
                <form method="post">
                    <input type="password" name="password" placeholder="Enter password" required autofocus>
                    <button type="submit">Login</button>
                </form>
            </div>
        </body>
        </html>
    ''', error=error)

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    app.logger.info(f"User logged out from {request.remote_addr}")
    return redirect(url_for('login'))

@app.route('/')
@require_password
def index():
    """Main dashboard page"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/monitor')
@require_password
def monitor_page():
    """Monitor control page"""
    try:
        template_content = load_monitor_template()
        if template_content:
            return template_content
        else:
            # Fallback if template file doesn't exist
            return """
            <h1>Monitor Page</h1>
            <p>Monitor template not found. Please ensure templates/monitor.html exists.</p>
            <a href="/">Back to Dashboard</a>
            """
    except Exception as e:
        app.logger.error(f"Error loading monitor template: {e}")
        return f"""
        <h1>Monitor Page Error</h1>
        <p>Error loading monitor page: {str(e)}</p>
        <a href="/">Back to Dashboard</a>
        """, 500

@app.route('/token')
@require_password
def token_details_page():
    """Token details page"""
    try:
        # Check if token.html exists, if not create a basic template
        token_template_path = 'templates/token.html'
        if os.path.exists(token_template_path):
            with open(token_template_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        else:
            # Return a basic token details template
            return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Token Details - Crypto Alpha Analysis</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #2d1b69 100%);
                        color: #e0e0e0;
                        margin: 0;
                        padding: 20px;
                    }
                    .container {
                        max-width: 1200px;
                        margin: 0 auto;
                    }
                    h1 {
                        color: #ffa726;
                        text-align: center;
                    }
                    .nav {
                        text-align: center;
                        margin: 20px 0;
                    }
                    .nav a {
                        color: #4fc3f7;
                        text-decoration: none;
                        margin: 0 15px;
                        font-weight: 600;
                    }
                    .nav a:hover {
                        text-decoration: underline;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>📊 Token Details</h1>
                    <div class="nav">
                        <a href="/">Dashboard</a>
                        <a href="/monitor">Monitor</a>
                    </div>
                    <p>Token details functionality coming soon...</p>
                </div>
            </body>
            </html>
            """
        
    except Exception as e:
        app.logger.error(f"Error loading token template: {e}")
        return f"""
        <h1>Error</h1>
        <p>Error loading token details page: {str(e)}</p>
        <a href="/">Back to Dashboard</a>
        """, 500

@app.errorhandler(404)
def not_found(error):
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>404 - Page Not Found</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #2d1b69 100%);
                    color: #e0e0e0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    text-align: center;
                }
                .error-box {
                    background: linear-gradient(145deg, #1e1e3a, #2a2a5a);
                    padding: 40px;
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
                }
                h1 { color: #ffa726; }
                a {
                    color: #4fc3f7;
                    text-decoration: none;
                    font-weight: 600;
                }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <div class="error-box">
                <h1>404 - Page Not Found</h1>
                <p>The page you're looking for doesn't exist.</p>
                <a href="/">← Back to Dashboard</a>
            </div>
        </body>
        </html>
    '''), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Internal server error: {error}")
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>500 - Internal Server Error</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #2d1b69 100%);
                    color: #e0e0e0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    text-align: center;
                }
                .error-box {
                    background: linear-gradient(145deg, #1e1e3a, #2a2a5a);
                    padding: 40px;
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
                }
                h1 { color: #ef5350; }
                a {
                    color: #4fc3f7;
                    text-decoration: none;
                    font-weight: 600;
                }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <div class="error-box">
                <h1>500 - Internal Server Error</h1>
                <p>Something went wrong on our end.</p>
                <a href="/">← Back to Dashboard</a>
            </div>
        </body>
        </html>
    '''), 500

# Initialize app context
with app.app_context():
    def initialize():
        """Initialize the app"""
        print("🚀 Initializing Crypto Alpha Analysis System...")
        
        # Log configuration info
        if os.getenv('FLASK_ENV') == 'production':
            app.logger.info("Application starting in production mode")
            app.logger.info(f"Password protection: {'enabled' if APP_PASSWORD else 'disabled'}")
        
        # Test database connection on startup
        try:
            tracker = BaseTracker()
            if tracker.test_connection():
                print("✅ Database connection successful")
                if os.getenv('FLASK_ENV') == 'production':
                    app.logger.info("Database connection established")
            else:
                print("❌ Database connection failed")
                if os.getenv('FLASK_ENV') == 'production':
                    app.logger.error("Database connection failed")
        except Exception as e:
            print(f"❌ Database initialization error: {e}")
            if os.getenv('FLASK_ENV') == 'production':
                app.logger.error(f"Database initialization error: {e}")

if __name__ == '__main__':
    print("🚀 Starting Crypto Alpha Analysis API...")
    print("📊 Available endpoints:")
    print("   - http://localhost:5000/ (Web Dashboard)")
    print("   - http://localhost:5000/monitor (Monitor Control)")
    print("   - http://localhost:5000/token (Token Details)")
    print("   - http://localhost:5000/api/eth/buy")
    print("   - http://localhost:5000/api/eth/sell") 
    print("   - http://localhost:5000/api/base/buy")
    print("   - http://localhost:5000/api/base/sell")
    print("   - http://localhost:5000/api/monitor/status")
    print("   - http://localhost:5000/api/monitor/start")
    print("   - http://localhost:5000/api/monitor/stop")
    print("   - http://localhost:5000/api/status")
    print("   - http://localhost:5000/health")
    print("\n🤖 Monitor Features:")
    print("   - Automated hourly checks")
    print("   - New token detection")
    print("   - Activity surge alerts")
    print("   - Multiple notification channels")
    print("\n🔐 Security:")
    print(f"   - Password protection: {'enabled' if APP_PASSWORD else 'disabled'}")
    print("\n✅ Starting Flask server...")
    
    initialize()
    
    # Development server
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    app.run(debug=debug, host='0.0.0.0', port=port)