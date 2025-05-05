"""
Utilities for media processing
"""
import os
import random
import tempfile
import json
import traceback
import itertools
import time
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from multiprocessing import Pool, cpu_count
from functools import lru_cache

import cv2
import numpy as np
import ffmpeg
import whisper_timestamped as whisper
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, CompositeAudioClip, ColorClip
from moviepy.video.fx import fadeout, fadein
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import requests

from app.core.config import settings
from app.models.video import GameplayType

# Disable ImageMagick binary requirement
os.environ["IMAGEMAGICK_BINARY"] = ""

# Constants for better aesthetics
TEXT_COLOR = (255, 255, 255, 255)  # White with full opacity
SHADOW_COLOR = (0, 0, 0, 180)  # Black with 70% opacity
FONT_SIZE = 64  # Larger text for better readability
SHADOW_OFFSET = 3  # Bigger shadow for better visibility
# Remove custom font - use system fonts instead

# Cache for video metadata to avoid repeated probing
VIDEO_METADATA_CACHE: Dict[str, Dict[str, Any]] = {}

def create_text_image(text: str, width: int, height: int, fontsize: int = 120):
    """Create a bold, white text with black border centered and positioned higher."""
    # Create blank transparent image
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Use system fonts - try to use a bold font
    try:
        font = ImageFont.truetype("Arial Bold.ttf", fontsize)
    except:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", fontsize)
        except:
            try:
                font = ImageFont.truetype("Arial", fontsize)
            except:
                font = ImageFont.load_default()
    
    # Calculate text size to ensure padding
    if hasattr(draw, 'textbbox'):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    else:
        text_width, text_height = draw.textsize(text, font=font)
    
    # Make sure text fits within image with 10% padding on each side
    max_width = int(width * 0.9)  # 90% of width
    
    # If text is too wide, scale down the font
    if text_width > max_width:
        scale_factor = max_width / text_width
        new_fontsize = int(fontsize * scale_factor)
        
        # Try with new size
        try:
            font = ImageFont.truetype("Arial Bold.ttf", new_fontsize)
        except:
            try:
                font = ImageFont.truetype("DejaVuSans-Bold.ttf", new_fontsize)
            except:
                font = ImageFont.load_default()
        
        # Recalculate with new font
        if hasattr(draw, 'textbbox'):
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        else:
            text_width, text_height = draw.textsize(text, font=font)
    
    # Position at center but higher up (40% from bottom)
    position = ((width - text_width) // 2, int(height * 0.6) - text_height)
    
    # Draw thick black outline (no background)
    for offset_x in range(-5, 6, 1):
        for offset_y in range(-5, 6, 1):
            if abs(offset_x) + abs(offset_y) > 0:  # Skip the center (that will be white)
                draw.text(
                    (position[0] + offset_x, position[1] + offset_y),
                    text, font=font, fill=(0, 0, 0, 255)
                )
    
    # Draw main white text
    draw.text(position, text, font=font, fill=(255, 255, 255, 255))
    
    return img

def create_styled_text_clip(text: str, size: Tuple[int, int], duration: float, start_time: float):
    """
    Create a stylized text clip for captions using PIL and ImageClip with better animation
    
    Args:
        text: Text content
        size: Size of the clip (width, height)
        duration: Duration of the clip
        start_time: Start time of the clip
        
    Returns:
        Styled ImageClip with text and animation
    """
    img = create_text_image(text, size[0], size[1])
    
    # Convert PIL Image to MoviePy ImageClip
    clip = ImageClip(np.array(img))
    
    # First set position and duration
    clip = clip.set_position(('center', 'top')).set_duration(duration).set_start(start_time)
    
    # Then add animations (fade in/out) if the clip is long enough
    fade_duration = min(0.2, duration / 4)  # Fade time proportional to clip duration
    if duration > 0.4:  # Only add fades if clip is long enough
        clip = clip.fadein(fade_duration).fadeout(fade_duration)
    
    return clip

def transcribe_audio(audio_path: Path) -> List[Dict[str, Any]]:
    """
    Transcribe audio file using Whisper.
    
    Args:
        audio_path: Path to the audio file
        
    Returns:
        List of segments with text, start, end, confidence
    """
    try:
        # Initialize and load the model
        model = whisper.load_model(settings.WHISPER_MODEL)
        
        # Configure options - try advanced features first
        options = {
            "verbose": False,
            "word_timestamps": True,
            "language": "en",
            # Only add threads if it's actually supported in this version
            # to avoid the "transcribe_timestamped() got an unexpected keyword argument 'threads'" error
        }
        
        # Add thread count only if we're using a sufficiently recent version that supports it
        try:
            # Check if this specific function accepts the threads parameter
            import inspect
            if 'threads' in inspect.signature(whisper.transcribe).parameters:
                options["threads"] = settings.WHISPER_THREADS
        except Exception:
            # If there's any error checking, just don't use threads parameter
            pass
        
        # Use word timestamps for better sync
        try:
            result = whisper.transcribe(model, str(audio_path), **options)
        except TypeError:
            # Fall back to simpler options if word_timestamps not supported
            options.pop("word_timestamps", None)
            if "threads" in options:
                options.pop("threads", None)
            result = whisper.transcribe(model, str(audio_path), **options)
    except Exception as e:
        print(f"Transcription error with advanced options: {e}")
        # Last resort fallback with minimal options
        try:
            result = whisper.transcribe(model, str(audio_path))
        except Exception as e2:
            print(f"Basic transcription also failed: {e2}")
            # Return minimal segments if all transcription attempts fail
            return [{"text": "Transcription failed", "start": 0, "end": 5, "confidence": 1.0}]
    
    # Process result to get cleaner segments
    segments = []
    
    if "segments" in result:
        for segment in result["segments"]:
            if "words" in segment:
                words = segment["words"]
                
                # Group words into reasonable phrases (4-6 words)
                phrase_size = 5  # Target words per phrase
                for i in range(0, len(words), phrase_size):
                    phrase_words = words[i:i+phrase_size]
                    if phrase_words:
                        segments.append({
                            "text": " ".join([w.get("text", "").strip() for w in phrase_words]),
                            "start": phrase_words[0].get("start", 0),
                            "end": phrase_words[-1].get("end", 0),
                            "confidence": sum([w.get("confidence", 1.0) for w in phrase_words]) / len(phrase_words)
                        })
            else:
                # If no word timestamps, use segment level
                segments.append({
                    "text": segment.get("text", ""),
                    "start": segment.get("start", 0),
                    "end": segment.get("end", 0),
                    "confidence": 1.0
                })
    elif "word_segments" in result:
        # Same grouping logic for word_segments format
        words = result["word_segments"]
        phrase_size = 5
        for i in range(0, len(words), phrase_size):
            phrase_words = words[i:i+phrase_size]
            if phrase_words:
                segments.append({
                    "text": " ".join([w.get("text", "").strip() for w in phrase_words]),
                    "start": phrase_words[0].get("start", 0),
                    "end": phrase_words[-1].get("end", 0),
                    "confidence": sum([w.get("confidence", 1.0) for w in phrase_words]) / len(phrase_words)
                })
    else:
        # Fallback
        text = result.get("text", "")
        words = text.split()
        duration = get_audio_duration(audio_path)
        
        # Create segments of 5 words each
        phrase_size = 5
        for i in range(0, len(words), phrase_size):
            phrase = " ".join(words[i:i+phrase_size])
            segment_duration = duration / (len(words) / phrase_size)
            start_time = i / len(words) * duration
            segments.append({
                "text": phrase,
                "start": start_time,
                "end": start_time + segment_duration,
                "confidence": 1.0
            })
    
    return segments

def select_random_background(gameplay_type: GameplayType) -> Path:
    """
    Select background video based on gameplay type.
    
    Args:
        gameplay_type: Type of gameplay background to use
        
    Returns:
        Path to the selected background video
    """
    # Get the folder path for the specified gameplay type
    folder_path = settings.BACKGROUND_DIR / str(gameplay_type.value)
    
    # Check if folder exists
    if not folder_path.exists():
        raise ValueError(f"Background folder not found for gameplay type: {gameplay_type}")
    
    # List all video files in the directory (supports webm, mp4, mov formats)
    video_files = list(folder_path.glob("*.webm")) + list(folder_path.glob("*.mp4")) + list(folder_path.glob("*.mov"))
    
    if not video_files:
        raise ValueError(f"No video files found in {folder_path}")
    
    # Select a random video file
    return random.choice(video_files)

def select_random_music() -> Path:
    """
    Select a random music track.
    
    Returns:
        Path to the selected music file
    """
    music_files = list(settings.MUSIC_DIR.glob("*.MP3"))
    return random.choice(music_files)

@lru_cache(maxsize=32)
def get_audio_duration(audio_path: Path) -> float:
    """
    Get the duration of an audio file.
    
    Args:
        audio_path: Path to the audio file
        
    Returns:
        Duration in seconds
    """
    audio = AudioFileClip(str(audio_path))
    duration = audio.duration
    audio.close()
    return duration

def get_video_metadata(video_path: Path) -> Dict[str, Any]:
    """Get metadata for a video file with caching for improved performance.
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Dictionary with video metadata
    """
    path_str = str(video_path)
    
    # Return cached metadata if available
    if path_str in VIDEO_METADATA_CACHE:
        return VIDEO_METADATA_CACHE[path_str]
    
    try:
        # Probe the video and cache the results
        probe = ffmpeg.probe(path_str)
        
        # Limit cache size to prevent memory issues
        if len(VIDEO_METADATA_CACHE) >= settings.MAX_CACHE_SIZE:
            # Remove a random item if cache is full
            VIDEO_METADATA_CACHE.pop(next(iter(VIDEO_METADATA_CACHE)))
            
        VIDEO_METADATA_CACHE[path_str] = probe
        return probe
    except Exception as e:
        print(f"Error probing video {path_str}: {e}")
        # Return a minimal fallback
        return {"format": {"duration": "60.0"}, "streams": [{"codec_type": "video"}]}

def extract_random_segment(video_path: Path, duration: float) -> Path:
    """Extract a random segment from a video file with the specified duration using direct ffmpeg commands for speed."""
    # Get basic info about the video without loading it fully
    try:
        probe = get_video_metadata(video_path)
        video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        video_duration = float(probe['format']['duration'])
    except Exception as e:
        print(f"Error processing video metadata: {e}")
        # Default to 60 seconds if we can't get duration
        video_duration = 60.0
    
    # Choose a random start point
    max_start = max(0, video_duration - duration)
    start_time = random.uniform(0, max_start) if max_start > 0 else 0
    
    # Generate output path
    extracted_path = settings.PROCESSED_VIDEOS_DIR / f"temp_background_{random.randint(1000, 9999)}.mp4"
    
    try:
        # Direct ffmpeg command for maximum speed
        (
            ffmpeg
            .input(str(video_path), ss=start_time, t=min(duration, video_duration-start_time))
            .output(
                str(extracted_path),
                vcodec='libx264',
                preset=settings.VIDEO_PRESET,
                crf=settings.VIDEO_CRF,
                pix_fmt='yuv420p',
                an=None,  # No audio
                threads=settings.FFMPEG_THREADS
            )
            .global_args('-loglevel', 'error', '-y')
            .run(capture_stdout=True, capture_stderr=True)
        )
        
        # Register the file for cleanup
        from app.utils.cleanup import cleanup_service
        cleanup_service.register_video(extracted_path)
        
        return extracted_path
    except Exception as e:
        print(f"Error in ffmpeg extraction: {e}")
        # If extraction fails, just copy the original file as fallback
        shutil.copy(str(video_path), str(extracted_path))
        
        # Register the file for cleanup even in error case
        from app.utils.cleanup import cleanup_service
        cleanup_service.register_video(extracted_path)
        
        return extracted_path

def create_subtitle_file(temp_dir: Path, transcript_segments: List[Dict[str, Any]]) -> Path:
    """Create ASS subtitle file with word-by-word animation from transcript segments.
    
    Args:
        temp_dir: Directory to store the subtitle file
        transcript_segments: List of transcript segments with timing information
        
    Returns:
        Path to the created subtitle file
    """
    subtitle_file = temp_dir / "subtitles.ass"
    with open(subtitle_file, 'w', encoding='utf-8') as f:
        f.write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
; BorderStyle=1 is outline only, no box
; &H00000000 is fully transparent for BackColour
Style: Default,Arial,160,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,9,0,2,10,10,180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""")
        
        # Process transcript to show ONE WORD AT A TIME with subtle bounce animation
        for segment in transcript_segments:
            if "text" not in segment or not segment["text"].strip():
                continue
            
            words = segment["text"].split()
            
            if not words:
                continue
            
            # Calculate time per word - sync to audio exactly
            segment_duration = segment["end"] - segment["start"]
            word_duration = segment_duration / len(words)
            
            # Add each word as a separate subtitle with exact timing and bounce animation
            # Start subtitles at second 0
            for i, word in enumerate(words):
                word_start = segment["start"] + (i * word_duration)
                word_end = word_start + word_duration
                
                # Format times in ASS format (h:mm:ss.cc)
                start_str = f"{int(word_start//3600)}:{int((word_start%3600)//60):02d}:{word_start%60:05.2f}"
                end_str = f"{int(word_end//3600)}:{int((word_end%3600)//60):02d}:{word_end%60:05.2f}"
                
                # Escape any special characters in the text
                clean_word = word.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
                
                # Add slightly more noticeable bounce animation using ASS transform tags
                # The animation scales the text up and down during its display time
                # Also explicitly set \bord for border and \shad0 for no shadow
                animated_word = f"{{\\bord9\\shad0\\t(0,{word_duration/6:.2f},\\fscx125\\fscy125\\frz-5)\\t({word_duration/6:.2f},{word_duration/3:.2f},\\fscx100\\fscy100\\frz0)}}{clean_word}"
                
                # Write the dialogue line for a single word with animation and NO BACKGROUND
                f.write(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{animated_word}\\N\n")
                
    return subtitle_file

def prepare_background(gameplay_type: GameplayType, duration: float) -> Path:
    """Prepare a background video segment for the specified gameplay type and duration.
    
    Args:
        gameplay_type: Type of gameplay background
        duration: Required duration in seconds
        
    Returns:
        Path to the prepared background video
    """
    # Get background video and extract a random segment based on the required duration
    bg_video_path = select_random_background(gameplay_type)
    background = extract_random_segment(bg_video_path, duration)
    
    # Ensure the background is registered for cleanup
    from app.utils.cleanup import cleanup_service
    cleanup_service.register_video(background)
    
    return background

def generate_video(
    audio_path: Path,
    transcript_segments: List[Dict[str, Any]],
    intro_image_path: Path,
    outro_image_path: Path,
    gameplay_type: GameplayType
) -> Path:
    """Generate a video with optimal settings for viral content."""
    try:
        print("Starting optimal viral video generation...")
        
        # Create temp directory for minimal processing
        temp_dir = settings.PROCESSED_VIDEOS_DIR / f"temp_{random.randint(1000, 9999)}"
        temp_dir.mkdir(exist_ok=True)
        
        try:
            # Generate output paths
            output_path = settings.PROCESSED_VIDEOS_DIR / f"video_{random.randint(10000, 99999)}.mp4"
            
            # Use subprocess directly for max performance
            import subprocess
            
            # Step 1: Get the audio duration
            audio_duration = get_audio_duration(audio_path)
            print(f"Audio duration: {audio_duration}s")
            
            # Step 2: Create subtitle file with proper styling
            subtitle_file = create_subtitle_file(temp_dir, transcript_segments)
            
            # Define animation durations for intro and outro
            intro_delay = 5.0
            intro_duration = 5.0
            
            # Outro shows 10 seconds before end and disappears 5 seconds before end
            outro_start_offset = 10.0  # seconds before the end
            outro_duration = 5.0  # show for 5 seconds
            
            # Calculate exact timings
            intro_start = intro_delay
            intro_end = intro_start + intro_duration
            
            # Outro starts 10 seconds before end and shows for 5 seconds
            outro_start = audio_duration - outro_start_offset
            outro_end = outro_start + outro_duration  # 5 seconds before end
            
            # Total video length should account for intro delay and full audio duration
            total_duration = audio_duration + intro_delay
            
            # Prepare background video
            bg_video_path = prepare_background(gameplay_type, total_duration)
            
            # Create the mixed audio - simpler version with popup sound at intro and outro
            mixed_audio_path = temp_dir / "mixed_audio.mp3"
            
            # Mix audio: narration with popup sounds at intro and outro
            subprocess.run([
                "ffmpeg", "-y",
                "-i", str(audio_path),                    # Input 0: Main audio
                "-i", str(select_random_music()),         # Input 1: Background music
                "-i", str(settings.SOUNDS_DIR / "popup.mp3"),  # Input 2: Popup sound (intro)
                "-i", str(settings.SOUNDS_DIR / "popup.mp3"),  # Input 3: Popup sound (outro)
                "-filter_complex",
                # No delay for main audio, boost volume
                "[0:a]volume=1.5[narration];"
                # Increase background music volume
                "[1:a]volume=0.8[music];"
                # Increase popup sound volume at intro
                f"[2:a]volume=5.0,adelay={int(intro_delay*1000)}|{int(intro_delay*1000)}[popup_intro];"
                # Increase popup sound volume at outro
                f"[3:a]volume=5.0,adelay={int(outro_start*1000)}|{int(outro_start*1000)}[popup_outro];"
                # Mix all audio streams
                "[narration][music][popup_intro][popup_outro]amix=inputs=4:duration=longest:normalize=0",
                "-b:a", settings.AUDIO_BITRATE,
                "-threads", str(settings.FFMPEG_THREADS),
                str(mixed_audio_path)
            ], check=True)
            
            # Command to create the final video
            cmd = [
                "ffmpeg", "-y",
                # Background video with loop
                "-stream_loop", "-1",
                "-i", str(bg_video_path),
                # Mixed audio
                "-i", str(mixed_audio_path),
                # Intro image - static, no animation
                "-loop", "1", "-i", str(intro_image_path),
                # Outro image - static, no animation
                "-loop", "1", "-i", str(outro_image_path),
                # Filter graph
                "-filter_complex",
                # Scale background video to vertical
                f"[0:v]scale=1080:1920,setpts=PTS-STARTPTS[bg];" +
                # Add subtitles with proper styling (centered, bold, large with NO background)
                # BorderStyle=1 means outline only (no box), set backcolor to transparent
                f"[bg]subtitles={str(subtitle_file).replace(chr(92), '/')}:force_style='FontName=Arial,FontSize=160,Alignment=2,MarginV=180,BorderStyle=1,Outline=9,Shadow=0,Bold=1,BackColour=&H00000000'[bg_sub];" +
                # Process intro image - NO animation, positioned higher with more side padding
                f"[2:v]scale=900:900:force_original_aspect_ratio=decrease," +
                f"pad=1080:1920:(ow-iw)/2:300:color=black@0," +
                f"setpts=PTS-STARTPTS+{intro_start},trim=0:{intro_duration}[intro];" +
                # Process outro image - NO animation, positioned higher with more side padding
                f"[3:v]scale=900:900:force_original_aspect_ratio=decrease," +
                f"pad=1080:1920:(ow-iw)/2:300:color=black@0," +
                f"setpts=PTS-STARTPTS+{outro_start},trim=0:{outro_duration}[outro];" +
                # Overlay intro and outro at exact timings
                f"[bg_sub][intro]overlay=0:0:enable='between(t,{intro_start},{intro_end})'[with_intro];" +
                f"[with_intro][outro]overlay=0:0:enable='between(t,{outro_start},{outro_end})'[final]",
                # Map streams
                "-map", "[final]",
                "-map", "1:a",
                # Output settings
                "-c:v", "libx264",
                "-preset", settings.VIDEO_PRESET,
                "-crf", str(settings.VIDEO_CRF),
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", 
                "-b:a", settings.AUDIO_BITRATE,
                # Exact duration matching audio plus outro
                "-t", str(total_duration),
                "-movflags", "+faststart",
                "-threads", str(settings.FFMPEG_THREADS),
                str(output_path)
            ]
            
            # Execute the command
            subprocess.run(cmd, check=True)
            
            print(f"Video generation complete: {output_path}")
            return output_path
            
        except Exception as inner_e:
            print(f"Error in processing: {str(inner_e)}")
            traceback.print_exc()
            raise inner_e
        finally:
            # Clean up temp directory
            try:
                shutil.rmtree(str(temp_dir))
            except Exception as cleanup_e:
                print(f"Warning: Failed to clean up temp directory: {cleanup_e}")
            
    except Exception as e:
        print(f"Error in video generation: {str(e)}")
        traceback.print_exc()
        try:
            return create_emergency_video(audio_path, intro_image_path)
        except Exception as e2:
            print(f"Emergency video also failed: {e2}")
            return settings.PROCESSED_VIDEOS_DIR / f"error_{random.randint(10000, 99999)}.mp4"

def create_emergency_video(audio_path: Path, image_path: Path) -> Path:
    """Create a super simple video with just audio and an image using direct ffmpeg for speed."""
    output_path = settings.PROCESSED_VIDEOS_DIR / f"emergency_{random.randint(10000, 99999)}.mp4"
    
    try:
        # Direct subprocess approach for maximum reliability
        print("Creating emergency video with direct subprocess...")
        
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(image_path),
            "-i", str(audio_path),
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", settings.AUDIO_BITRATE,
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # Ensure even dimensions
            "-preset", settings.VIDEO_PRESET,
            "-threads", str(settings.FFMPEG_THREADS),
            str(output_path)
        ]
        
        import subprocess
        subprocess.run(cmd, check=True)
        return output_path
    except Exception as e:
        print(f"Emergency video failed: {e}")
        traceback.print_exc()
        # Last resort - static image as fallback
        try:
            # Try to convert image directly to video without audio using subprocess
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(image_path),
                "-t", "5",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "ultrafast",
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # Ensure even dimensions
                str(output_path)
            ]
            subprocess.run(cmd, check=True)
            return output_path
        except Exception as e:
            print(f"Basic video fallback also failed: {e}")
            traceback.print_exc()
            # Just return a path even if nothing works
            with open(str(output_path), 'wb') as f:
                f.write(b'MP4 placeholder')
            return output_path 

def generate_reddit_video(
    audio_path: Path,
    transcript_segments: List[Dict[str, Any]],
    reddit_post_path: Path,
    first_image_path: Path,
    second_image_path: Path,
    gameplay_type: GameplayType
) -> Path:
    """Generate a Reddit post video with optimal settings for viral content."""
    try:
        print("Starting optimal Reddit video generation...")
        
        # Create temp directory for minimal processing
        temp_dir = settings.PROCESSED_VIDEOS_DIR / f"temp_{random.randint(1000, 9999)}"
        temp_dir.mkdir(exist_ok=True)
        
        try:
            # Generate output paths
            output_path = settings.PROCESSED_VIDEOS_DIR / f"reddit_video_{random.randint(10000, 99999)}.mp4"
            
            # Use subprocess directly for max performance
            import subprocess
            
            # Step 1: Get the audio duration
            audio_duration = get_audio_duration(audio_path)
            print(f"Audio duration: {audio_duration}s")
            
            # Step 2: Create subtitle file with proper styling
            subtitle_file = create_subtitle_file(temp_dir, transcript_segments)
            
            # Define image timings for Reddit format
            # Reddit post comes after 1 second and stays for 5 seconds
            reddit_post_start = 1.0
            reddit_post_duration = 5.0
            
            # Middle image appears at the middle of the audio duration and stays for 5 seconds
            # Calculate the middle point of the audio
            middle_point = audio_duration / 2
            first_image_start = middle_point - 2.5  # Center the 5-second image around the middle point
            first_image_duration = 5.0
            
            # Second image appears with a 5-second gap between the end of the video and the image
            # This means the image ends 5 seconds before the end of the video
            second_image_start = audio_duration - 10.0  # Start 10 seconds before end (5 seconds for image + 5 seconds gap)
            second_image_duration = 5.0  # Show for 5 seconds
            
            # Total video length
            total_duration = audio_duration
            
            # Prepare background video
            bg_video_path = prepare_background(gameplay_type, total_duration)
            
            # Create the mixed audio - simpler version with popup sound at transitions
            mixed_audio_path = temp_dir / "mixed_audio.mp3"
            
            # Mix audio: narration with popup sounds at image transitions
            subprocess.run([
                "ffmpeg", "-y",
                "-i", str(audio_path),                    # Input 0: Main audio
                "-i", str(select_random_music()),         # Input 1: Background music
                "-i", str(settings.SOUNDS_DIR / "popup.mp3"),  # Input 2: Popup sound (reddit post)
                "-i", str(settings.SOUNDS_DIR / "popup.mp3"),  # Input 3: Popup sound (first image)
                "-i", str(settings.SOUNDS_DIR / "popup.mp3"),  # Input 4: Popup sound (second image)
                "-filter_complex",
                # No delay for main audio, boost volume
                "[0:a]volume=1.5[narration];"
                # Increase background music volume
                "[1:a]volume=0.8[music];"
                # Popup sound for Reddit post
                f"[2:a]volume=5.0,adelay={int(reddit_post_start*1000)}|{int(reddit_post_start*1000)}[popup_reddit];"
                # Popup sound for first image
                f"[3:a]volume=5.0,adelay={int(first_image_start*1000)}|{int(first_image_start*1000)}[popup_first];"
                # Popup sound for second image
                f"[4:a]volume=5.0,adelay={int(second_image_start*1000)}|{int(second_image_start*1000)}[popup_second];"
                # Mix all audio streams
                "[narration][music][popup_reddit][popup_first][popup_second]amix=inputs=5:duration=longest:normalize=0",
                "-b:a", settings.AUDIO_BITRATE,
                "-threads", str(settings.FFMPEG_THREADS),
                str(mixed_audio_path)
            ], check=True)
            
            # Command to create the final video
            cmd = [
                "ffmpeg", "-y",
                # Background video with loop
                "-stream_loop", "-1",
                "-i", str(bg_video_path),
                # Mixed audio
                "-i", str(mixed_audio_path),
                # Reddit post image
                "-loop", "1", "-i", str(reddit_post_path),
                # First image
                "-loop", "1", "-i", str(first_image_path),
                # Second image
                "-loop", "1", "-i", str(second_image_path),
                # Filter graph
                "-filter_complex",
                # Scale background video to vertical
                f"[0:v]scale=1080:1920,setpts=PTS-STARTPTS[bg];" +
                # Add subtitles with proper styling (centered, bold, large with NO background)
                # BorderStyle=1 means outline only (no box), set backcolor to transparent
                f"[bg]subtitles={str(subtitle_file).replace(chr(92), '/')}:force_style='FontName=Arial,FontSize=160,Alignment=2,MarginV=180,BorderStyle=1,Outline=9,Shadow=0,Bold=1,BackColour=&H00000000'[bg_sub];" +
                # Process Reddit post image - positioned higher with more side padding
                f"[2:v]scale=900:900:force_original_aspect_ratio=decrease," +
                f"pad=1080:1920:(ow-iw)/2:300:color=black@0," +
                f"setpts=PTS-STARTPTS+{reddit_post_start},trim=0:{reddit_post_duration}[reddit_post];" +
                # Process first image - positioned higher with more side padding
                f"[3:v]scale=900:900:force_original_aspect_ratio=decrease," +
                f"pad=1080:1920:(ow-iw)/2:300:color=black@0," +
                f"setpts=PTS-STARTPTS+{first_image_start},trim=0:{first_image_duration}[first_img];" +
                # Process second image - positioned higher with more side padding
                f"[4:v]scale=900:900:force_original_aspect_ratio=decrease," +
                f"pad=1080:1920:(ow-iw)/2:300:color=black@0," +
                f"setpts=PTS-STARTPTS+{second_image_start},trim=0:{second_image_duration}[second_img];" +
                # Overlay all images at exact timings
                f"[bg_sub][reddit_post]overlay=0:0:enable='between(t,{reddit_post_start},{reddit_post_start+reddit_post_duration})'[with_reddit];" +
                f"[with_reddit][first_img]overlay=0:0:enable='between(t,{first_image_start},{first_image_start+first_image_duration})'[with_first];" +
                f"[with_first][second_img]overlay=0:0:enable='between(t,{second_image_start},{second_image_start+second_image_duration})'[final]",
                # Map streams
                "-map", "[final]",
                "-map", "1:a",
                # Output settings
                "-c:v", "libx264",
                "-preset", settings.VIDEO_PRESET,
                "-crf", str(settings.VIDEO_CRF),
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", 
                "-b:a", settings.AUDIO_BITRATE,
                # Exact duration matching audio
                "-t", str(total_duration),
                "-movflags", "+faststart",
                "-threads", str(settings.FFMPEG_THREADS),
                str(output_path)
            ]
            
            # Execute the command
            subprocess.run(cmd, check=True)
            
            print(f"Reddit video generation complete: {output_path}")
            return output_path
        
        except Exception as inner_e:
            print(f"Error in processing: {str(inner_e)}")
            traceback.print_exc()
            raise inner_e
        finally:
            # Clean up temp directory
            try:
                shutil.rmtree(str(temp_dir))
            except Exception as cleanup_e:
                print(f"Warning: Failed to clean up temp directory: {cleanup_e}")
        
    except Exception as e:
        print(f"Error in Reddit video generation: {str(e)}")
        traceback.print_exc()
        try:
            return create_emergency_video(audio_path, reddit_post_path)
        except Exception as e2:
            print(f"Emergency video also failed: {e2}")
            return settings.PROCESSED_VIDEOS_DIR / f"error_{random.randint(10000, 99999)}.mp4" 