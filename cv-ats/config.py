import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# On Railway, mount a volume at /data and set DATA_DIR=/data so the database
# and uploaded CVs survive redeploys.
DATA_DIR = os.getenv('DATA_DIR', os.path.join(BASE_DIR, 'data'))
UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')
DATABASE_PATH = os.path.join(DATA_DIR, 'ats.db')

for d in (DATA_DIR, UPLOAD_DIR):
    os.makedirs(d, exist_ok=True)

SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-in-production')
# Leave empty to disable the login screen (only do that locally).
APP_PASSWORD = os.getenv('APP_PASSWORD', '')

ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
CLAUDE_MODEL = os.getenv('AI_MODEL', 'claude-opus-5')
# low | medium | high | xhigh | max — lower is cheaper/faster.
CLAUDE_EFFORT = os.getenv('AI_EFFORT', 'high')

# How many CVs are analysed in parallel.
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 3))
MAX_UPLOAD_MB = int(os.getenv('MAX_UPLOAD_MB', 100))
PORT = int(os.getenv('PORT', 5000))

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt', 'rtf', 'png', 'jpg', 'jpeg', 'webp'}
