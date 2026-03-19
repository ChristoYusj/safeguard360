@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"
echo Creating directories in: %CD%

REM Backend directories
mkdir backend\app\config 2>nul
mkdir backend\app\api 2>nul
mkdir backend\app\websocket 2>nul
mkdir backend\app\models 2>nul
mkdir backend\app\db 2>nul
mkdir backend\app\services 2>nul
mkdir backend\app\camera 2>nul
mkdir backend\app\inference 2>nul
mkdir backend\app\pipeline 2>nul
mkdir backend\app\decision 2>nul
mkdir backend\app\actuator 2>nul
mkdir backend\app\utils 2>nul
mkdir backend\tests 2>nul

REM Frontend directories
mkdir frontend\src\components\layout 2>nul
mkdir frontend\src\components\common 2>nul
mkdir frontend\src\components\live 2>nul
mkdir frontend\src\components\attendance 2>nul
mkdir frontend\src\components\events 2>nul
mkdir frontend\src\components\alerts 2>nul
mkdir frontend\src\components\enrollment 2>nul
mkdir frontend\src\pages 2>nul
mkdir frontend\src\hooks 2>nul
mkdir frontend\src\services 2>nul
mkdir frontend\src\context 2>nul
mkdir frontend\src\utils 2>nul
mkdir frontend\public 2>nul

REM Other directories
mkdir data\models 2>nul
mkdir data\faces 2>nul
mkdir data\snapshots 2>nul
mkdir data\videos 2>nul
mkdir scripts 2>nul
mkdir docs 2>nul
mkdir tests\test_data 2>nul

echo.
echo All directories created successfully!
pause
