@echo off
echo ============================================
echo  ShiftGuard - Windows Service Installer
echo ============================================
cd /d %~dp0
echo Installing packages...
venv\Scripts\pip.exe install -r requirements.txt --quiet
echo Initializing database...
venv\Scripts\python.exe init_db.py
echo Installing service...
nssm install ShiftGuard "%~dp0venv\Scripts\python.exe" "%~dp0app.py"
nssm set ShiftGuard AppDirectory "%~dp0"
nssm set ShiftGuard Start SERVICE_AUTO_START
nssm set ShiftGuard DisplayName "ShiftGuard Attendance System"
nssm start ShiftGuard
echo ============================================
echo  Done! Open: http://localhost:5000/kiosk
echo  Admin:      http://localhost:5000/admin
echo ============================================
pause
