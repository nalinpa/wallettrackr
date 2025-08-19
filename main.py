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

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"✅ Static files mounted from: {static_dir}")
else:
    logger.warning(f"⚠️ Static directory not found: {static_dir}")

# Set up templates
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
if os.path.exists(templates_dir):
    templates = Jinja2Templates(directory=templates_dir)
    logger.info(f"✅ Templates configured from: {templates_dir}")
else:
    logger.warning(f"⚠️ Templates directory not found: {templates_dir}")
    
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
from api.routes.frontend import router as frontend_router
from api.routes.monitoring import router as monitoring_router
from api.routes.token import router as token_router 

app.include_router(analysis_router, prefix="/api")
app.include_router(status_router, prefix="/api")
app.include_router(cache_router, prefix="/api")
app.include_router(frontend_router)
app.include_router(monitoring_router, prefix="/api") 
app.include_router(token_router, prefix="/api") 

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