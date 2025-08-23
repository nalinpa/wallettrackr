import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
import json
from dotenv import load_dotenv

load_dotenv()

class NetworkType(str, Enum):
    ETHEREUM = "ethereum"
    BASE = "base"

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

@dataclass
class DatabaseConfig:
    """Database configuration"""
    mongo_uri: str
    db_name: str = 'crypto_tracker'
    wallets_collection: str = 'smart_wallets'
    connection_timeout: int = 5000
    
    def __post_init__(self):
        if not self.mongo_uri:
            raise ValueError("MONGO_URI environment variable is required")

@dataclass
class AlchemyConfig:
    """Alchemy API configuration"""
    api_key: str
    rate_limit_per_second: int = 25
    timeout_seconds: int = 30
    max_retries: int = 3
    
    def __post_init__(self):
        if not self.api_key:
            raise ValueError("ALCHEMY_API_KEY environment variable is required")
    
    @property
    def eth_url(self) -> str:
        return f"https://eth-mainnet.g.alchemy.com/v2/"
    
    @property 
    def base_url(self) -> str:
        return f"https://base-mainnet.g.alchemy.com/v2/"

@dataclass
class AuthConfig:
    """Authentication configuration"""
    require_auth: bool = False
    app_password: str = "admin"
    secret_key: str = "crypto-tracker-secret-key-change-this"
    session_timeout_hours: int = 24
    
    # Security settings
    secure_cookies: bool = True  # Use secure cookies in production
    httponly_cookies: bool = True
    samesite_cookies: str = "lax"  # "strict", "lax", or "none"
    
    def __post_init__(self):
        # Ensure we have a proper secret key
        if self.secret_key == "crypto-tracker-secret-key-change-this" and self.require_auth:
            print("[WARNING] Warning: Using default secret key. Please set SECRET_KEY environment variable.")
        
        # Warn about default password
        if self.app_password == "admin" and self.require_auth:
            print("[WARNING] Warning: Using default password 'admin'. Please set APP_PASSWORD environment variable.")

@dataclass
class AnalysisConfig:
    """Analysis parameters configuration"""
    # Minimum values
    min_eth_value: float = 0.1
    min_eth_value_base: float = 0.05  # Lower for Base due to cheaper gas
    
    # Default analysis parameters
    default_wallet_count: int = 173
    max_wallet_count: int = 500
    default_days_back_eth: int = 1
    default_days_back_base: int = 1
    max_days_back: int = 30
    
    # Token filtering
    excluded_tokens: List[str] = field(default_factory=lambda: [
        # Stablecoins
        "USDC", "USDT", "DAI", "FRAX", "BUSD", "TUSD", "GUSD", "PYUSD",
        "USDbC", "USDP", "sUSD", "LUSD", "MIM", "DOLA", "VUSD", "BEAN", "USDe",
        
        # ETH and wrapped tokens
        "ETH", "WETH", "stETH", "wstETH", "rETH", "cbETH", "frxETH", "sfrxETH",
        
        # Major DeFi tokens
        "AAVE", "UNI", "SUSHI", "CRV", "CVX", "BAL", "YFI", "SNX", "MKR", "COMP",
        "PENDLE", "LDO", "FXS", "OHM", "TRIBE", "FEI", "ALCX", "SPELL", "ICE",
        
        # Base specific excluded tokens
        "BALD", "TOSHI", "BRETT", "NORMIE", "DEGEN", "HIGHER", "MOCHI"
    ])
    
    # Alpha scoring parameters
    alpha_scoring: Dict[str, float] = field(default_factory=lambda: {
        'wallet_quality_weight': 0.4,
        'eth_investment_weight': 0.3,
        'consensus_weight': 0.2,
        'platform_diversity_weight': 0.1,
        'max_possible_wallet_score': 300.0
    })

@dataclass
class MonitorConfig:
    """Monitoring system configuration"""
    # Timing
    default_check_interval_minutes: int = 60
    min_check_interval_minutes: int = 5
    max_check_interval_minutes: int = 1440  # 24 hours
    
    # Networks to monitor
    default_networks: List[NetworkType] = field(default_factory=lambda: [NetworkType.BASE])
    supported_networks: List[NetworkType] = field(default_factory=lambda: [NetworkType.ETHEREUM, NetworkType.BASE])
    
    # Alert thresholds
    alert_thresholds: Dict[str, float] = field(default_factory=lambda: {
        'min_wallets': 2,
        'min_eth_spent': 0.5,
        'min_alpha_score': 30.0,
        'surge_multiplier': 2.0
    })
    
    # Notification settings
    max_alerts_per_notification: int = 5
    max_stored_alerts: int = 100

