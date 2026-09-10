@echo off
setlocal
cd /d "%~dp0"
title Centro Operativo

color 0A
set "CODEX_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%CODEX_PYTHON%" goto :python_missing
echo.
curl.exe -fsS --max-time 1 http://127.0.0.1:8000/health >nul 2>nul
if not errorlevel 1 goto :open_page

echo Iniciando el servidor de Centro Operativo...
start "Centro Operativo - Servidor" "%CODEX_PYTHON%" "%~dp0app\local_server.py"
timeout /t 2 /nobreak >nul

:open_page
echo Abriendo Centro Operativo en el navegador...
start "" "http://localhost:8000"
exit /b 0

:python_missing
echo No se encontro el componente local necesario.
echo Vuelva a abrir el proyecto desde Codex e intentelo nuevamente.
pause
exit /b 1
