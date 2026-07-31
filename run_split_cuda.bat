@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "VENV_DIR=%SCRIPT_DIR%.venv"
set "PY_EXE=%VENV_DIR%\Scripts\python.exe"
set "REQ_FILE=%SCRIPT_DIR%requirements.txt"
set "MARKER=%VENV_DIR%\.requirements.sha256"

if not exist "%PY_EXE%" (
  echo Creating venv at "%VENV_DIR%"...
  py -3 -m venv "%VENV_DIR%" || exit /b 1
)

rem Keep the CUDA side flow aligned with the main environment setup.
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

if not exist "%SCRIPT_DIR%input_cuda" mkdir "%SCRIPT_DIR%input_cuda"
if not exist "%SCRIPT_DIR%output_cuda" mkdir "%SCRIPT_DIR%output_cuda"
if not exist "%SCRIPT_DIR%archive_cuda" mkdir "%SCRIPT_DIR%archive_cuda"

"%PY_EXE%" "%SCRIPT_DIR%split_videos_to_frames_cuda.py" --timestamp-names %*
exit /b %ERRORLEVEL%
