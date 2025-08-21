from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from datetime import datetime

@dataclass
class Purchase:
    """Immutable purchase data"""
    transaction_hash: str
    token_bought: str
    amount_received: float
    eth_spent: float
    wallet_address: str
    platform: str
    block_number: int
    timestamp: datetime
    sophistication_score: Optional[float] = None
    web3_analysis: Optional[Dict] = None

@dataclass
class WalletData:
    """Wallet information"""
    address: str
    score: float
    network: str
    web3_analysis: Optional[Dict] = None

@dataclass
class WalletSubmission:
    """Wallet submission data"""
    address: str
    rating: int
    tag: Optional[str] = None
    network: str = "ethereum"
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None
    status: str = "pending"  # pending, approved, rejected
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

@dataclass
class WalletValidationResult:
    """Wallet validation result"""
    is_valid: bool
    errors: list
    warnings: list
    normalized_address: str = ""
    
@dataclass  
class AnalysisResult:
    """Analysis result container"""
    network: str
    analysis_type: str
    total_transactions: int
    unique_tokens: int
    total_eth_value: float
    ranked_tokens: List[tuple]
    performance_metrics: Dict[str, Any]
    web3_enhanced: bool = False
    
    def dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'network': self.network,
            'analysis_type': self.analysis_type,
            'total_transactions': self.total_transactions,
            'unique_tokens': self.unique_tokens,
            'total_eth_value': self.total_eth_value,
            'ranked_tokens': self.ranked_tokens,
            'performance_metrics': self.performance_metrics,
            'web3_enhanced': self.web3_enhanced
        }