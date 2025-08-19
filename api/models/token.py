from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime

class TokenMetadata(BaseModel):
    symbol: str = Field(..., description="Token symbol")
    name: str = Field(..., description="Token name")
    decimals: int = Field(18, description="Token decimals")
    totalSupply: Optional[str] = Field(None, description="Total supply")

class TokenActivity(BaseModel):
    wallet_count: int = Field(..., description="Number of active wallets")
    total_eth_spent: float = Field(..., description="Total ETH spent on purchases")
    alpha_score: float = Field(..., description="Alpha score")
    platforms: List[str] = Field(default_factory=list, description="Trading platforms")

class SellPressure(BaseModel):
    sell_score: float = Field(..., description="Sell pressure score")
    methods: List[str] = Field(default_factory=list, description="Selling methods")

class PurchaseTransaction(BaseModel):
    wallet: str = Field(..., description="Wallet address")
    wallet_score: int = Field(..., description="Wallet score")
    amount: float = Field(..., description="Token amount purchased")
    eth_spent: float = Field(..., description="ETH spent")
    platform: str = Field(..., description="Trading platform")
    tx_hash: Optional[str] = Field(None, description="Transaction hash")

class DetailedBuyActivity(BaseModel):
    total_purchases: int = Field(..., description="Total number of purchases")
    total_eth_spent: float = Field(..., description="Total ETH spent")
    unique_wallets: int = Field(..., description="Number of unique wallets")
    avg_purchase_size: float = Field(..., description="Average purchase size in ETH")
    platforms: List[str] = Field(default_factory=list, description="Trading platforms")
    recent_transactions: List[Dict] = Field(default_factory=list, description="Recent transactions")

class DetailedSellActivity(BaseModel):
    total_sells: int = Field(..., description="Total number of sells")
    total_eth_received: float = Field(..., description="Total ETH received")
    unique_wallets: int = Field(..., description="Number of unique wallets")
    methods: List[str] = Field(default_factory=list, description="Selling methods")
    recent_transactions: List[Dict] = Field(default_factory=list, description="Recent transactions")

class TokenScores(BaseModel):
    alpha_score: float = Field(..., description="Alpha score")
    sell_pressure_score: float = Field(..., description="Sell pressure score")
    avg_wallet_score: float = Field(..., description="Average wallet score")

class TokenSummary(BaseModel):
    net_activity: str = Field(..., description="Net activity sentiment")
    wallet_sentiment: str = Field(..., description="Wallet sentiment")
    activity_level: str = Field(..., description="Activity level")

class DetailedAnalysis(BaseModel):
    buy_activity: DetailedBuyActivity
    sell_activity: DetailedSellActivity
    scores: TokenScores
    summary: TokenSummary

class TokenAnalysisResponse(BaseModel):
    status: str = Field(default="success", description="Response status")
    network: str = Field(..., description="Blockchain network")
    contract_address: str = Field(..., description="Token contract address")
    token_symbol: str = Field(..., description="Token symbol")
    analysis_period_days: float = Field(..., description="Analysis period in days")
    wallets_analyzed: int = Field(..., description="Number of wallets analyzed")
    analysis_time_seconds: float = Field(..., description="Analysis time in seconds")
    last_updated: datetime = Field(..., description="Last updated timestamp")
    
    # Core data (backward compatible)
    metadata: TokenMetadata
    is_base_native: bool = Field(False, description="Is Base native token")
    activity: TokenActivity
    sell_pressure: SellPressure
    purchases: List[PurchaseTransaction]
    
    # Detailed analysis (new)
    detailed_analysis: DetailedAnalysis

class TokenMetadataResponse(BaseModel):
    status: str = Field(default="success")
    contract_address: str
    network: str
    metadata: TokenMetadata
    last_updated: datetime

class TokenActivitySummaryResponse(BaseModel):
    status: str = Field(default="success")
    contract_address: str
    network: str
    period_days: float
    activity_summary: Dict
    last_updated: datetime