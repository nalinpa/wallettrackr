from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from api.models.responses import ApiStatus

# Import existing monitor
try:
    from auto_monitor import monitor
    MONITOR_AVAILABLE = True
except ImportError:
    MONITOR_AVAILABLE = False

router = APIRouter(tags=["monitoring"])

@router.get("/status", response_model=Dict[str, Any])
async def get_monitor_status():
    """Get monitoring system status"""
    if not MONITOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Monitor not available")
    
    try:
        status = monitor.get_status()
        return {"status": "success", "data": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/start")
async def start_monitor():
    """Start the monitoring system"""
    if not MONITOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Monitor not available")
    
    try:
        result = monitor.start_monitoring()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop")
async def stop_monitor():
    """Stop the monitoring system"""
    if not MONITOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Monitor not available")
    
    try:
        result = monitor.stop_monitoring()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))