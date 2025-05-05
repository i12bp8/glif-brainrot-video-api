#!/bin/bash

# Set the API URL for Reddit video endpoint
API_URL="http://localhost:8000/api/v1/create-reddit-video"

# Send the request using curl
echo "Sending Reddit test request to $API_URL..."
curl -X POST \
  -H "Content-Type: application/json" \
  -d @sample-reddit-request.json \
  --silent \
  $API_URL | jq .

echo "Request sent. Check the response above." 