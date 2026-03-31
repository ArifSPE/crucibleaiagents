@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Start API + Frontend locally (without Docker)
REM Usage: scripts\start_local_api_frontend.cmd

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
set "LOG_DIR=%PROJECT_ROOT%\logs"
set "API_LOG=%LOG_DIR%\api-local.log"
set "FRONTEND_LOG=%LOG_DIR%\frontend-local.log"

if "%API_HOST%"=="" set "API_HOST=0.0.0.0"
if "%API_PORT%"=="" set "API_PORT=8080"
if "%FRONTEND_HOST%"=="" set "FRONTEND_HOST=0.0.0.0"
if "%FRONTEND_PORT%"=="" set "FRONTEND_PORT=5173"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm is required but was not found in PATH.
  exit /b 1
)

set "PYTHON_CMD=python"
if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
  set "PYTHON_CMD=%PROJECT_ROOT%\.venv\Scripts\python.exe"
)

"%PYTHON_CMD%" -c "import uvicorn" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] uvicorn is not available in %PYTHON_CMD%
  echo [INFO] Install backend deps first: %PYTHON_CMD% -m pip install -r requirements.txt
  exit /b 1
)

if exist "%PROJECT_ROOT%\.env" (
  for /f "usebackq tokens=* delims=" %%A in ("%PROJECT_ROOT%\.env") do (
    set "line=%%A"
    if not "!line!"=="" if not "!line:~0,1!"=="#" set "!line!"
  )
)

if not exist "%PROJECT_ROOT%\frontend\node_modules" (
  echo [INFO] Installing frontend dependencies...
  pushd "%PROJECT_ROOT%\frontend"
  call npm install
  if errorlevel 1 (
    popd
    echo [ERROR] npm install failed.
    exit /b 1
  )
  popd
)

echo [INFO] Starting API locally on http://localhost:%API_PORT%
start "Local API" cmd /k "cd /d "%PROJECT_ROOT%\api" && "%PYTHON_CMD%" -m uvicorn main:app --host %API_HOST% --port %API_PORT% --reload 1>>"%API_LOG%" 2>&1"

echo [INFO] Starting frontend locally on http://localhost:%FRONTEND_PORT%
start "Local Frontend" cmd /k "cd /d "%PROJECT_ROOT%\frontend" && set VITE_API_BASE_URL=http://localhost:%API_PORT% && npm run dev -- --host %FRONTEND_HOST% --port %FRONTEND_PORT% 1>>"%FRONTEND_LOG%" 2>&1"

echo.
echo [OK] API and frontend launch commands were started in separate windows.
echo [INFO] API:      http://localhost:%API_PORT%
echo [INFO] Frontend: http://localhost:%FRONTEND_PORT%
echo [INFO] Logs:     %API_LOG% and %FRONTEND_LOG%
echo.

exit /b 0
