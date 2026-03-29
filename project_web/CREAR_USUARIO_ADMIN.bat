@echo off
chcp 65001 >nul
cd /d "%~dp0"
title QDV - Crear usuario admin
cls
echo.
echo  ============================================================
echo    CREAR USUARIO: admin
echo    Te va a pedir la CLAVE dos veces (no se ve al escribir).
echo    Si dice que admin ya existe, usa CAMBIAR_CLAVE.bat
echo  ============================================================
echo.
python -m alembic upgrade head
echo.
python -m flask --app run create-admin admin
if errorlevel 1 (
  echo.
  echo  *** Si dijo que admin ya existe: cerrá esta ventana y abrí CAMBIAR_CLAVE.bat ***
  goto fin
)
echo.
echo  ------------------------------------------------------------
echo   LISTO: usuario = admin    clave = la que escribiste arriba
echo   Ahora ejecutá iniciar_local.bat y entrá en el navegador.
echo  ------------------------------------------------------------
:fin
echo.
pause
