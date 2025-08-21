from fastapi import APIRouter, Depends, HTTPException, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
import logging
from datetime import datetime
try:
    from api.auth import require_auth, get_template_context
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    def require_auth(): return True
    def get_template_context(request): return {"request": request}

from services.blockchain.wallet_manager import WalletManager
from services.database.database_client import DatabaseClient

logger = logging.getLogger(__name__)
router = APIRouter(tags=["wallet_management"])
templates = Jinja2Templates(directory="templates")

class WalletSubmissionRequest(BaseModel):
    address: str = Field(..., description="Ethereum wallet address")
    rating: int = Field(..., ge=0, lt=1000, description="Smart money rating (0-999)")
    tag: Optional[str] = Field(None, max_length=20, description="Optional tag")
    network: str = Field("ethereum", description="Blockchain network")
    
    @field_validator('address')
    @classmethod
    def validate_address(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Address is required")
        return v.strip()
    
    @field_validator('rating')
    @classmethod
    def validate_rating(cls, v: int) -> int:
        if v < 0 or v >= 1000:
            raise ValueError("Rating must be between 0 and 999")
        return v
    
    @field_validator('tag')
    @classmethod
    def validate_tag(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip()
            if len(v) > 20:
                raise ValueError("Tag must be 20 characters or less")
            # Check format (letters, numbers, underscore, hyphen only)
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', v):
                raise ValueError("Tag can only contain letters, numbers, underscore, and hyphen")
        return v if v else None
    
    @field_validator('network')
    @classmethod
    def validate_network(cls, v: str) -> str:
        if v not in ["ethereum", "base"]:
            raise ValueError("Network must be 'ethereum' or 'base'")
        return v

class WalletSearchResponse(BaseModel):
    wallets: List[dict] = Field(..., description="List of wallet matches")
    total: int = Field(..., description="Total number of results")

class WalletStatsResponse(BaseModel):
    total_wallets: int = Field(..., description="Total wallets in database")
    web_submissions: int = Field(..., description="Wallets added via web form")
    today_additions: int = Field(..., description="Wallets added today")
    high_rating_count: int = Field(..., description="Wallets with rating 300+")
    average_score: float = Field(..., description="Average wallet score")
    network_breakdown: dict = Field(..., description="Wallets per network")

class WalletUpdateRequest(BaseModel):
    rating: Optional[int] = Field(None, ge=0, lt=1000, description="New rating")
    tag: Optional[str] = Field(None, max_length=20, description="New tag")
    network: Optional[str] = Field(None, description="New network")
    
    @field_validator('rating')
    @classmethod
    def validate_rating(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 0 or v >= 1000):
            raise ValueError("Rating must be between 0 and 999")
        return v
    
    @field_validator('tag')
    @classmethod
    def validate_tag(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip()
            if len(v) > 20:
                raise ValueError("Tag must be 20 characters or less")
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', v):
                raise ValueError("Tag can only contain letters, numbers, underscore, and hyphen")
        return v if v else None
    
    @field_validator('network')
    @classmethod
    def validate_network(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ["ethereum", "base"]:
            raise ValueError("Network must be 'ethereum' or 'base'")
        return v

class WalletSearchResponse(BaseModel):
    wallets: List[dict]
    total: int


@router.post("/wallet/add")
async def add_wallet_api(
    wallet_data: WalletSubmissionRequest,
    auth: bool = Depends(require_auth) if AUTH_AVAILABLE else None
):
    """Add a new wallet directly to main smart_wallets table"""
    
    try:
        async with DatabaseClient() as db:
            wallet_manager = WalletManager(db.db)
            
            result = await wallet_manager.submit_wallet(
                address=wallet_data.address,
                rating=wallet_data.rating,
                tag=wallet_data.tag,
                network=wallet_data.network,
                created_by="api_user"
            )
            
            if result["success"]:
                return {
                    "status": "success",
                    "message": result["message"],
                    "wallet": result["wallet"],
                    "warnings": result.get("warnings", [])
                }
            else:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "status": "error",
                        "errors": result["errors"],
                        "warnings": result.get("warnings", [])
                    }
                )
                
    except Exception as e:
        logger.error(f"❌ Error in add_wallet_api: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
@router.post("/wallet/add-form")
async def add_wallet_form(
    request: Request,
    address: str = Form(...),
    rating: int = Form(...),
    tag: Optional[str] = Form(None),
    network: str = Form("ethereum"),
    auth: bool = Depends(require_auth) if AUTH_AVAILABLE else None
):
    """Add wallet via HTML form submission"""
    
    try:
        # Validate form data
        wallet_data = WalletSubmissionRequest(
            address=address,
            rating=rating,
            tag=tag,
            network=network
        )
        
        async with DatabaseClient() as db:
            wallet_manager = WalletManager(db.db)
            
            result = await wallet_manager.submit_wallet(
                address=wallet_data.address,
                rating=wallet_data.rating,
                tag=wallet_data.tag,
                network=wallet_data.network,
                created_by="web_form"
            )
            
            context = get_template_context(request) if AUTH_AVAILABLE else {"request": request}
            context.update({
                "title": "Add Smart Wallet",
                "page": "add_wallet",
                "result": result,
                "form_data": {
                    "address": address,
                    "rating": rating,
                    "tag": tag,
                    "network": network
                }
            })
            
            return templates.TemplateResponse("add_wallet.html", context)
            
    except ValueError as e:
        # Validation error
        context = get_template_context(request) if AUTH_AVAILABLE else {"request": request}
        context.update({
            "title": "Add Smart Wallet",
            "page": "add_wallet",
            "result": {
                "success": False,
                "errors": [str(e)],
                "warnings": []
            },
            "form_data": {
                "address": address,
                "rating": rating,
                "tag": tag,
                "network": network
            }
        })
        
        return templates.TemplateResponse("add_wallet.html", context)
        
    except Exception as e:
        logger.error(f"❌ Error in add_wallet_form: {e}")
        context = get_template_context(request) if AUTH_AVAILABLE else {"request": request}
        context.update({
            "title": "Add Smart Wallet",
            "page": "add_wallet",
            "result": {
                "success": False,
                "errors": [f"System error: {str(e)}"],
                "warnings": []
            },
            "form_data": {
                "address": address,
                "rating": rating, 
                "tag": tag,
                "network": network
            }
        })
        
        return templates.TemplateResponse("add_wallet.html", context)

@router.get("/wallet/recent")
async def get_recent_wallets(
    limit: int = Query(20, ge=1, le=100),
    all_sources: bool = Query(False, description="Include all sources or just web submissions"),
    auth: bool = Depends(require_auth) if AUTH_AVAILABLE else None
):
    """Get recent wallets from main smart_wallets table"""
    
    try:
        async with DatabaseClient() as db:
            wallet_manager = WalletManager(db.db)
            
            if all_sources:
                wallets = await wallet_manager.get_all_recent_wallets(limit)
            else:
                wallets = await wallet_manager.get_recent_wallets(limit)
            
            return {
                "status": "success",
                "wallets": wallets,
                "total": len(wallets),
                "source": "main_table"
            }
            
    except Exception as e:
        logger.error(f"❌ Error fetching recent wallets: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/wallet/detailed-stats")
async def get_detailed_wallet_stats(
    auth: bool = Depends(require_auth) if AUTH_AVAILABLE else None
):
    """Get detailed wallet statistics for manage page"""
    
    try:
        async with DatabaseClient() as db:
            wallet_manager = WalletManager(db.db)
            stats = await wallet_manager.get_detailed_stats()
            
            return {
                "status": "success",
                "stats": stats,
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"❌ Error fetching detailed wallet stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/wallet/stats")
async def get_wallet_stats():
    """Get wallet statistics - working version"""
    try:
        async with DatabaseClient() as db:
            # Get total count (we know this works)
            total_count = await db.db.smart_wallets.count_documents({})
            
            # Get web submissions count
            web_submissions = await db.db.smart_wallets.count_documents({"source": "web_submission"})
            
            # Get today's additions
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_count = await db.db.smart_wallets.count_documents({
                "created_at": {"$gte": today_start}
            })
            
            # Get average score
            try:
                pipeline = [{"$group": {"_id": None, "avg_score": {"$avg": "$score"}}}]
                avg_result = await db.db.smart_wallets.aggregate(pipeline).to_list(1)
                avg_score = avg_result[0]["avg_score"] if avg_result else 0
            except:
                avg_score = 0
            
            return {
                "status": "success",
                "stats": {
                    "total_wallets": total_count,
                    "web_submissions": web_submissions,
                    "today_additions": today_count,
                    "average_score": round(avg_score, 1) if avg_score else 0
                },
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"❌ Error getting wallet stats: {e}")
        return {
            "status": "error",
            "error": str(e),
            "stats": {
                "total_wallets": 0,
                "web_submissions": 0,
                "today_additions": 0,
                "average_score": 0
            }
        }
        
@router.put("/wallet/{address}")
async def update_wallet(
    address: str,
    updates: dict,
    auth: bool = Depends(require_auth) if AUTH_AVAILABLE else None
):
    """Update an existing wallet"""
    
    try:
        async with DatabaseClient() as db:
            wallet_manager = WalletManager(db.db)
            result = await wallet_manager.update_wallet(address, updates)
            
            if result["success"]:
                return {
                    "status": "success",
                    "message": result["message"]
                }
            else:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "status": "error",
                        "errors": result["errors"]
                    }
                )
                
    except Exception as e:
        logger.error(f"❌ Error updating wallet: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/wallet/{address}")
async def delete_wallet(
    address: str,
    auth: bool = Depends(require_auth) if AUTH_AVAILABLE else None
):
    """Delete a wallet from main table"""
    
    try:
        async with DatabaseClient() as db:
            wallet_manager = WalletManager(db.db)
            result = await wallet_manager.delete_wallet(address)
            
            if result["success"]:
                return {
                    "status": "success",
                    "message": result["message"]
                }
            else:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "status": "error",
                        "errors": result["errors"]
                    }
                )
                
    except Exception as e:
        logger.error(f"❌ Error deleting wallet: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/wallet/test-count")
async def test_wallet_count():
    """Simple test to get wallet count"""
    try:
        async with DatabaseClient() as db:
            count = await db.db.smart_wallets.count_documents({})
            return {
                "status": "success",
                "total_count": count,
                "collection_name": "smart_wallets",
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        return {
            "status": "error", 
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }