import re
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from core.data.models import WalletSubmission, WalletValidationResult

logger = logging.getLogger(__name__)

class WalletManager:
    """Service for managing wallet submissions directly to main smart_wallets table"""
    
    def __init__(self, database):
        self.db = database
        self.wallets_collection = database.smart_wallets  # Main table only
        
        # Validation patterns
        self.ethereum_address_pattern = re.compile(r'^0x[a-fA-F0-9]{40}$')
        self.tag_pattern = re.compile(r'^[a-zA-Z0-9_-]{1,20}$')
        
        # Common invalid addresses to reject
        self.invalid_addresses = {
            '0x0000000000000000000000000000000000000000',  # Zero address
            '0xdead000000000000000000000000000000000000',  # Dead address
            '0x000000000000000000000000000000000000dead',  # Dead address variant
        }
    
    async def validate_wallet_submission(self, address: str, rating: int, tag: Optional[str] = None) -> WalletValidationResult:
        """Comprehensive wallet validation"""
        errors = []
        warnings = []
        normalized_address = ""
        
        # 1. Validate address format
        if not address:
            errors.append("Wallet address is required")
        else:
            # Clean and normalize address
            cleaned_address = address.strip()
            if not cleaned_address.startswith('0x'):
                cleaned_address = '0x' + cleaned_address
            
            normalized_address = cleaned_address.lower()
            
            # Check format
            if not self.ethereum_address_pattern.match(cleaned_address):
                errors.append("Invalid Ethereum address format (must be 42 characters starting with 0x)")
            
            # Check for invalid/burn addresses
            if normalized_address in self.invalid_addresses:
                errors.append("Cannot add burn or zero addresses")
            
            # Check for existing wallet
            existing = await self.wallets_collection.find_one({"address": normalized_address})
            if existing:
                errors.append(f"Wallet already exists with rating {existing.get('score', 'unknown')}")
        
        # 2. Validate rating
        if rating is None:
            errors.append("Rating is required")
        else:
            try:
                rating_int = int(rating)
                if rating_int < 0:
                    errors.append("Rating cannot be negative")
                elif rating_int >= 1000:
                    errors.append("Rating must be less than 1000")
                elif rating_int > 500:
                    warnings.append("High rating detected - please verify this is a premium wallet")
            except (ValueError, TypeError):
                errors.append("Rating must be a valid number")
        
        # 3. Validate tag (optional)
        if tag:
            tag = tag.strip()
            if not self.tag_pattern.match(tag):
                errors.append("Tag must be 1-20 characters (letters, numbers, underscore, hyphen only)")
            
            # Check for duplicate tags
            existing_tag = await self.wallets_collection.find_one({"tag": tag})
            if existing_tag:
                warnings.append(f"Tag '{tag}' is already used by another wallet")
        
        return WalletValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            normalized_address=normalized_address
        )
    
    async def submit_wallet(self, address: str, rating: int, tag: Optional[str] = None, 
                           network: str = "ethereum", created_by: str = "web_form") -> Dict:
        """Add wallet directly to main smart_wallets table"""
        
        # Validate submission
        validation = await self.validate_wallet_submission(address, rating, tag)
        
        if not validation.is_valid:
            return {
                "success": False,
                "errors": validation.errors,
                "warnings": validation.warnings
            }
        
        try:
            # Create wallet document for main table
            wallet_doc = {
                "address": validation.normalized_address,
                "score": int(rating),  # Main field name is 'score' not 'rating'
                "network": network,
                "created_at": datetime.now(),
                "imported_at": datetime.now(),
                "source": "web_submission",
                "tag": tag.strip() if tag else None,
                "active": True,
                "created_by": created_by,
                "original_line": None,  # For compatibility with file imports
                "verified": True  # Web submissions are considered verified
            }
            
            # Insert directly into main wallets collection
            result = await self.wallets_collection.insert_one(wallet_doc)
            
            logger.info(f"✅ New wallet added to main table: {validation.normalized_address} (score: {rating})")
            
            return {
                "success": True,
                "message": "Wallet added successfully to smart wallets database!",
                "wallet": {
                    "address": validation.normalized_address,
                    "rating": int(rating),  # Return as 'rating' for display
                    "score": int(rating),   # Also include 'score' for consistency
                    "tag": tag.strip() if tag else None,
                    "network": network,
                    "id": str(result.inserted_id)
                },
                "warnings": validation.warnings
            }
            
        except Exception as e:
            logger.error(f"❌ Error adding wallet to main table: {e}")
            return {
                "success": False,
                "errors": [f"Database error: {str(e)}"],
                "warnings": []
            }
    
    async def get_recent_wallets(self, limit: int = 20) -> List[Dict]:
        """Get recently added wallets from main table"""
        try:
            cursor = self.wallets_collection.find(
                {"source": "web_submission"},  # Only web submissions
                {
                    "address": 1,
                    "score": 1,
                    "tag": 1,
                    "network": 1,
                    "created_at": 1,
                    "created_by": 1,
                    "_id": 0
                }
            ).sort("created_at", -1).limit(limit)
            
            wallets = await cursor.to_list(length=limit)
            
            # Convert for display (score -> rating for frontend)
            for wallet in wallets:
                wallet["rating"] = wallet.get("score", 0)  # Add rating field for frontend
                if isinstance(wallet.get("created_at"), datetime):
                    wallet["created_at"] = wallet["created_at"].isoformat()
            
            return wallets
        except Exception as e:
            logger.error(f"❌ Error fetching recent wallets: {e}")
            return []
    
    async def get_all_recent_wallets(self, limit: int = 100) -> List[Dict]:
        """Get all recently added wallets (including file imports) for stats"""
        try:
            cursor = self.wallets_collection.find(
                {},
                {
                    "address": 1,
                    "score": 1,
                    "tag": 1,
                    "network": 1,
                    "created_at": 1,
                    "source": 1,
                    "_id": 0
                }
            ).sort("created_at", -1).limit(limit)
            
            wallets = await cursor.to_list(length=limit)
            
            # Convert for display
            for wallet in wallets:
                wallet["rating"] = wallet.get("score", 0)
                if isinstance(wallet.get("created_at"), datetime):
                    wallet["created_at"] = wallet["created_at"].isoformat()
            
            return wallets
        except Exception as e:
            logger.error(f"❌ Error fetching all recent wallets: {e}")
            return []
    
    async def search_wallets(self, query: str, limit: int = 10) -> List[Dict]:
        """Search existing wallets in main table"""
        try:
            # Search by address or tag
            search_filter = {
                "$or": [
                    {"address": {"$regex": query, "$options": "i"}},
                    {"tag": {"$regex": query, "$options": "i"}} if query else {}
                ]
            }
            
            cursor = self.wallets_collection.find(
                search_filter,
                {"address": 1, "score": 1, "tag": 1, "network": 1, "_id": 0}
            ).limit(limit)
            
            wallets = await cursor.to_list(length=limit)
            
            # Convert score to rating for frontend consistency
            for wallet in wallets:
                wallet["rating"] = wallet.get("score", 0)
            
            return wallets
        except Exception as e:
            logger.error(f"❌ Error searching wallets: {e}")
            return []
    
    async def get_wallet_stats(self) -> Dict:
        """Get wallet statistics from main table"""
        try:
            # Get total count
            total_count = await self.wallets_collection.count_documents({})
            
            # Get web submission count
            web_submissions = await self.wallets_collection.count_documents({"source": "web_submission"})
            
            # Get today's additions
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_count = await self.wallets_collection.count_documents({
                "created_at": {"$gte": today_start}
            })
            
            # Get high rating count (300+)
            high_rating_count = await self.wallets_collection.count_documents({"score": {"$gte": 300}})
            
            # Get average rating
            pipeline = [
                {"$group": {"_id": None, "avg_score": {"$avg": "$score"}}}
            ]
            avg_result = await self.wallets_collection.aggregate(pipeline).to_list(1)
            avg_score = avg_result[0]["avg_score"] if avg_result else 0
            
            # Get network breakdown
            network_pipeline = [
                {"$group": {"_id": "$network", "count": {"$sum": 1}}}
            ]
            network_results = await self.wallets_collection.aggregate(network_pipeline).to_list(10)
            network_breakdown = {item["_id"]: item["count"] for item in network_results}
            
            return {
                "total_wallets": total_count,
                "web_submissions": web_submissions,
                "today_additions": today_count,
                "high_rating_count": high_rating_count,
                "average_score": round(avg_score, 1),
                "network_breakdown": network_breakdown
            }
        except Exception as e:
            logger.error(f"❌ Error getting wallet stats: {e}")
            return {
                "total_wallets": 0,
                "web_submissions": 0,
                "today_additions": 0,
                "high_rating_count": 0,
                "average_score": 0,
                "network_breakdown": {}
            }
    
    async def update_wallet(self, address: str, updates: Dict) -> Dict:
        """Update an existing wallet"""
        try:
            normalized_address = address.lower()
            
            # Prepare updates
            update_doc = {"$set": {}}
            
            if "rating" in updates or "score" in updates:
                score = updates.get("rating") or updates.get("score")
                if 0 <= score < 1000:
                    update_doc["$set"]["score"] = int(score)
            
            if "tag" in updates:
                tag = updates["tag"]
                if tag and self.tag_pattern.match(tag.strip()):
                    update_doc["$set"]["tag"] = tag.strip()
                elif not tag:
                    update_doc["$unset"] = {"tag": ""}
            
            if "network" in updates:
                if updates["network"] in ["ethereum", "base"]:
                    update_doc["$set"]["network"] = updates["network"]
            
            # Add update timestamp
            update_doc["$set"]["updated_at"] = datetime.now()
            
            if not update_doc["$set"]:
                return {"success": False, "errors": ["No valid updates provided"]}
            
            result = await self.wallets_collection.update_one(
                {"address": normalized_address},
                update_doc
            )
            
            if result.modified_count > 0:
                return {
                    "success": True,
                    "message": "Wallet updated successfully",
                    "modified": True
                }
            else:
                return {
                    "success": False,
                    "errors": ["Wallet not found or no changes made"]
                }
                
        except Exception as e:
            logger.error(f"❌ Error updating wallet: {e}")
            return {
                "success": False,
                "errors": [f"Update error: {str(e)}"]
            }
    
    async def delete_wallet(self, address: str) -> Dict:
        """Delete a wallet from main table"""
        try:
            normalized_address = address.lower()
            
            result = await self.wallets_collection.delete_one({"address": normalized_address})
            
            if result.deleted_count > 0:
                logger.info(f"✅ Wallet deleted: {normalized_address}")
                return {
                    "success": True,
                    "message": "Wallet deleted successfully"
                }
            else:
                return {
                    "success": False,
                    "errors": ["Wallet not found"]
                }
                
        except Exception as e:
            logger.error(f"❌ Error deleting wallet: {e}")
            return {
                "success": False,
                "errors": [f"Delete error: {str(e)}"]
            }
            
