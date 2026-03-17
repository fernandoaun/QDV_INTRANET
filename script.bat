@echo off
setlocal

REM ==========================================================
REM  Proyecto: qdv_salmuera
REM  Crea estructura + archivos vacíos
REM ==========================================================

set ROOT=qdv_salmuera

if exist "%ROOT%" (
  echo La carpeta "%ROOT%" ya existe. Cancelando para no pisar nada.
  exit /b 1
)

mkdir "%ROOT%"
mkdir "%ROOT%\assets"
mkdir "%ROOT%\config"
mkdir "%ROOT%\data"
mkdir "%ROOT%\utils"
mkdir "%ROOT%\ui"

REM Archivos raíz
type nul > "%ROOT%\run.py"
type nul > "%ROOT%\requirements.txt"

REM Config
type nul > "%ROOT%\config\settings.py"

REM Data
type nul > "%ROOT%\data\db.py"

REM Utils
type nul > "%ROOT%\utils\validators.py"

REM UI
type nul > "%ROOT%\ui\mainapp.py"
type nul > "%ROOT%\ui\produccion_window.py"
type nul > "%ROOT%\ui\graficos_window.py"

echo.
echo Estructura creada en: %CD%\%ROOT%
echo Recorda copiar el logo a: %ROOT%\assets\logo_qdv.png
echo.
pause
endlocal