@dataclass
class TelegramConfig:
    """Telegram notification configuration"""
    bot_token: Optional[str] = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id: Optional[str] = os.getenv('TELEGRAM_CHAT_ID')
    enabled: bool = False
    max_message_length: int = 4096
    
    def __post_init__(self):
        if self.bot_token and self.chat_id:
            self.enabled = True

@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: LogLevel = LogLevel.INFO
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # File logging
    log_to_file: bool = False
    log_file_path: str = "logs/app.log"
    max_log_file_size_mb: int = 10
    backup_count: int = 5
    
    # JSON logging for production
    json_logging: bool = False

@dataclass
class Settings:
    """Main application settings"""
    database: DatabaseConfig
    alchemy: AlchemyConfig
    analysis: AnalysisConfig
    monitor: MonitorConfig
    telegram: TelegramConfig
    logging: LoggingConfig
    auth: AuthConfig  # Added auth configuration
    
    # Environment
    environment: str = "development"
    
    @classmethod
    def from_env(cls) -> 'Settings':
        environment = os.getenv('ENVIRONMENT', os.getenv('ENV', 'development'))
        
        return cls(
            database=DatabaseConfig(
                mongo_uri=os.getenv('MONGO_URI'),
                db_name=os.getenv('DB_NAME', 'crypto_tracker'),
                wallets_collection=os.getenv('WALLETS_COLLECTION', 'smart_wallets'),
                connection_timeout=int(os.getenv('DB_CONNECTION_TIMEOUT', 5000))
            ),
            
            alchemy=AlchemyConfig(
                api_key=os.getenv('ALCHEMY_API_KEY'),
                rate_limit_per_second=int(os.getenv('ALCHEMY_RATE_LIMIT', 25)),
                timeout_seconds=int(os.getenv('ALCHEMY_TIMEOUT', 30)),
                max_retries=int(os.getenv('ALCHEMY_MAX_RETRIES', 3))
            ),
            
            analysis=AnalysisConfig(
                min_eth_value=float(os.getenv('MIN_ETH_VALUE', 0.01)),
                min_eth_value_base=float(os.getenv('MIN_ETH_VALUE_BASE', 0.005)),
                default_wallet_count=int(os.getenv('DEFAULT_WALLET_COUNT', 173)),
                max_wallet_count=int(os.getenv('MAX_WALLET_COUNT', 500)),
                default_days_back_eth=int(os.getenv('DEFAULT_DAYS_BACK_ETH', 1)),
                default_days_back_base=int(os.getenv('DEFAULT_DAYS_BACK_BASE', 1)),
                max_days_back=int(os.getenv('MAX_DAYS_BACK', 30))
            ),
            
            monitor=MonitorConfig(
                default_check_interval_minutes=int(os.getenv('MONITOR_INTERVAL_MINUTES', 60)),
                alert_thresholds={
                    'min_wallets': float(os.getenv('ALERT_MIN_WALLETS', 2)),
                    'min_eth_spent': float(os.getenv('ALERT_MIN_ETH', 0.5)),
                    'min_alpha_score': float(os.getenv('ALERT_MIN_SCORE', 30.0)),
                    'surge_multiplier': float(os.getenv('ALERT_SURGE_MULTIPLIER', 2.0))
                }
            ),
            
            telegram=TelegramConfig(
                bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
                chat_id=os.getenv('TELEGRAM_CHAT_ID')
            ),
            
            
            # New auth configuration
            auth=AuthConfig(
                require_auth=os.getenv('REQUIRE_AUTH', 'false').lower() == 'true',
                app_password=os.getenv('APP_PASSWORD', 'admin'),
                secret_key=os.getenv('SECRET_KEY', 'crypto-tracker-secret-key-change-this'),
                session_timeout_hours=int(os.getenv('SESSION_TIMEOUT_HOURS', 24)),
                secure_cookies=environment == 'production',
                httponly_cookies=True,
                samesite_cookies=os.getenv('COOKIE_SAMESITE', 'lax')
            ),
            
            logging=LoggingConfig(
                level=LogLevel(os.getenv('LOG_LEVEL', 'INFO')),
                log_to_file=os.getenv('LOG_TO_FILE', 'false').lower() == 'true',
                json_logging=environment == 'production'
            ),
            
            environment=environment
        )
    
    def get_network_config(self, network: NetworkType) -> Dict:
        """Get network-specific configuration"""
        if network == NetworkType.BASE:
            return {
                'min_eth_value': self.analysis.min_eth_value_base,
                'default_days_back': self.analysis.default_days_back_base,
                'alchemy_url': self.alchemy.base_url
            }
        elif network == NetworkType.ETHEREUM:
            return {
                'min_eth_value': self.analysis.min_eth_value,
                'default_days_back': self.analysis.default_days_back_eth,
                'alchemy_url': self.alchemy.eth_url
            }
        else:
            raise ValueError(f"Unsupported network: {network}")
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of issues"""
        issues = []
        
        # Validate ranges
        if self.analysis.default_wallet_count > self.analysis.max_wallet_count:
            issues.append("default_wallet_count cannot exceed max_wallet_count")
        
        if self.analysis.default_days_back_eth > self.analysis.max_days_back:
            issues.append("default_days_back_eth cannot exceed max_days_back")
            
        if self.monitor.default_check_interval_minutes < self.monitor.min_check_interval_minutes:
            issues.append("check_interval_minutes cannot be less than min_check_interval_minutes")
        
        # Validate Telegram config
        if self.telegram.enabled and (not self.telegram.bot_token or not self.telegram.chat_id):
            issues.append("Telegram bot_token and chat_id required when enabled")
        
        # Validate auth config
        if self.auth.require_auth:
            if self.auth.app_password == "admin":
                issues.append("Default password 'admin' should be changed for security")
            if self.auth.secret_key == "crypto-tracker-secret-key-change-this":
                issues.append("Default secret key should be changed for security")
            if self.auth.session_timeout_hours < 1:
                issues.append("session_timeout_hours must be at least 1")
        
        return issues
    
    def to_dict(self) -> Dict:
        """Convert settings to dictionary (for debugging/API responses)"""
        def clean_dict(obj):
            if hasattr(obj, '__dict__'):
                result = {}
                for key, value in obj.__dict__.items():
                    if 'token' in key.lower() or 'key' in key.lower() or 'secret' in key.lower() or 'password' in key.lower():
                        result[key] = '[REDACTED]' if value else None
                    elif hasattr(value, '__dict__'):
                        result[key] = clean_dict(value)
                    else:
                        result[key] = value
                return result
            return obj
        
        return clean_dict(self)

# Create global settings instance
try:
    settings = Settings.from_env()
    
    # Validate settings
    validation_issues = settings.validate()
    if validation_issues:
        print("[WARNING] Configuration validation issues:")
        for issue in validation_issues:
            print(f"   - {issue}")
    
    print(f"[OK] Configuration loaded successfully for {settings.environment} environment")
    print(f"   Auth enabled: {settings.auth.require_auth}")
    print(f"   Password configured: {bool(settings.auth.app_password and settings.auth.app_password != 'admin')}")
    
except Exception as e:
    print(f"[ERROR] Failed to load configuration: {e}")
    print("Please check your environment variables")
    raise

class NetworkConfig:
    """Network configuration for alchemy client compatibility"""
    
    @staticmethod
    def get_config(network: str) -> Dict:
        """Get network configuration for alchemy client"""
        network = network.lower()
        
        if network == "ethereum":
            return {
                'alchemy_url': f"https://eth-mainnet.g.alchemy.com/v2/{settings.alchemy.api_key}",
                'chain_id': 1,
                'blocks_per_day': 7200,  # ~12 second blocks
                'name': 'ethereum'
            }
        elif network == "base":
            return {
                'alchemy_url': f"https://base-mainnet.g.alchemy.com/v2/{settings.alchemy.api_key}",
                'chain_id': 8453,
                'blocks_per_day': 43200,  # ~2 second blocks
                'name': 'base'
            }
        else:
            raise ValueError(f"Unsupported network: {network}")


# Export commonly used configs for convenience
db_config = settings.database
alchemy_config = settings.alchemy
analysis_config = settings.analysis
monitor_config = settings.monitor
telegram_config = settings.telegram
auth_config = settings.auth  