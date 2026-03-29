@echo off
chcp 65001 >nul
cd /d "%~dp0"
title QDV - Cambiar clave
cls
echo.
echo  Usuarios que existen en esta base de datos:
echo.
python -m flask --app run list-users
echo.
set /p NOMBRE="Escribi el USUARIO de la lista (ejemplo: admin) y apreta Enter: "
if "%NOMBRE%"=="" (
  echo No escribiste nada. Cerrando.
  pause
  exit /b 1
)
echo.
echo  Te va a pedir la NUEVA clave dos veces.
echo.
python -m flask --app run reset-password %NOMBRE%
echo.
pause
