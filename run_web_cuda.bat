@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

rem Pin the CUDA-capable FFmpeg build. Explorer/shortcut PATH order can otherwise
rem select the non-CUDA MSYS2 build installed elsewhere on this machine.
set "FFMPEG_DIR=%USERPROFILE%\anaconda3\Library\bin"
set "VIDEO_FRAMES_FFMPEG=%FFMPEG_DIR%\ffmpeg.exe"
set "VIDEO_FRAMES_FFPROBE=%FFMPEG_DIR%\ffprobe.exe"

if not exist "%VIDEO_FRAMES_FFMPEG%" (
  echo ERROR: CUDA-capable ffmpeg not found: "%VIDEO_FRAMES_FFMPEG%"
  exit /b 1
)
if not exist "%VIDEO_FRAMES_FFPROBE%" (
  echo ERROR: matching ffprobe not found: "%VIDEO_FRAMES_FFPROBE%"
  exit /b 1
)

set "PATH=%FFMPEG_DIR%;%PATH%"

set "VENV_DIR=%SCRIPT_DIR%.venv"
set "PY_EXE=%VENV_DIR%\Scripts\python.exe"
set "REQ_FILE=%SCRIPT_DIR%requirements.txt"
set "MARKER=%VENV_DIR%\.requirements.sha256"

if not exist "%PY_EXE%" (
  echo Creating venv at "%VENV_DIR%"...
  py -3 -m venv "%VENV_DIR%" || exit /b 1
)

"%PY_EXE%" -m ensurepip --upgrade >nul 2>nul
if exist "%VENV_DIR%\Lib\site-packages\~ip" rmdir /s /q "%VENV_DIR%\Lib\site-packages\~ip" >nul 2>nul
for /d %%D in ("%VENV_DIR%\Lib\site-packages\~ip-*.dist-info") do (
  if exist "%%D" rmdir /s /q "%%D" >nul 2>nul
)

if not exist "%REQ_FILE%" (
  echo ERROR: requirements file not found: "%REQ_FILE%"
  exit /b 1
)

for /f %%A in ('powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 \"%REQ_FILE%\").Hash"') do set "REQ_HASH=%%A"
set "NEED_INSTALL=1"
if exist "%MARKER%" (
  set /p "OLD_HASH="<"%MARKER%"
  if /i "!OLD_HASH!"=="!REQ_HASH!" set "NEED_INSTALL=0"
)

if "!NEED_INSTALL!"=="1" (
  echo Installing requirements...
  "%PY_EXE%" -m pip install --upgrade pip || exit /b 1
  "%PY_EXE%" -m pip install -r "%REQ_FILE%" || exit /b 1
  echo !REQ_HASH!>"%MARKER%"
)

set "VIDEO_FRAMES_DATA_DIR=%SCRIPT_DIR%web_data_cuda"
set "VIDEO_FRAMES_PORT=8003"
set "VIDEO_FRAMES_ENGINE=CUDA"

echo Serving CUDA web app on http://0.0.0.0:%VIDEO_FRAMES_PORT%
"%PY_EXE%" "%SCRIPT_DIR%web_app_cuda.py"
exit /b %ERRORLEVEL%
