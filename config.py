import os

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, 'data')
LOGS_DIR    = os.path.join(BASE_DIR, 'logs')
BACKUP_DIR  = os.path.join(BASE_DIR, 'backup')
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')
PHOTOS_DIR  = os.path.join(BASE_DIR, 'static', 'photos')

for d in [DATA_DIR, LOGS_DIR, BACKUP_DIR, REPORTS_DIR, PHOTOS_DIR]:
    os.makedirs(d, exist_ok=True)

DATABASE_PATH = os.path.join(DATA_DIR, 'shiftguard.db')
LOG_FILE      = os.path.join(LOGS_DIR, 'system.log')
SECRET_KEY    = os.getenv('SECRET_KEY', 'shiftguard-2026-secret-key!')
PORT          = int(os.getenv('PORT', 5000))
HOST          = '0.0.0.0'
DEBUG         = False

LATE_THRESHOLD_MINUTES = 10
PIN_LENGTH             = 4
SESSION_HOURS          = 8
PHOTO_MAX_MB           = 5

# ── SALARY CALCULATION ─────────────────────────────────────────────────────
# How much of an employee's per-minute rate is deducted for each minute they
# arrive late. 1.0 = full/accurate rate (10 min late = 10 min of pay lost).
# Lower it (e.g. 0.5) to only dock half rate as a leniency policy.
LATE_DEDUCTION_FACTOR  = 1.0
# Pay multiplier applied to overtime hours (1.5 = time-and-a-half).
OVERTIME_MULTIPLIER    = 1.5

# ── LEAVE TYPES (seeded once; fully editable afterwards in Admin → Leave) ──
# (name, is_paid) — Annual Leave and Sick Leave default to PAID, but every
# type's paid/unpaid flag can be changed per-business in the dashboard.
DEFAULT_LEAVE_TYPES = [
    ('Annual Leave',      1),
    ('Sick Leave',        1),
    ('Unpaid Leave',      0),
    ('Personal / Other',  0),
]

DEFAULT_BLOCKED_SITES = [
    ('tiktok.com',    'social_media'),
    ('facebook.com',  'social_media'),
    ('instagram.com', 'social_media'),
    ('youtube.com',   'video'),
    ('whatsapp.com',  'messaging'),
    ('netflix.com',   'entertainment'),
    ('reddit.com',    'social_media'),
    ('twitter.com',   'social_media'),
    ('x.com',         'social_media'),
    ('snapchat.com',  'social_media'),
    ('twitch.tv',     'entertainment'),
]

DEFAULT_THEME = {
    'primary':   '00A8A8',
    'secondary': 'E8F8F8',
    'accent':    '2ab3b8',
    'dark':      '1c3a3b',
    'text':      '2d4a4b',
    'font':      'Segoe UI',
    'logo_text': 'ShiftGuard',
    'dark_mode': '0',
}
