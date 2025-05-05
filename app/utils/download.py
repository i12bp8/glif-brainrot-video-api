"""
Utilities for downloading assets from URLs
"""
import os
import time
import uuid
from pathlib import Path
from typing import Tuple

import httpx

from app.core.config import settings


async def download_file(url: str, directory: Path, extension: str = None) -> Path:
    """
    Download a file from a URL to a local directory.
    
    Args:
        url: The URL of the file to download
        directory: Directory to save the file
        extension: File extension to use (defaults to original extension)
        
    Returns:
        Path to the downloaded file
    """
    os.makedirs(directory, exist_ok=True)
    
    # Generate a unique filename
    file_id = str(uuid.uuid4())
    
    # If extension is not provided, try to extract it from the URL
    if not extension:
        extension = os.path.splitext(url)[-1]
        if not extension:
            # Default extension based on likely content type
            if "audio" in url.lower():
                extension = ".mp3"
            elif "image" in url.lower():
                extension = ".jpg"
            else:
                extension = ""
    
    # Make sure extension starts with a dot
    if extension and not extension.startswith("."):
        extension = f".{extension}"
        
    filename = f"{file_id}{extension}"
    file_path = directory / filename
    
    # Download the file with timeout and retries
    async with httpx.AsyncClient(timeout=60.0) as client:
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                response = await client.get(url)
                response.raise_for_status()
                
                with open(file_path, "wb") as f:
                    f.write(response.content)
                    
                return file_path
                
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                if attempt < max_retries - 1:
                    # Wait before retrying
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    raise RuntimeError(f"Failed to download file from {url}: {str(e)}")
    
    raise RuntimeError(f"Failed to download file from {url}")


async def download_resources(
    audio_url: str, 
    intro_image_url: str, 
    outro_image_url: str
) -> Tuple[Path, Path, Path]:
    """
    Download all resources needed for video processing.
    
    Args:
        audio_url: URL of the audio file
        intro_image_url: URL of the intro image
        outro_image_url: URL of the outro image
        
    Returns:
        Tuple of paths to the downloaded files (audio, intro image, outro image)
    """
    # Create temp directory
    temp_dir = settings.PROCESSED_VIDEOS_DIR / "temp"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Download all resources concurrently
    audio_path = await download_file(audio_url, temp_dir, ".mp3")
    intro_image_path = await download_file(intro_image_url, temp_dir, ".jpg")
    outro_image_path = await download_file(outro_image_url, temp_dir, ".jpg")
    
    return audio_path, intro_image_path, outro_image_path


async def download_reddit_resources(
    audio_url: str, 
    reddit_post_url: str, 
    first_image_url: str,
    second_image_url: str
) -> Tuple[Path, Path, Path, Path]:
    """
    Download all resources needed for Reddit post video processing.
    
    Args:
        audio_url: URL of the audio file
        reddit_post_url: URL of the Reddit post image
        first_image_url: URL of the first image
        second_image_url: URL of the second image
        
    Returns:
        Tuple of paths to the downloaded files (audio, reddit post image, first image, second image)
    """
    # Create temp directory
    temp_dir = settings.PROCESSED_VIDEOS_DIR / "temp"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Download all resources concurrently
    audio_path = await download_file(audio_url, temp_dir, ".mp3")
    reddit_post_path = await download_file(reddit_post_url, temp_dir, ".jpg")
    first_image_path = await download_file(first_image_url, temp_dir, ".jpg")
    second_image_path = await download_file(second_image_url, temp_dir, ".jpg")
    
    return audio_path, reddit_post_path, first_image_path, second_image_path 