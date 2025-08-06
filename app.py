from flask import Flask, render_template_string
from flask_cors import CORS
from api_routes import api_bp
from templates import HTML_TEMPLATE

app = Flask(__name__)
CORS(app)

# Register API blueprint
app.register_blueprint(api_bp, url_prefix='/api')

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    print("🚀 Starting Crypto Alpha Analysis API...")
    print("📊 Available endpoints:")
    print("   - http://localhost:5000/ (Web Dashboard)")
    print("   - http://localhost:5000/api/eth/buy")
    print("   - http://localhost:5000/api/eth/sell") 
    print("   - http://localhost:5000/api/base/buy")
    print("   - http://localhost:5000/api/base/sell")
    print("   - http://localhost:5000/api/status")
    print("\n✅ Starting Flask server...")
    
    app.run(debug=True, host='0.0.0.0', port=5000)