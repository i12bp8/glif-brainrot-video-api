"""
Utilities for cleaning up resources
"""
import os
import time
import asyncio
import threading
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Set
from concurrent.futures import ThreadPoolExecutor
import shutil

from app.core.config import settings

# Setup logging
logger = logging.getLogger(__name__)

class CleanupService:
    """Service to clean up old videos after a specified retention period"""
    
    def __init__(self):
        self.processed_videos: Dict[str, datetime] = {}
        self.running = False
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=2)
    
    def register_video(self, video_path: Path):
        """
        Register a video for cleanup after the retention period.
        
        Args:
            video_path: Path to the video file
        """
        with self.lock:
            self.processed_videos[str(video_path)] = datetime.now()
    
    def start(self):
        """Start the cleanup service"""
        if not self.running:
            self.running = True
            threading.Thread(target=self._cleanup_loop, daemon=True, name="CleanupThread").start()
            logger.info("Cleanup service started")
    
    def stop(self):
        """Stop the cleanup service"""
        self.running = False
        logger.info("Cleanup service stopped")
    
    def _cleanup_loop(self):
        """Loop to clean up old videos"""
        while self.running:
            try:
                self._cleanup_old_videos()
                # Also clean up any orphaned temp files periodically
                self._cleanup_orphaned_temp_files()
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
            
            # Sleep for 1 minute
            time.sleep(60)
    
    def _cleanup_old_videos(self):
        """Clean up videos older than the retention period"""
        now = datetime.now()
        retention_period = timedelta(minutes=settings.VIDEO_RETENTION_MINUTES)
        videos_to_remove = []
        
        with self.lock:
            # Find videos that exceed the retention period
            for path, created_time in self.processed_videos.items():
                if now - created_time > retention_period:
                    videos_to_remove.append(path)
            
            # Remove videos from the tracking dictionary
            for path in videos_to_remove:
                del self.processed_videos[path]
        
        # Delete the files in parallel
        if videos_to_remove:
            logger.info(f"Cleaning up {len(videos_to_remove)} old videos")
            list(self.executor.map(self._safe_remove_file, videos_to_remove))
    
    def _cleanup_orphaned_temp_files(self):
        """Clean up temporary files that are older than 1 hour"""
        now = datetime.now()
        temp_cutoff = timedelta(hours=1)  # Reduced from 2 hours to 1 hour
        
        # Get all temp files in a list first to avoid modification during iteration
        temp_files = []
        
        # Check all files in the processed_videos directory with temp in the name
        for file_pattern in ["*temp*", "*temp_background_*"]:
            temp_files.extend(settings.PROCESSED_VIDEOS_DIR.glob(file_pattern))
        
        # Process each file
        for file_path in temp_files:
            try:
                # Skip if already deleted
                if not file_path.exists():
                    continue
                    
                # Skip directories - we'll handle them separately
                if file_path.is_dir():
                    continue
                    
                # Get file stats
                stat = file_path.stat()
                # Convert to datetime
                file_time = datetime.fromtimestamp(stat.st_mtime)
                
                # If file is older than cutoff, delete it
                if now - file_time > temp_cutoff:
                    # Special handling for temp background files to make sure they're removed
                    if "temp_background_" in str(file_path):
                        logger.info(f"Removing orphaned background file: {file_path}")
                        self._safe_remove_file(str(file_path))
                    else:
                        self._safe_remove_file(str(file_path))
            except Exception as e:
                logger.warning(f"Error checking temp file {file_path}: {e}")
        
        # Also check for and remove empty temp directories
        try:
            for dir_path in settings.PROCESSED_VIDEOS_DIR.glob("temp_*"):
                if dir_path.is_dir():
                    # Check if directory is older than cutoff
                    dir_stat = dir_path.stat()
                    dir_time = datetime.fromtimestamp(dir_stat.st_mtime)
                    if now - dir_time > temp_cutoff:
                        self._safe_remove_file(str(dir_path))
        except Exception as e:
            logger.warning(f"Error cleaning up temp directories: {e}")
    
    def _safe_remove_file(self, path: str):
        """Safely remove a file with error handling"""
        try:
            path_obj = Path(path)
            
            # Check if this is a directory
            if path_obj.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                logger.debug(f"Removed directory: {path}")
            else:
                os.remove(path)
                logger.debug(f"Removed file: {path}")
                
        except FileNotFoundError:
            # File already gone, just log it
            logger.debug(f"File not found during cleanup: {path}")
        except PermissionError:
            # Can't delete now, try again later
            logger.warning(f"Permission error deleting file: {path}")
        except Exception as e:
            # Log any other errors
            logger.error(f"Error deleting file {path}: {e}")
    
    def cleanup_all_temp_files(self):
        """Clean up all temporary files in the processed_videos directory"""
        logger.info("Cleaning up all temporary files")
        
        # First try to remove the entire temp directory
        temp_dir = settings.PROCESSED_VIDEOS_DIR / "temp"
        if temp_dir.exists():
            try:
                # Recursively remove the directory and recreate it
                shutil.rmtree(str(temp_dir), ignore_errors=True)
                temp_dir.mkdir(exist_ok=True)
                logger.info("Cleaned temp directory")
            except Exception as e:
                logger.warning(f"Error cleaning temp directory: {e}")
                # Fall back to individual file removal
                self._cleanup_temp_files_individually(temp_dir)
        
        # Explicitly clean up all background temp files
        background_files = list(settings.PROCESSED_VIDEOS_DIR.glob("temp_background_*"))
        if background_files:
            logger.info(f"Cleaning {len(background_files)} background temp files")
            list(self.executor.map(self._safe_remove_file, [str(f) for f in background_files]))
        
        # Also clean up any temp files in the main directory
        self._cleanup_temp_files_individually(settings.PROCESSED_VIDEOS_DIR)
    
    def _cleanup_temp_files_individually(self, directory: Path):
        """Clean up individual temporary files in a directory"""
        # Only get regular files, not directories
        temp_files = [f for f in directory.glob("*temp*") if f.is_file()]
        if temp_files:
            logger.info(f"Cleaning {len(temp_files)} individual temp files in {directory}")
            list(self.executor.map(self._safe_remove_file, [str(f) for f in temp_files]))
    
    def __del__(self):
        """Ensure executor is shutdown on deletion"""
        self.executor.shutdown(wait=False)


# Create a singleton instance
cleanup_service = CleanupService() 