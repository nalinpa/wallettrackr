from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal
from datetime import datetime

class TokenAnalysis(BaseModel):
    rank: int
    token: str
    alpha_score: float = Field(..., description="Alpha discovery score")
    wallet_count: int
    total_eth_spent: float
    platforms: List[str]
    contract_address: str
    avg_wallet_score: float
    sophistication_score: Optional[float] = None
    is_base_native: Optional[bool] = None

class Web3EnhancedData(BaseModel):
    total_transactions_analyzed: int
    sophisticated_transactions: int
    method_distribution: Dict[str, int]
    avg_sophistication: float
    gas_efficiency_avg: float

class BuyAnalysisResponse(BaseModel):
    status: str = "success"
    network: str
    analysis_type: str = "buy"
    total_purchases: int
    unique_tokens: int
    total_eth_spent: float
    total_usd_spent: float
    top_tokens: List[TokenAnalysis]
    platform_summary: Dict[str, int]
    web3_analysis: Optional[Web3EnhancedData] = None
    web3_enhanced: bool = False
    orjson_enabled: bool = True
    analysis_time_seconds: float
    last_updated: datetime

class SellAnalysisResponse(BaseModel):
    status: str = "success"
    network: str
    analysis_type: str = "sell"
    total_sells: int
    unique_tokens: int
    total_estimated_eth: float
    top_tokens: List[TokenAnalysis]
    method_summary: Dict[str, int]
    web3_analysis: Optional[Web3EnhancedData] = None
    web3_enhanced: bool = False
    orjson_enabled: bool = True
    analysis_time_seconds: float
    last_updated: datetime

class ProgressUpdate(BaseModel):
    type: Literal["progress", "results", "complete", "error"]
    processed: Optional[int] = None
    total: Optional[int] = None
    percentage: Optional[int] = None
    wallet_address: Optional[str] = None
    purchases_found: Optional[int] = None
    message: Optional[str] = None
    data: Optional[Dict] = None
    error: Optional[str] = None

class ApiStatus(BaseModel):
    status: str
    environment: str
    cached_data: Dict
    last_updated: Optional[str]
    supported_networks: List[str]
    web3_status: Dict
    orjson_status: Dict
    endpoints: List[str]