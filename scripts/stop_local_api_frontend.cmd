@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Stop API + Frontend started locally (without Docker)
REM Usage: scripts\stop_local_api_frontend.cmd

if "%API_PORT%"=="" set "API_PORT=8080"
if "%FRONTEND_PORT%"=="" set "FRONTEND_PORT=5173"

set "STOPPED_ANY=0"

call :stop_port "%API_PORT%" "API"
call :stop_port "%FRONTEND_PORT%" "Frontend"

if "%STOPPED_ANY%"=="1" (
  echo [OK] Local API + frontend stop completed.
) else (
  echo [INFO] Nothing to stop.
)

exit /b 0

:stop_port
set "PORT=%~1"
set "NAME=%~2"
set "FOUND=0"

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":%PORT% .*LISTENING"') do (
  set "FOUND=1"
  echo [INFO] Stopping %NAME% listener on port %PORT% (PID %%P)...
  taskkill /PID %%P /T /F >nul 2>nul
)

if "%FOUND%"=="1" (
  set "STOPPED_ANY=1"
  echo [OK] %NAME% stopped on port %PORT%.
) else (
  echo [INFO] %NAME% is not listening on port %PORT%.
)

exit /b 0
