@echo off
setlocal
cd /d "%~dp0"
echo HimanshuDigitalTwin - local synthetic research demo
echo Open http://127.0.0.1:8000 after startup.
echo If dependencies are missing, run:
echo     python -m pip install -r backend\requirements.txt
echo.
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
if errorlevel 1 (
  echo.
  echo Startup failed. Confirm Python 3.11+ and install backend requirements.
  exit /b 1
)
