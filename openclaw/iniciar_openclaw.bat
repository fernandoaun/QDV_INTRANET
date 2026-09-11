@echo off
chcp 65001 >nul
cd /d "%~dp0"
title QDV - OpenClaw + WhatsApp
echo.
echo  ============================================================
echo    OpenClaw (gateway nativo de WhatsApp)
echo    No usa WhatsApp Business. No usa DATABASE_URL.
echo  ============================================================
echo.
python scripts\check_setup.py
if errorlevel 2 (
  echo.
  echo  *** Sacá DATABASE_URL de openclaw\.env ***
  pause
  exit /b 2
)
if errorlevel 1 (
  echo.
  echo  *** Completá openclaw\.env y volvé a ejecutar este .bat ***
  pause
  exit /b 1
)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1"
if errorlevel 1 (
  echo.
  echo  *** Falló Docker. ¿Está Docker Desktop iniciado? ***
  pause
  exit /b 1
)
echo.
echo  Control UI: http://127.0.0.1:18789/
echo  Después: whatsapp_login.bat
echo.
pause
