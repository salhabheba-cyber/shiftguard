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
8. Open browser to: `http://localhost:5000` and click **Account** (top right)
9. Sign in:
   - **As the owner** with `owner@shiftguard.app` / `owner12345` → **Owner Dashboard** (you're asked to change this password)
   - **As the first business** with `admin` / `admin123` → **Kiosk** or **Admin Dashboard**

### Install as Windows Service

Run `install_service.bat` as Administrator

## Deployment

Deploy to Render, Railway, or PythonAnywhere:

1. Push this repository to GitHub
2. Connect to your hosting platform
3. Set Build Command: `pip install -r requirements.txt`
4. Set Start Command: `gunicorn app:app`
5. Add environment variables:
   - `SECRET_KEY`: a long random string (if missing, one is generated and stored in `data/`)
   - `OWNER_EMAIL` / `OWNER_PASSWORD`: your owner login (only used the first time the app starts)
   - `LEGACY_ACCOUNT_NAME`: name for the first business account (default `MySpa`)
6. Keep the `data/` folder on persistent storage (e.g. a Railway volume) so accounts survive redeploys

## Accounts

ShiftGuard hosts many businesses. Each business account has its own database
file, so one business can never see another's employees, attendance or photos.

- **Owner** (you): signs in on the home page and gets the Owner Dashboard:
  every account with live numbers, sign-up requests to approve or reject,
  new accounts, suspend/activate, reset a business admin's password, open any
  account's admin dashboard or kiosk, and a log of sign-ins and changes.
- **Businesses**: request an account on the home page (**Account → Create
  account**). Once you approve it they sign in with their email and password
  and choose Kiosk or Admin Dashboard.
- **The original business**: the database that existed before accounts
  (`data/shiftguard.db`) becomes the first account, unchanged.

Where data lives:

| What | Where |
|---|---|
| Account list, owner login, activity | `data/platform.db` |
| Original business | `data/shiftguard.db`, photos in `static/photos/` |
| Other businesses | `data/accounts/<name>.db`, photos in `static/photos/a/<name>/` |
| Deleted accounts | moved to `data/archive/` (not destroyed) |

## Default Logins

- **Owner:** `owner@shiftguard.app` / `owner12345`
- **First business:** `admin` / `admin123`
- **⚠️ Change both passwords immediately after first login!**

## URLs

- Home page and sign-in: `/`
- Owner Dashboard: `/owner`
- Admin Dashboard: `/admin`
- Employee Kiosk: `/kiosk`

## License

MIT License - Free for personal and commercial use

## Author

MySpa - Employee Attendance System
