@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "run.py" (
  echo ERROR: run.py no encontrado. Este .bat debe estar en la carpeta project_web.
  pause
  exit /b 1
)
python -m pip install -r requirements.txt
if not exist ".env" (
  echo Creando .env desde .env.example ...
  copy /Y .env.example .env
)
python -m alembic upgrade head
echo.
echo Si no podes entrar: lee COMO_ENTRAR.txt y usa CREAR_USUARIO_ADMIN.bat
echo Servidor: http://127.0.0.1:5000  (o el puerto en PORT del .env)
echo Ctrl+C para detener.
echo.
python run.py
pause
