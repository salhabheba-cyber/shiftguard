import os

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, 'data')
LOGS_DIR    = os.path.join(BASE_DIR, 'logs')
BACKUP_DIR  = os.path.join(BASE_DIR, 'backup')
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')
PHOTOS_DIR  = os.path.join(BASE_DIR, 'static', 'photos')

for d in [DATA_DIR, LOGS_DIR, BACKUP_DIR, REPORTS_DIR, PHOTOS_DIR]:
    os.makedirs(d, exist_ok=True)

# The original single-business database. It is kept exactly where it was and
# becomes the first account on the platform, so none of its data moves.
DATABASE_PATH = os.path.join(DATA_DIR, 'shiftguard.db')
# Platform-level data: the list of accounts and the owner login.
PLATFORM_DB_PATH = os.path.join(DATA_DIR, 'platform.db')
# Every other account gets its own database file here.
ACCOUNTS_DIR  = os.path.join(DATA_DIR, 'accounts')
ARCHIVE_DIR   = os.path.join(DATA_DIR, 'archive')
os.makedirs(ACCOUNTS_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)
# Name given to the original business when it becomes the first account.
LEGACY_ACCOUNT_NAME = os.getenv('LEGACY_ACCOUNT_NAME', 'MySpa')
# First owner login. Set OWNER_EMAIL / OWNER_PASSWORD in the environment to
# choose your own; otherwise the defaults below are used and the owner
# dashboard asks you to change the password on first sign-in.
OWNER_EMAIL    = os.getenv('OWNER_EMAIL', 'owner@shiftguard.app')
OWNER_PASSWORD = os.getenv('OWNER_PASSWORD', 'owner12345')
# Set OWNER_RESET=1 to force the already-stored owner login to match
# OWNER_EMAIL/OWNER_PASSWORD on next boot, then turn it back off.
OWNER_RESET    = os.getenv('OWNER_RESET', '').strip().lower() in ('1', 'true', 'yes')
# One-time seed for the FaceFit Studio business account. Set SEED_FACEFIT=1
# plus FACEFIT_ADMIN_PASSWORD (and optionally FACEFIT_ADMIN_EMAIL) to create
# it on next boot; it's skipped if that email is already registered. Turn
# SEED_FACEFIT back off once it's created.
SEED_FACEFIT          = os.getenv('SEED_FACEFIT', '').strip().lower() in ('1', 'true', 'yes')
FACEFIT_ADMIN_EMAIL    = os.getenv('FACEFIT_ADMIN_EMAIL', 'facefit@shiftguard.app')
FACEFIT_ADMIN_PASSWORD = os.getenv('FACEFIT_ADMIN_PASSWORD', '')
LOG_FILE      = os.path.join(LOGS_DIR, 'system.log')
LEGAL_UPDATED = 'November 13, 2026'

def _secret_key():
    """SECRET_KEY from the environment, else a random key generated once and
    kept in data/. (A key written in the source code would let anyone who has
    read the code forge a signed-in session.)"""
    env = os.getenv('SECRET_KEY')
    if env: return env
    path = os.path.join(DATA_DIR, '.secret_key')
    try:
        with open(path) as f:
            key = f.read().strip()
            if key: return key
    except FileNotFoundError:
        pass
    import secrets
    key = secrets.token_hex(32)
    with open(path, 'w') as f: f.write(key)
    return key

SECRET_KEY    = _secret_key()
PORT          = int(os.getenv('PORT', 5000))
HOST          = '0.0.0.0'
DEBUG         = False

LATE_THRESHOLD_MINUTES = 10
PIN_LENGTH             = 4
SESSION_HOURS          = 8
PHOTO_MAX_MB           = 5
# Check-in/out photos older than this are auto-deleted once a day (roughly
# "monthly" at the 30-day default). Adjustable in Admin → Settings.
DEFAULT_PHOTO_RETENTION_DAYS = 30

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
    'primary':   'FF6A00',
    'secondary': 'EEF3FB',
    'accent':    'FF8A1F',
    'dark':      '0A1633',
    'text':      '0F1B3D',
    'font':      'Inter',
    'logo_text': 'ShiftGuard',
    'dark_mode': '0',
    'logo_url':  '',
}
