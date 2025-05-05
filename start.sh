#!/bin/bash

# Get environment variables with defaults
PORT=${PORT:-8000}
WORKERS=${WORKERS:-0}

# Calculate optimal worker count if set to auto or 0
if [ "$WORKERS" = "auto" ] || [ "$WORKERS" = "0" ]; then
    # Get CPU count
    CPU_COUNT=$(nproc)
    
    # Use all available CPUs
    WORKERS=$CPU_COUNT
    
    echo "Auto-configured $WORKERS workers based on $CPU_COUNT CPU cores"
fi

echo "Starting server with $WORKERS workers on port $PORT"

# Run the application
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers $WORKERS 