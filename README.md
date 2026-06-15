# ShiftGuard 2.0

Attendance Management System with PIN + Camera Photo, Salary Calculator, Network Security, and Website Blocking.

## Features

- **PIN + Camera Photo Check-in/out** - Employees take a photo when checking in/out
- **Admin Dashboard** - Complete control over employees, attendance, and settings
- **Multi-branch Support** - Manage multiple spa locations
- **Salary Calculator** - Auto-calculate monthly salaries with deductions for absences and late arrivals
- **Excel Reports** - Daily and monthly reports with photos
- **Network Security** - Block social media websites (TikTok, Facebook, Instagram, etc.)
- **Photo Management** - View and delete attendance photos
- **Theme Customizer** - Change colors, fonts, and dark/light mode

## Tech Stack

- Python 3.10+
- Flask (Backend)
- SQLite (Database)
- JavaScript + HTML/CSS (Frontend)
- Waitress/Gunicorn (Production Server)

## Installation

### Local Installation (Windows)

1. Create folder: `C:\ShiftGuard`
2. Copy all files into this folder
3. Open Command Prompt as Administrator
4. Run: `python -m venv venv`
5. Run: `venv\Scripts\pip install -r requirements.txt`
6. Run: `venv\Scripts\python init_db.py`
7. Run: `venv\Scripts\python app.py`
8. Open browser to: `http://localhost:5000/admin`
9. Login: `admin / admin123`

### Install as Windows Service

Run `install_service.bat` as Administrator

## Deployment

Deploy to Render, Railway, or PythonAnywhere:

1. Push this repository to GitHub
2. Connect to your hosting platform
3. Set Build Command: `pip install -r requirements.txt`
4. Set Start Command: `gunicorn app:app`
5. Add environment variable: `SECRET_KEY`

## Default Login

- **Username:** `admin`
- **Password:** `admin123`
- **⚠️ Change this password immediately after first login!**

## URLs

- Admin Dashboard: `/admin`
- Employee Kiosk: `/kiosk`
- Login: `admin / admin123`

## License

MIT License - Free for personal and commercial use

## Author

MySpa - Employee Attendance System
