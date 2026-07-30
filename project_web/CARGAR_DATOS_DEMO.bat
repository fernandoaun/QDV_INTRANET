@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "run.py" (
  echo ERROR: run.py no encontrado. Este .bat debe estar en la carpeta project_web.
  pause
  exit /b 1
)
echo Aplicando migraciones...
python -m alembic upgrade head
if errorlevel 1 (
  echo ERROR al aplicar migraciones.
  pause
  exit /b 1
)
echo.
echo Cargando datos de demostracion local...
python -m flask --app run seed-demo --password "demo123"
if errorlevel 1 (
  echo ERROR al cargar datos demo.
  pause
  exit /b 1
)
echo.
echo Usuarios tipicos: admin, demo_ops, demo_log, demo_adm, demo_mant, demo_sgi
echo Contraseña (solo usuarios nuevos): demo123
echo.
pause
