@echo off
rem Starts Video Prep Studio. Finds Python even when it is not on PATH.
cd /d "%~dp0"
set "PY="

py -c "import sys" >nul 2>nul && set "PY=py"
if not defined PY (python -c "import sys" >nul 2>nul && set "PY=python")
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Python\pythoncore-*") do if exist "%%D\python.exe" set "PY=%%D\python.exe"
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PY=%%D\python.exe"

if not defined PY (
  echo Could not find Python. Install it from https://www.python.org/downloads/ and try again.
  pause
  exit /b 1
)

"%PY%" -c "import fastapi, uvicorn, matplotlib, dotenv, requests, multipart" >nul 2>nul
if errorlevel 1 (
  echo Installing the packages this app needs. This happens once...
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo Package install failed. See the messages above.
    pause
    exit /b 1
  )
)

"%PY%" app.py
if errorlevel 1 pause
