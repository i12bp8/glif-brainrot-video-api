"""
Main application module
"""
import os
import logging
import multiprocessing
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
import uvicorn

from app.core.config import settings
from app.api.endpoints import router
from app.utils.cleanup import cleanup_service


# Configure logging with a more detailed format for better debugging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

# Disable uvicorn access logs
uvicorn_logger = logging.getLogger("uvicorn.access")
uvicorn_logger.setLevel(logging.WARNING)

# Setup app logger
logger = logging.getLogger("app")
logger.setLevel(logging.INFO)

# Create application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Brainrot video generator API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
if os.path.exists(settings.PROCESSED_VIDEOS_DIR):
    app.mount(
        "/videos",
        StaticFiles(directory=str(settings.PROCESSED_VIDEOS_DIR)),
        name="videos",
    )

# Include API routes
app.include_router(router, prefix=settings.API_V1_STR)


@app.on_event("startup")
async def startup_event():
    """Run startup tasks"""
    # Only log startup once per worker
    if int(os.getenv("WORKER_ID", "0")) == 0:
        logger.info(f"Starting {settings.PROJECT_NAME}")
        logger.info(f"Using {settings.FFMPEG_THREADS} threads for FFmpeg")
        logger.info(f"Using {settings.WHISPER_THREADS} threads for Whisper")
        logger.info(f"Using {settings.WHISPER_MODEL} model for audio transcription")
    
    # Create required directories
    settings.setup()
    
    # Clean all temp files on startup
    cleanup_service.cleanup_all_temp_files()
    
    # Start cleanup service
    cleanup_service.start()


@app.on_event("shutdown")
async def shutdown_event():
    """Run shutdown tasks"""
    logger.info("Shutting down")
    cleanup_service.stop()


@app.get("/health", include_in_schema=False)
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "version": "1.0.0"
    }


@app.get("/", include_in_schema=False)
async def index():
    """Redirect to API documentation"""
    html_content = """
    <!DOCTYPE html>
    <html>
        <head>
            <title>Brainrot Generator API</title>
            <meta http-equiv="refresh" content="0; url=/api/docs" />
        </head>
        <body>
            <p>Redirecting to <a href="/api/docs">API documentation</a>...</p>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8000,
        workers=int(os.getenv("WORKERS", "1")),
        log_level="info"
    ) 