from flask import Flask, render_template_string
from flask_cors import CORS
from api_routes import api_bp
from templates import HTML_TEMPLATE
from auto_monitor import monitor_bp, monitor
import os

app = Flask(__name__)
CORS(app)

# Register API blueprint
app.register_blueprint(api_bp, url_prefix='/api')

# Register Monitor blueprint
app.register_blueprint(monitor_bp, url_prefix='/api')

# Load the monitor page template
def load_monitor_template():
    """Load monitor template from file or use embedded"""
    template_file = 'templates/monitor.html'
    if os.path.exists(template_file):
        with open(template_file, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/monitor')
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