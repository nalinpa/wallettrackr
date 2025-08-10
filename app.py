from functools import wraps
from flask import Flask, request, session, redirect, url_for, render_template_string
from flask_cors import CORS
from api_routes import api_bp
from templates import HTML_TEMPLATE
from auto_monitor import monitor_bp, monitor
import os

app = Flask(__name__)
CORS(app)

app.secret_key = os.getenv('SECRET_KEY')

# Register API blueprint
app.register_blueprint(api_bp, url_prefix='/api')

# Register Monitor blueprint
app.register_blueprint(monitor_bp, url_prefix='/api')

APP_PASSWORD = os.getenv('APP_PASSWORD', None)

# Load the monitor page template
def load_monitor_template():
    """Load monitor template from file or use embedded"""
    template_file = 'templates/monitor.html'
    if os.path.exists(template_file):
        with open(template_file, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
        
def require_password(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if APP_PASSWORD and not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == APP_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        else:
            error = 'Invalid password'
    else:
        error = None
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Login</title>
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
                    width: 300px;
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
                }
                button:hover {
                    background: linear-gradient(135deg, #764ba2, #667eea);
                }
                .error {
                    color: #ef5350;
                    text-align: center;
                    margin-bottom: 15px;
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
    return redirect(url_for('login'))

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/token')
def token_page():
    """Serve the token details page"""
    try:
        # Read the token details HTML template
        with open('templates/token.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Token Details</title>
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    background: #1a1a2e; 
                    color: white; 
                    padding: 20px; 
                }
                .error { 
                    background: #ff4757; 
                    padding: 20px; 
                    border-radius: 10px; 
                }
            </style>
        </head>
        <body>
            <div class="error">
                <h1>Token Details Page Not Found</h1>
                <p>The token details template (paste.txt) was not found.</p>
                <a href="/">Back to Dashboard</a>
            </div>
        </body>
        </html>
        """, 404
        
@app.route('/monitor')
@require_password
def monitor_page():
    """Monitor control page"""
    try:
        with open('templates/monitor.html', 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except FileNotFoundError:
        return """
        <h1>Monitor Page Not Found</h1>
        <p>Please save the monitor template to templates/monitor.html</p>
        <a href="/">Back to Dashboard</a>
        """

with app.app_context():
    def initialize():
        """Initialize the app"""
        print("🚀 Initializing Crypto Alpha Analysis System...")
        
        # Check if auto-start is enabled
        if os.getenv('AUTO_START_MONITOR', 'false').lower() == 'true':
            print("🤖 Auto-starting monitor...")
            result = monitor.start_monitoring()
            print(f"   {result['message']}")

if __name__ == '__main__':
    print("🚀 Starting Crypto Alpha Analysis API...")
    print("📊 Available endpoints:")
    print("   - http://localhost:5000/ (Web Dashboard)")
    print("   - http://localhost:5000/monitor (Monitor Control)")
    print("   - http://localhost:5000/api/eth/buy")
    print("   - http://localhost:5000/api/eth/sell") 
    print("   - http://localhost:5000/api/base/buy")
    print("   - http://localhost:5000/api/base/sell")
    print("   - http://localhost:5000/api/monitor/status")
    print("   - http://localhost:5000/api/monitor/start")
    print("   - http://localhost:5000/api/monitor/stop")
    print("   - http://localhost:5000/api/status")
    print("\n🤖 Monitor Features:")
    print("   - Automated hourly checks")
    print("   - New token detection")
    print("   - Activity surge alerts")
    print("   - Multiple notification channels")
    print("\n✅ Starting Flask server...")
    
    app.run(debug=True, host='0.0.0.0', port=5000)