async def get_total_wallet_count(self) -> int:
    """Get total count of all wallets in database"""
    try:
        total_count = await self.wallets_collection.count_documents({})
        return total_count
    except Exception as e:
        logger.error(f"❌ Error getting total wallet count: {e}")
        return 0

async def get_detailed_stats(self) -> Dict:
    """Get detailed wallet statistics for manage page"""
    try:
        # Get total count
        total_count = await self.wallets_collection.count_documents({})
        
        # Get web submission count
        web_submissions = await self.wallets_collection.count_documents({"source": "web_submission"})
        
        # Get file import count
        file_imports = await self.wallets_collection.count_documents({"source": "file_import"})
        
        # Get network breakdown
        network_pipeline = [
            {"$group": {"_id": "$network", "count": {"$sum": 1}}}
        ]
        network_results = await self.wallets_collection.aggregate(network_pipeline).to_list(10)
        network_breakdown = {item["_id"]: item["count"] for item in network_results}
        
        # Get rating distribution
        rating_pipeline = [
            {
                "$bucket": {
                    "groupBy": "$score",
                    "boundaries": [0, 50, 150, 300, 500, 1000],
                    "default": "Other",
                    "output": {"count": {"$sum": 1}}
                }
            }
        ]
        rating_results = await self.wallets_collection.aggregate(rating_pipeline).to_list(10)
        rating_distribution = {str(item["_id"]): item["count"] for item in rating_results}
        
        # Get average rating
        avg_pipeline = [
            {"$group": {"_id": None, "avg_score": {"$avg": "$score"}}}
        ]
        avg_result = await self.wallets_collection.aggregate(avg_pipeline).to_list(1)
        avg_score = avg_result[0]["avg_score"] if avg_result else 0
        
        # Get today's additions
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = await self.wallets_collection.count_documents({
            "created_at": {"$gte": today_start}
        })
        
        return {
            "total_wallets": total_count,
            "web_submissions": web_submissions,
            "file_imports": file_imports,
            "today_additions": today_count,
            "average_score": round(avg_score, 1) if avg_score else 0,
            "network_breakdown": network_breakdown,
            "rating_distribution": rating_distribution
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting detailed stats: {e}")
        return {
            "total_wallets": 0,
            "web_submissions": 0,
            "file_imports": 0,
            "today_additions": 0,
            "average_score": 0,
            "network_breakdown": {},
            "rating_distribution": {}
        }