"""
API endpoint definitions
"""
import os
import asyncio
import time
import stat
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from starlette.status import HTTP_202_ACCEPTED, HTTP_404_NOT_FOUND, HTTP_400_BAD_REQUEST, HTTP_206_PARTIAL_CONTENT, HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE

from app.core.config import settings
from app.models.video import VideoRequest, RedditVideoRequest, VideoResponse, VideoStatus
from app.services.video_processor import video_processor


router = APIRouter()


@router.post("/create-video", status_code=HTTP_202_ACCEPTED, response_model=VideoResponse)
async def create_video(request: VideoRequest):
    """
    Generate a video from the provided audio, images, and script.
    
    Args:
        request: Video generation request
        
    Returns:
        JSON response with the video URL or task ID
    """
    try:
        # Create a new task
        task_id = await video_processor.create_task(request)
        
        # Wait for the task to complete or fail
        task = video_processor.get_task(task_id)
        while task.status not in [VideoStatus.COMPLETED, VideoStatus.FAILED]:
            await asyncio.sleep(1)
            task = video_processor.get_task(task_id)
        
        # Check if the task failed
        if task.status == VideoStatus.FAILED:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Video generation failed: {task.error}"
            )
        
        # Get the video URL
        video_url = video_processor.get_video_url(task_id)
        if not video_url:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        # Return the video URL
        return VideoResponse(video_url=video_url)
        
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Error processing request: {str(e)}"
        )


@router.post("/create-reddit-video", status_code=HTTP_202_ACCEPTED, response_model=VideoResponse)
async def create_reddit_video(request: RedditVideoRequest):
    """
    Generate a Reddit post video from the provided audio, Reddit post image, and additional images.
    
    Args:
        request: Reddit video generation request
        
    Returns:
        JSON response with the video URL or task ID
    """
    try:
        # Create a new Reddit task
        task_id = await video_processor.create_reddit_task(request)
        
        # Wait for the task to complete or fail
        task = video_processor.get_task(task_id)
        while task.status not in [VideoStatus.COMPLETED, VideoStatus.FAILED]:
            await asyncio.sleep(1)
            task = video_processor.get_task(task_id)
        
        # Check if the task failed
        if task.status == VideoStatus.FAILED:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Reddit video generation failed: {task.error}"
            )
        
        # Get the video URL
        video_url = video_processor.get_video_url(task_id)
        if not video_url:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        # Return the video URL
        return VideoResponse(video_url=video_url)
        
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Error processing request: {str(e)}"
        )


def send_file_with_range_support(
    file_path: Path, 
    media_type: str,
    request: Request
) -> StreamingResponse:
    """
    Stream a file with support for HTTP range requests.
    
    Args:
        file_path: Path to the file
        media_type: Media type of the file
        request: HTTP request
        
    Returns:
        Streaming response with range support
    """
    file_size = file_path.stat().st_size
    range_header = request.headers.get("Range", "").strip()
    
    # Range header processing
    start = 0
    end = file_size - 1
    
    # Check for valid range header
    if range_header:
        try:
            range_parts = range_header.replace("bytes=", "").split("-")
            if range_parts[0]:
                start = int(range_parts[0])
            if len(range_parts) > 1 and range_parts[1]:
                end = min(int(range_parts[1]), file_size - 1)
                
            # Validate range
            if start > end or start < 0 or end >= file_size:
                raise HTTPException(
                    status_code=HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                    detail=f"Invalid range request: {start}-{end}/{file_size}"
                )
        except ValueError:
            # If we can't parse the range header, ignore it
            pass
    
    # Calculate the content length
    content_length = end - start + 1
    
    # Prepare the response headers
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Type": media_type,
        "Content-Disposition": f"attachment; filename={file_path.name}",
        "Cache-Control": "public, max-age=86400"  # 24 hour cache
    }
    
    # Create a generator to stream the file
    async def file_streamer():
        with open(file_path, "rb") as f:
            f.seek(start)
            data = f.read(min(content_length, 1024 * 1024))  # Read up to 1MB at a time
            while data:
                yield data
                content_length_remaining = end - f.tell() + 1
                if content_length_remaining <= 0:
                    break
                data = f.read(min(content_length_remaining, 1024 * 1024))
    
    # Return the appropriate response
    status_code = HTTP_206_PARTIAL_CONTENT if range_header else 200
    return StreamingResponse(
        file_streamer(),
        status_code=status_code,
        headers=headers
    )


@router.get("/videos/{filename}")
async def get_video(filename: str, request: Request):
    """
    Get a video file with streaming and range request support.
    
    Args:
        filename: Name of the video file
        request: The HTTP request
        
    Returns:
        Streaming video file with support for range requests
    """
    file_path = settings.PROCESSED_VIDEOS_DIR / filename
    
    # Attempt file access with retries
    max_retries = 3
    retry_delay = 1.0  # seconds
    
    for attempt in range(max_retries):
        if not os.path.exists(file_path):
            if attempt < max_retries - 1:
                # Wait and retry if the file might still be in the process of being moved/created
                await asyncio.sleep(retry_delay)
                continue
            else:
                raise HTTPException(
                    status_code=HTTP_404_NOT_FOUND,
                    detail="Video not found"
                )
        
        # Make sure the file is readable and wait for any locks to clear
        try:
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                if attempt < max_retries - 1:
                    # File exists but is empty or still being written
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    raise HTTPException(
                        status_code=HTTP_400_BAD_REQUEST,
                        detail="Video file is empty or corrupted"
                    )
                    
            # Attempt to open the file to verify it's available and not locked
            with open(file_path, "rb") as _:
                pass
                
            # File is good, break the retry loop
            break
                
        except (PermissionError, OSError) as e:
            if attempt < max_retries - 1:
                # File might be locked, wait and retry
                await asyncio.sleep(retry_delay)
            else:
                # Try to fix permissions if needed
                try:
                    os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                except Exception as perm_e:
                    raise HTTPException(
                        status_code=HTTP_400_BAD_REQUEST,
                        detail=f"Cannot read video file: {str(perm_e)}"
                    )
    
    # Let Glif client know this is a media file that should be handled appropriately
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=86400"  # 24 hour cache to reduce repeated requests
    }
    
    # Return streaming response with range support
    return send_file_with_range_support(
        file_path=file_path,
        media_type="video/mp4",
        request=request
    ) 