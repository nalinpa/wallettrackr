from datetime import datetime
from functools import wraps
from flask import Flask, jsonify, request, session, redirect, url_for, render_template, flash
from flask_cors import CORS
from api_routes import api_bp
from auto_monitor import monitor_bp
import os

app = Flask(__name__)
CORS(app)

app.secret_key = os.getenv('SECRET_KEY')

# Register API blueprint
app.register_blueprint(api_bp, url_prefix='/api')

# Register Monitor blueprint
app.register_blueprint(monitor_bp, url_prefix='/api')

APP_PASSWORD = os.getenv('APP_PASSWORD', None)

@app.context_processor
def inject_common_vars():
    """Inject common variables into all templates"""
    return {
        'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'request': request  # For navbar active state
    }
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
            flash('Successfully logged in!', 'success')
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid password')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@require_password
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/token')
@require_password
def token_page():
    """Serve the token details page"""
    return render_template('token.html')

@app.route('/monitor')
@require_password
def monitor_page():
    """Monitor control page"""
    return render_template('monitor.html')

@app.route('/api/status')
def api_status():
    """API status endpoint"""
    from data_service import AnalysisService
    service = AnalysisService()
    
    cache_status = service.get_cache_status()
    
    return {
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
    }

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    return render_template('error.html', 
                         title="Page Not Found",
                         message="The page you're looking for doesn't exist.",
                         error_code="404",
                         back_url=url_for('index'),
                         back_text="Back to Dashboard"), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return render_template('error.html',
                         title="Internal Server Error",
                         message="Something went wrong on our end. Please try again later.",
                         error_code="500",
                         back_url=url_for('index'),
                         back_text="Back to Dashboard"), 500

@app.errorhandler(Exception)
def handle_exception(e):
    """Handle general exceptions"""
    return render_template('error.html',
                         title="Application Error",
                         message="An unexpected error occurred.",
                         details=str(e) if app.debug else None,
                         back_url=url_for('index'),
                         back_text="Back to Dashboard"), 500
    
# JavaScript functions for navbar tools
@app.route('/api/refresh-data', methods=['POST'])
@require_password
def refresh_data():
    """Refresh data endpoint for navbar"""
    return jsonify({"status": "success", "message": "Data refresh initiated"})

@app.route('/api/export-data', methods=['GET'])
@require_password
def export_data():
    """Export data endpoint for navbar"""
    return jsonify({"status": "success", "message": "Export functionality would go here"})

@app.route('/api/settings', methods=['GET', 'POST'])
@require_password
def settings():
    """Settings endpoint for navbar"""
    if request.method == 'POST':
        # Handle settings update
        return jsonify({"status": "success", "message": "Settings updated"})
    else:
        # Return current settings
        return jsonify({"status": "success", "settings": {}})

# Template filters
@app.template_filter('datetime')
def datetime_filter(timestamp):
    """Format datetime for templates"""
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except:
            return timestamp
    return timestamp.strftime('%Y-%m-%d %H:%M:%S') if timestamp else ''

@app.template_filter('timeago')
def timeago_filter(timestamp):
    """Human readable time ago"""
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except:
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

with app.app_context():
    def initialize():
        """Initialize the app"""
        print("🚀 Initializing Crypto Alpha Analysis System...")
    

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