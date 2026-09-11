@echo off
chcp 65001 >nul
cd /d "%~dp0"
title QDV - Vincular WhatsApp (QR)
echo.
echo  Escaneá el QR con el celular del BOT:
echo  WhatsApp → Dispositivos vinculados → Vincular dispositivo
echo  No es WhatsApp Business. Usá un número aparte, no el personal de planta.
echo.
docker compose exec -it -u node openclaw openclaw channels login --channel whatsapp
if errorlevel 1 (
  echo.
  echo  Si no existe el comando openclaw, probá:
  echo    docker compose exec -it -u node openclaw node /app/openclaw.mjs channels login --channel whatsapp
  pause
  exit /b 1
)
echo.
echo  Listo. Escribile al número vinculado desde un celular de QDV_WHATSAPP_ALLOW_FROM.
pause
