@echo off
chcp 65001 >nul
cd /d "%~dp0"
title QDV - Usuario API OpenClaw
echo.
echo  Crea un usuario Angel de fallback (sin cabecera WhatsApp).
echo  El bot identifica a cada operador por el número en Admin → Usuarios.
echo  Corre contra la base LOCAL (SQLite). En Render usá el Shell del web service.
echo.
python -m alembic upgrade head
python -m flask --app run create-openclaw-bot
echo.
echo  Después: definí API_BEARER_TOKEN en project_web\.env (local) o Environment de Render.
echo  Usá el MISMO valor en openclaw\.env como QDV_API_BEARER_TOKEN.
echo  Vinculá el WhatsApp de cada usuario en Admin. API_BEARER_USER_ID es opcional.
echo.
pause
