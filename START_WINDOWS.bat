@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title VIREO V8 - Auto Train and Start

echo ================================================
echo VIREO V8 - 200.000 GIAO DICH - IF + PYOD ECOD
echo ================================================

echo [1/5] Kiem tra moi truong Python...
if not exist ".venv\Scripts\python.exe" (
  py -3.13 --version >nul 2>&1
  if errorlevel 1 (
    py -m venv .venv
  ) else (
    py -3.13 -m venv .venv
  )
)

if not exist ".venv\Scripts\python.exe" (echo LOI: Khong tao duoc moi truong Python. Kiem tra lenh py --version. & pause & exit /b 1)

echo [2/5] Kiem tra va cai thu vien...
.venv\Scripts\python.exe -m pip install --only-binary=:all: -r backend\requirements-py313.txt
if errorlevel 1 .venv\Scripts\python.exe -m pip install --only-binary=:all: -r backend\requirements.txt
if errorlevel 1 (echo LOI: Cai thu vien that bai. Python 3.13 duoc khuyen dung neu 3.15 khong tuong thich. & pause & exit /b 1)
.venv\Scripts\python.exe -c "from pyod.models.ecod import ECOD; from sklearn.ensemble import IsolationForest; print('PyOD + IF OK')"
if errorlevel 1 (echo LOI: Khong import duoc mo hinh & pause & exit /b 1)

echo [3/5] Kiem tra mo hinh va nguong F1 Validation...
.venv\Scripts\python.exe backend\check_models.py
if errorlevel 1 (
  echo [4/5] Chua co mo hinh hop le. Tu dong huan luyen tren CSV GOC 200000 dong...
  if not exist "Bank_Transaction_Fraud_Detection.csv" (echo LOI: Thieu CSV 200000 dong & pause & exit /b 1)
  .venv\Scripts\python.exe backend\train.py --csv Bank_Transaction_Fraud_Detection.csv
  if errorlevel 1 (echo LOI: Huan luyen khong thanh cong. Xem thong bao o tren. & pause & exit /b 1)
  .venv\Scripts\python.exe backend\check_models.py
  if errorlevel 1 (echo LOI: Mo hinh hoac thong tin F1 sau huan luyen khong hop le. Backend KHONG khoi dong. & pause & exit /b 1)
) else (
  echo [4/5] Da co mo hinh dung. KHONG huan luyen lai.
)

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8013 -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 (echo LOI: Cong 8013 dang duoc su dung. Dong server cu tren cong nay roi chay lai. & pause & exit /b 1)
echo [5/5] Mo website tai http://127.0.0.1:8013
start "" /b ".venv\Scripts\python.exe" backend\open_browser.py
.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8013
if errorlevel 1 (echo LOI: Khong khoi dong duoc server. Kiem tra port 8013. & pause & exit /b 1)
pause
