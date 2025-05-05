FROM python:3.11-slim

WORKDIR /app

# Install system dependencies with optimized FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1-mesa-glx \
    pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy all files
COPY . .

# Install dependencies in an optimized order
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "numpy==1.26.1" "Pillow==10.1.0" "opencv-python-headless==4.8.1.78"

# Install torch with CPU-only support for Whisper
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    "torch==2.1.1+cpu" "torchaudio==2.1.1+cpu"

# Install Whisper AI for audio transcription
RUN pip install --no-cache-dir "openai-whisper==20231117" "whisper-timestamped==1.15.8"

# Install FastAPI and other core dependencies
RUN pip install --no-cache-dir "fastapi==0.104.1" "uvicorn[standard]==0.23.2" \
    "python-multipart==0.0.6" "httpx==0.25.1" "pydantic==2.4.2" \
    "ffmpeg-python==0.2.0" "python-dotenv==1.0.0" "watchdog==3.0.0" \
    "moviepy==1.0.3" "decorator==4.4.2"

# Create required directories
RUN mkdir -p processed_videos/temp

# Expose port
EXPOSE 8000

# Use a custom entry point script to calculate optimal workers
COPY ./start.sh /start.sh
RUN chmod +x /start.sh

# Command to run the application with auto worker scaling
ENTRYPOINT ["/start.sh"] 