"""
Service for processing videos
"""
import os
import uuid
import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, Optional, List

from app.core.config import settings
from app.models.video import VideoRequest, RedditVideoRequest, VideoStatus, VideoTask, GameplayType
from app.utils.download import download_resources, download_reddit_resources
from app.utils.media import transcribe_audio, generate_video, generate_reddit_video
from app.utils.cleanup import cleanup_service


class VideoProcessor:
    """Service for handling video processing tasks"""
    
    def __init__(self):
        self.tasks: Dict[str, VideoTask] = {}
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_VIDEOS)
        self.logger = logging.getLogger("video_processor")
        # Start the cleanup service
        cleanup_service.start()
        
    async def create_task(self, request: VideoRequest) -> str:
        """
        Create a new video processing task.
        
        Args:
            request: Video processing request
            
        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())
        
        # Store request type to differentiate processing
        task = VideoTask(
            id=task_id,
            status=VideoStatus.PENDING,
            request=request,
            result_path=None
        )
        
        # Add a custom attribute to track request type
        setattr(task, '_request_type', 'standard')
        
        self.tasks[task_id] = task
        
        # Start processing in the background
        asyncio.create_task(self._process_video(task_id))
        
        return task_id
    
    async def create_reddit_task(self, request: RedditVideoRequest) -> str:
        """
        Create a new Reddit video processing task.
        
        Args:
            request: Reddit video processing request
            
        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())
        
        # Store request type to differentiate processing
        task = VideoTask(
            id=task_id,
            status=VideoStatus.PENDING,
            request=request,
            result_path=None
        )
        
        # Add a custom attribute to track request type
        setattr(task, '_request_type', 'reddit')
        
        self.tasks[task_id] = task
        
        # Start processing in the background
        asyncio.create_task(self._process_reddit_video(task_id))
        
        return task_id
    
    def get_task(self, task_id: str) -> Optional[VideoTask]:
        """
        Get a task by ID.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task object or None if not found
        """
        return self.tasks.get(task_id)
    
    def get_video_url(self, task_id: str) -> Optional[str]:
        """
        Get the URL for a processed video.
        
        Args:
            task_id: Task ID
            
        Returns:
            URL to the video or None if not ready
        """
        task = self.get_task(task_id)
        if task and task.status == VideoStatus.COMPLETED and task.result_path:
            # Ensure the file actually exists before returning URL
            if os.path.exists(task.result_path):
                # Return full Cloudflare URL instead of relative path
                filename = os.path.basename(task.result_path)
                return f"https://brainrot.i12bp8.xyz/videos/{filename}"
            else:
                self.logger.error(f"Video file {task.result_path} does not exist on disk")
                return None
        return None
        
    async def _process_video(self, task_id: str):
        """
        Process a video task.
        
        Args:
            task_id: Task ID
        """
        async with self.semaphore:
            task = self.tasks[task_id]
            task.status = VideoStatus.PROCESSING
            
            # Track temporary files for cleanup
            temp_files = []
            
            try:
                # Explicitly cast the request to VideoRequest to avoid type issues
                video_request = task.request
                
                # Download resources
                self.logger.info(f"Task {task_id}: Downloading resources")
                audio_path, intro_image_path, outro_image_path = await download_resources(
                    video_request.audio_url,
                    video_request.intro_image,
                    video_request.outro_image
                )
                
                # Keep track of temp files
                temp_files.extend([audio_path, intro_image_path, outro_image_path])
                
                # Transcribe audio
                self.logger.info(f"Task {task_id}: Transcribing audio")
                try:
                    transcript_segments = transcribe_audio(audio_path)
                    self.logger.info(f"Task {task_id}: Transcription complete - {len(transcript_segments)} segments")
                except Exception as e:
                    self.logger.error(f"Task {task_id}: Transcription failed: {str(e)}")
                    raise
                
                # Generate video
                self.logger.info(f"Task {task_id}: Generating video")
                output_path = generate_video(
                    audio_path,
                    transcript_segments,
                    intro_image_path,
                    outro_image_path,
                    video_request.gameplay_type
                )
                
                # Verify the output file exists and is not empty
                if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                    raise Exception(f"Generated video file {output_path} is missing or empty")
                
                # Update task
                self.logger.info(f"Task {task_id}: Video generated successfully at {output_path}")
                task.result_path = str(output_path)
                task.status = VideoStatus.COMPLETED
                
                # Register for cleanup
                # Ensure the file is stable before registering for cleanup
                # Wait a short time for any potential file system operations to complete
                await asyncio.sleep(1)
                cleanup_service.register_video(output_path)
                
            except Exception as e:
                import traceback
                self.logger.error(f"Error processing video for task {task_id}: {str(e)}")
                self.logger.error(f"Traceback for task {task_id}: {traceback.format_exc()}")
                task.status = VideoStatus.FAILED
                task.error = str(e)
            finally:
                # Always clean up temporary files regardless of success/failure
                if temp_files:
                    self._cleanup_temp_files(temp_files)
                
                # Force background cleanup service to scan for orphaned files
                try:
                    cleanup_service._cleanup_orphaned_temp_files()
                except Exception as cleanup_e:
                    self.logger.warning(f"Background cleanup scan failed: {cleanup_e}")
    
    async def _process_reddit_video(self, task_id: str):
        """
        Process a Reddit video task.
        
        Args:
            task_id: Task ID
        """
        async with self.semaphore:
            task = self.tasks[task_id]
            task.status = VideoStatus.PROCESSING
            
            # Track temporary files for cleanup
            temp_files = []
            
            try:
                # Explicitly cast the request to RedditVideoRequest to avoid type issues
                reddit_request = task.request
                
                # Download resources
                self.logger.info(f"Task {task_id}: Downloading Reddit resources")
                audio_path, reddit_post_path, first_image_path, second_image_path = await download_reddit_resources(
                    reddit_request.audio_url,
                    reddit_request.reddit_post_image,
                    reddit_request.first_image,
                    reddit_request.second_image
                )
                
                # Keep track of temp files
                temp_files.extend([audio_path, reddit_post_path, first_image_path, second_image_path])
                
                # Transcribe audio
                self.logger.info(f"Task {task_id}: Transcribing audio")
                try:
                    transcript_segments = transcribe_audio(audio_path)
                    self.logger.info(f"Task {task_id}: Transcription complete - {len(transcript_segments)} segments")
                except Exception as e:
                    self.logger.error(f"Task {task_id}: Transcription failed: {str(e)}")
                    raise
                
                # Generate Reddit video
                self.logger.info(f"Task {task_id}: Generating Reddit video")
                output_path = generate_reddit_video(
                    audio_path,
                    transcript_segments,
                    reddit_post_path,
                    first_image_path,
                    second_image_path,
                    reddit_request.gameplay_type
                )
                
                # Verify the output file exists and is not empty
                if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                    raise Exception(f"Generated Reddit video file {output_path} is missing or empty")
                
                # Update task
                self.logger.info(f"Task {task_id}: Reddit video generated successfully at {output_path}")
                task.result_path = str(output_path)
                task.status = VideoStatus.COMPLETED
                
                # Register for cleanup
                # Ensure the file is stable before registering for cleanup
                # Wait a short time for any potential file system operations to complete
                await asyncio.sleep(1)
                cleanup_service.register_video(output_path)
                
            except Exception as e:
                import traceback
                self.logger.error(f"Error processing Reddit video for task {task_id}: {str(e)}")
                self.logger.error(f"Traceback for task {task_id}: {traceback.format_exc()}")
                task.status = VideoStatus.FAILED
                task.error = str(e)
            finally:
                # Always clean up temporary files regardless of success/failure
                if temp_files:
                    self._cleanup_temp_files(temp_files)
                
                # Force background cleanup service to scan for orphaned files
                try:
                    cleanup_service._cleanup_orphaned_temp_files()
                except Exception as cleanup_e:
                    self.logger.warning(f"Background cleanup scan failed: {cleanup_e}")
    
    def _cleanup_temp_files(self, files: List[Path]):
        """
        Clean up temporary files.
        
        Args:
            files: List of file paths to clean up
        """
        for file_path in files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                self.logger.error(f"Error cleaning up file {file_path}: {str(e)}")


# Create singleton instance
video_processor = VideoProcessor() 