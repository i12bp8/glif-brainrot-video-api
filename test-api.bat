@echo off
setlocal

:: Set the API URL (modify as needed)
set API_URL=http://localhost:8000/api/v1/create-video

:: Send the request using curl
echo Sending test request to %API_URL%...
curl -X POST ^
  -H "Content-Type: application/json" ^
  -d @sample-request.json ^
  %API_URL%

echo.
echo Request sent. Check the response above.
pause 