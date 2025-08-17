from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn
import logging
from datetime import datetime

# Import your existing config
from config.settings import settings, flask_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    # Startup
    logger.info("🚀 FastAPI Crypto Tracker starting...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Supported networks: {[net.value for net in settings.monitor.supported_networks]}")
    
    yield
    
    # Shutdown
    logger.info("🛑 FastAPI Crypto Tracker shutting down...")

# Create FastAPI app
app = FastAPI(
    title="Crypto Alpha Tracker API",
    description="Advanced cryptocurrency trading analysis with real-time monitoring",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"] if settings.environment == 'development' else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Basic health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "environment": settings.environment
    }

from api.routes.analysis import router as analysis_router
from api.routes.status import router as status_router
from api.routes.cache import router as cache_router

app.include_router(analysis_router, prefix="/api")
app.include_router(status_router, prefix="/api")
app.include_router(cache_router, prefix="/api")

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.environment == 'development' else "An error occurred"
        }
    )

if __name__ == "__main__":
    uvicorn.run(
        "main_fastapi:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )