# Brainrot Video Generator API

A powerful API that combines audio, images, and text to create viral-style "brainrot" videos with animated captions over gameplay backgrounds. Perfect for creating engaging social media content.

## Features

- **Text-to-Video Generation**: Converts audio, script, and images into viral-style videos
- **Dynamic Captions**: Word-by-word animated captions that follow the audio
- **Multiple Video Types**: Regular videos and Reddit post video formats
- **Background Variety**: Easy to add new gameplay background types
- **Optimized Performance**: Multithreading, caching, and resource management
- **Robust Error Handling**: Graceful recovery from failures with emergency fallbacks

## Tech Stack

- **FastAPI**: Modern API framework with automatic documentation
- **Whisper AI**: Speech transcription with accurate timestamping
- **FFmpeg**: High-performance video and audio processing
- **Docker**: Containerization for easy deployment and scaling

## Setup Guide

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- At least 4GB RAM and 2 CPU cores recommended
- 2GB of free disk space for the application (more for video storage)

### Required Resource Directories

Create these directories in your project root:

1. `background/` - Contains gameplay videos organized by type:
   - `background/minecraft/` - Minecraft gameplay videos (.mp4, .webm, .mov)
   - `background/subway/` - Subway Surfers gameplay videos (.mp4, .webm, .mov)
   - Add more directories as needed for different gameplay types

2. `music/` - Contains background music (.MP3 files)

3. `Sounds/` - Contains sound effects:
   - `Sounds/popup.mp3` - Required popup sound for transitions

4. `processed_videos/` - Where generated videos will be stored
   - Will be created automatically if it doesn't exist

### Quick Start

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/brainrot-glif-api.git
   cd brainrot-glif-api
   ```

2. **Add your resource files**:
   - Add gameplay videos to `background/minecraft/` and `background/subway/`
   - Add music files to `music/`
   - Add popup sound to `Sounds/popup.mp3`

3. **Configure environment variables** (optional):
   Create a `.env` file in the root directory with your desired settings:
   ```
   # Brainrot Generator environment variables
   PORT=8000
   MAX_CONCURRENT_VIDEOS=0  # 0 = use all CPU cores
   VIDEO_RETENTION_MINUTES=1440
   WHISPER_MODEL=base
   WHISPER_THREADS=0  # 0 = auto
   WORKERS=0  # 0 = auto
   FFMPEG_THREADS=0  # 0 = auto
   VIDEO_CRF=26
   VIDEO_PRESET=ultrafast
   AUDIO_BITRATE=192k
   MAX_CACHE_SIZE=100
   ```

4. **Build and start the services**:
   ```bash
   docker compose up --build
   ```

5. **Access the API**:
   - API Endpoints: `http://localhost:8000/api/v1/`
   - API Documentation: `http://localhost:8000/docs`

### Cloudflare Tunnel Setup (Optional)

If you want to expose your API on the internet using Cloudflare:

1. Create a Cloudflare tunnel in your Cloudflare Zero Trust dashboard
2. Grab your tunnel token
3. Add to your `.env` file:
   ```
   CLOUDFLARE_TUNNEL_TOKEN=your_token_here
   ```

## API Usage

### Standard Video Generation

**Endpoint**: `POST /api/v1/create-video`

**Request Body**:
```json
{
    "audio_url": "https://example.com/audio.mp3",
    "intro_image": "https://example.com/intro.jpg",
    "outro_image": "https://example.com/outro.jpg",
    "gameplay_type": "minecraft"
}
```

### Reddit Post Video Generation

**Endpoint**: `POST /api/v1/create-reddit-video`

**Request Body**:
```json
{
    "audio_url": "https://example.com/audio.mp3",
    "reddit_post_image": "https://example.com/reddit-post.png",
    "first_image": "https://example.com/first.jpg",
    "second_image": "https://example.com/second.jpg",
    "gameplay_type": "minecraft"
}
```

**Response Format**:
```json
{
    "video_url": "http://localhost:8000/videos/video_12345.mp4"
}
```

## Video Timing Configuration

### Standard Video
- Intro image appears after 5 seconds and stays for 5 seconds
- Outro image appears 10 seconds before the end and stays for 5 seconds

### Reddit Post Video
- Reddit post image appears 1 second after start and stays for 5 seconds
- First image appears centered in the middle, stays for 5 seconds
- Second image appears 10 seconds before the end, stays for 5 seconds

## Adding New Background Types

1. **Update the GameplayType Enum**:
   Edit `app/models/video.py` to add your new gameplay type:
   ```python
   class GameplayType(str, Enum):
       MINECRAFT = "minecraft"
       SUBWAY = "subway"
       YOUR_NEW_TYPE = "your_new_type"  # Add this line
   ```

2. **Create a New Directory**:
   ```bash
   mkdir -p background/your_new_type
   ```

3. **Add Video Files**:
   Place your gameplay videos (MP4, WEBM, or MOV format) in this new directory.

## Performance Tuning

### Configuration Options

Adjust these in your `.env` file or directly in `docker-compose.yml`:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `MAX_CONCURRENT_VIDEOS` | Maximum videos processed simultaneously | Number of CPU cores |
| `VIDEO_RETENTION_MINUTES` | How long videos are kept before deletion | 1440 (24 hours) |
| `WHISPER_MODEL` | Model size for speech recognition | base |
| `WHISPER_THREADS` | Threads for audio transcription | Auto |
| `WORKERS` | FastAPI worker processes | Number of CPU cores |
| `FFMPEG_THREADS` | Threads for video encoding | Auto |
| `VIDEO_CRF` | Video quality (0-51, lower is better) | 26 |
| `VIDEO_PRESET` | FFmpeg encoding speed preset | ultrafast |
| `AUDIO_BITRATE` | Audio quality | 192k |
| `MAX_CACHE_SIZE` | Maximum items in metadata cache | 100 |

### Quality vs Speed Trade-offs

For **Better Quality** (slower):
```
WHISPER_MODEL=small
VIDEO_PRESET=medium
VIDEO_CRF=23
```

For **Faster Processing** (lower quality):
```
WHISPER_MODEL=base
VIDEO_PRESET=ultrafast
VIDEO_CRF=30
```

For **Balanced Approach**:
```
WHISPER_MODEL=base
VIDEO_PRESET=veryfast
VIDEO_CRF=26
```

## Troubleshooting

### Common Issues

1. **Error: No space left on device**
   - Check disk space: `df -h`
   - Manually clean processed videos: `rm processed_videos/*.mp4`
   - Increase the cleanup frequency by lowering VIDEO_RETENTION_MINUTES

2. **Memory Issues/Container Crashes**
   - Lower `MAX_CONCURRENT_VIDEOS` to reduce memory usage
   - Use a smaller Whisper model: `WHISPER_MODEL=base`
   - Add memory limits to Docker: `docker compose up -d --memory=4g`

3. **Slow Video Generation**
   - Ensure you have at least 2 CPU cores available
   - Optimize video preset: Use `VIDEO_PRESET=ultrafast`
   - Lower video quality: Increase `VIDEO_CRF` to 28-30
   - Use an SSD instead of HDD for storage

4. **Missing Background Videos**
   - Error: "Background folder not found for gameplay type"
   - Solution: Create the appropriate directory in `background/` and add video files

5. **Files Not Being Cleaned Up**
   - Check permissions on the processed_videos directory
   - Restart the container to trigger a full cleanup

### Logs and Debugging

View logs with:
```bash
docker compose logs -f app
```

For more detailed logging, edit `app/logging_config.py` to set `DEBUG` level.

## Development and Contributing

### Local Development Setup

1. Set up a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Run with auto-reload for development:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

### Running Tests

```bash
pytest app/tests
```

### Contributing Guidelines

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Create a Pull Request

## License

MIT License

## Creator

Made by SamWolfs - Check me out at [https://glif.app/@appelsiensam](https://glif.app/@appelsiensam) 
