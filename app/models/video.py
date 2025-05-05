"""
Data models for the video processing API
"""
from enum import Enum
from typing import Optional, Union
from pydantic import BaseModel, HttpUrl


class GameplayType(str, Enum):
    """
    Available gameplay types for background video.
    
    To add a new background type:
    1. Add a new entry here with a unique name
    2. Create a folder with the same name as the value under the 'background' directory
    3. Add your background video files in that folder (supported formats: .webm, .mp4, .mov)
    
    The system will automatically:
    - Select a random video file from the corresponding folder
    - Extract a random segment from that video based on the audio duration
    """
    MINECRAFT = "minecraft"
    SUBWAY = "subway"


class VideoRequest(BaseModel):
    """
    Input data model for video generation request.
    
    Attributes:
        audio_url: URL to the audio file
        script: Text transcript of the audio
        gameplay_type: Type of background gameplay video to use
        intro_image: URL to the image to show at the beginning
        outro_image: URL to the image to show at the end
    """
    audio_url: str
    script: str
    gameplay_type: GameplayType
    intro_image: str
    outro_image: str


class RedditVideoRequest(BaseModel):
    """
    Input data model for Reddit post video generation request.
    
    Attributes:
        audio_url: URL to the audio file
        script: Text transcript of the audio
        gameplay_type: Type of background gameplay video to use
        reddit_post_image: URL to the Reddit post image to show at the beginning
        first_image: URL to the first image to show in the middle
        second_image: URL to the second image to show at the end
    """
    audio_url: str
    script: str
    gameplay_type: GameplayType
    reddit_post_image: str
    first_image: str
    second_image: str


class VideoResponse(BaseModel):
    """
    Response data model with the URL to the generated video.
    
    Attributes:
        video_url: URL to access the generated video
    """
    video_url: str


class VideoStatus(str, Enum):
    """Status of a video processing task."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoTask(BaseModel):
    """Internal representation of a video processing task."""
    id: str
    status: VideoStatus
    request: Union[VideoRequest, RedditVideoRequest]
    result_path: Optional[str] = None
    error: Optional[str] = None 