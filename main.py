from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import logging
from datetime import datetime
import os

# Import your existing config
from config.settings import settings, flask_config
from services.cache.cache_service import startup_cache_service, shutdown_cache_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan with cache service"""
    # Startup
    logger.info("🚀 FastAPI Crypto Tracker starting...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Supported networks: {[net.value for net in settings.monitor.supported_networks]}")
    
    # Initialize cache service
    try:
        await startup_cache_service()
        logger.info("✅ Cache service initialized")
    except Exception as e:
        logger.error(f"❌ Cache service initialization failed: {e}")
        # Continue without cache - it's not critical for startup
    
    yield
    
    # Shutdown
    logger.info("🛑 FastAPI Crypto Tracker shutting down...")
    try:
        await shutdown_cache_service()
        logger.info("✅ Cache service shutdown complete")
    except Exception as e:
        logger.error(f"❌ Cache service shutdown failed: {e}")

# Create FastAPI app with integrated cache lifecycle
app = FastAPI(
    title="Crypto Alpha Tracker API",
    description="Advanced cryptocurrency trading analysis with real-time monitoring and intelligent caching",
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

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"✅ Static files mounted from: {static_dir}")
else:
    logger.warning(f"⚠️ Static directory not found: {static_dir}")

# Enhanced health check with cache info
@app.get("/health")
async def health_check():
    """Enhanced health check with cache status"""
    try:
        from services.cache.cache_service import get_cache_service
        cache_service = get_cache_service()
        cache_status = await cache_service.get_status()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "environment": settings.environment,
            "cache": {
                "enabled": True,
                "entries": cache_status.get("cache_entries", 0),
                "orjson": cache_status.get("orjson_available", False)
            }
        }
    except Exception as e:
        # Return basic health if cache fails
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0", 
            "environment": settings.environment,
            "cache": {
                "enabled": False,
                "error": str(e)
            }
        }

# API routes with updated imports
from api.routes.analysis import router as analysis_router
from api.routes.status import router as status_router
from api.routes.cache import router as cache_router
from api.routes.frontend import router as frontend_router
from api.routes.monitoring import router as monitoring_router
from api.routes.token import router as token_router 

# Include routers
app.include_router(analysis_router, prefix="/api")
app.include_router(status_router, prefix="/api")
app.include_router(cache_router, prefix="/api")  # Now uses FastAPI-native cache
app.include_router(frontend_router)
app.include_router(monitoring_router, prefix="/api") 
app.include_router(token_router, prefix="/api") 

# Cache-aware global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global exception: {exc}", exc_info=True)
    
    # Try to log cache status for debugging
    try:
        from services.cache.cache_service import get_cache_service
        cache_service = get_cache_service()
        cache_status = await cache_service.get_status()
        logger.error(f"Cache status during error: {cache_status.get('cache_entries', 0)} entries")
    except:
        pass  # Don't let cache debugging cause more errors
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.environment == 'development' else "An error occurred",
            "timestamp": datetime.now().isoformat()
        }
    )

# Development route to test cache functionality
if settings.environment == 'development':
    @app.get("/dev/cache-test")
    async def test_cache():
        """Development endpoint to test cache functionality"""
        try:
            from services.cache.cache_service import get_cache_service
            cache_service = get_cache_service()
            
            # Test cache operations
            test_data = {
                "test": "data",
                "timestamp": datetime.now().isoformat(),
                "value": 12345
            }
            
            # Set test data
            await cache_service.set("test_key", test_data, 60, "test", "development")
            
            # Get test data
            retrieved = await cache_service.get("test_key")
            
            # Get status
            status = await cache_service.get_status()
            
            return {
                "cache_test": "passed",
                "set_data": test_data,
                "retrieved_data": retrieved,
                "data_matches": test_data == retrieved,
                "cache_status": status
            }
            
        except Exception as e:
            return {
                "cache_test": "failed",
                "error": str(e)
            }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )