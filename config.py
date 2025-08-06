import os
from typing import Dict, Any

class Config:
    """Base configuration class"""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    DEBUG = os.environ.get('FLASK_ENV') == 'development'
    
    # Server settings
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 5000))
    
    # Analysis settings
    DEFAULT_WALLET_COUNT = int(os.environ.get('DEFAULT_WALLET_COUNT', 50))
    DEFAULT_DAYS_BACK_ETH = int(os.environ.get('DEFAULT_DAYS_BACK_ETH', 7))
    DEFAULT_DAYS_BACK_BASE = int(os.environ.get('DEFAULT_DAYS_BACK_BASE', 14))
    
    # Cache settings
    CACHE_TIMEOUT = int(os.environ.get('CACHE_TIMEOUT', 300))  # 5 minutes
    
    # Rate limiting
    RATE_LIMIT_ENABLED = os.environ.get('RATE_LIMIT_ENABLED', 'false').lower() == 'true'
    RATE_LIMIT_PER_MINUTE = int(os.environ.get('RATE_LIMIT_PER_MINUTE', 60))
    
    # CORS settings
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*').split(',')
    
    @staticmethod
    def get_analysis_params(network: str) -> Dict[str, Any]:
        """Get analysis parameters for specific network"""
        base_params = {
            'num_wallets': Config.DEFAULT_WALLET_COUNT,
        }
        
        if network == 'eth':
            base_params['days_back'] = Config.DEFAULT_DAYS_BACK_ETH
        elif network == 'base':
            base_params['days_back'] = Config.DEFAULT_DAYS_BACK_BASE
        else:
            base_params['days_back'] = 7  # default
            
        return base_params

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    
class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set for production environment")

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True
    DEFAULT_WALLET_COUNT = 10  # Smaller for testing
    DEFAULT_DAYS_BACK_ETH = 3
    DEFAULT_DAYS_BACK_BASE = 3

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}