"""
Configuration module for the application
"""
import os
import multiprocessing
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Application settings."""
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Brainrot Generator"
    
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    BACKGROUND_DIR: Path = BASE_DIR / "background"
    MUSIC_DIR: Path = BASE_DIR / "music"
    SOUNDS_DIR: Path = BASE_DIR / "Sounds"
    PROCESSED_VIDEOS_DIR: Path = BASE_DIR / "processed_videos"
    
    # Video configuration
    MAX_CONCURRENT_VIDEOS: int = int(os.getenv("MAX_CONCURRENT_VIDEOS", "0")) or multiprocessing.cpu_count()
    VIDEO_RETENTION_MINUTES: int = int(os.getenv("VIDEO_RETENTION_MINUTES", "1440"))  # Default to 24 hours instead of 60 minutes
    
    # Optimized defaults - using logical CPU count for better scaling
    DEFAULT_THREADS: int = max(2, multiprocessing.cpu_count())
    
    # Whisper configuration
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")
    WHISPER_THREADS: int = int(os.getenv("WHISPER_THREADS", "0")) or DEFAULT_THREADS
    
    # Performance
    WORKERS: str = os.getenv("WORKERS", "auto")
    
    # FFmpeg settings - use all available cores
    FFMPEG_THREADS: int = int(os.getenv("FFMPEG_THREADS", "0")) or DEFAULT_THREADS
    
    # Video quality settings
    VIDEO_CRF: int = int(os.getenv("VIDEO_CRF", "26"))  # Lower is better quality, range 0-51
    VIDEO_PRESET: str = os.getenv("VIDEO_PRESET", "ultrafast")  # Options: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
    AUDIO_BITRATE: str = os.getenv("AUDIO_BITRATE", "192k")
    
    # Cache settings
    MAX_CACHE_SIZE: int = int(os.getenv("MAX_CACHE_SIZE", "100"))  # Max number of items in caches
    
    def setup(self):
        """Create necessary directories if they don't exist."""
        os.makedirs(self.PROCESSED_VIDEOS_DIR, exist_ok=True)
        os.makedirs(self.PROCESSED_VIDEOS_DIR / "temp", exist_ok=True)
        
        # Setup performance optimizations
        os.environ["OMP_NUM_THREADS"] = str(self.DEFAULT_THREADS)
        os.environ["MKL_NUM_THREADS"] = str(self.DEFAULT_THREADS)
        os.environ["OPENBLAS_NUM_THREADS"] = str(self.DEFAULT_THREADS)


settings = Settings()
settings.setup() 