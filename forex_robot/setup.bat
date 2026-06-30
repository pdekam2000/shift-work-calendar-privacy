@echo off
echo ============================================
echo   نصب Robot 1 — فارکس تمام‌اتوماتیک
echo ============================================
echo.

echo [1] بررسی Python...
python --version 2>nul || (echo Python پیدا نشد! از python.org نصب کنید. & pause & exit)

echo [2] نصب کتابخانه‌ها...
pip install -r requirements.txt

echo [3] تست سریع...
python robot1.py --signal

echo.
echo ============================================
echo   نصب کامل شد!
echo   برای شروع: python robot1.py
echo ============================================
pause
