#!/bin/bash

# Set the API URL (modify as needed)
API_URL="http://localhost:8000/api/v1/create-video"

# Send the request using curl
echo "Sending test request to $API_URL..."
curl -X POST \
  -H "Content-Type: application/json" \
  -d @sample-request.json \
  --silent \
  $API_URL | jq .

echo "Request sent. Check the response above." 