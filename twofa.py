"""Shared TOTP (RFC 6238) two-factor auth helpers, used by both the owner
login (accounts.py / owners table) and business admin logins
(database.py / admin_users table, one per account). Backup codes are
stored as salted hashes, never in plain text — they're shown to the user
exactly once, at generation time."""
import pyotp
import secrets
import hashlib
import json

ISSUER = 'ShiftGuard'

def generate_secret():
    return pyotp.random_base32()

def otpauth_url(secret, label):
    return pyotp.TOTP(secret).provisioning_uri(name=label, issuer_name=ISSUER)

def verify_code(secret, code):
    if not secret or not code:
        return False
    try:
        return pyotp.TOTP(secret).verify(str(code).strip(), valid_window=1)
    except Exception:
        return False

def _hash_code(code):
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()

def generate_backup_codes(n=8):
    """Returns (plain_codes_to_show_once, json_to_store)."""
    plain  = [secrets.token_hex(4) for _ in range(n)]
    hashed = [_hash_code(c) for c in plain]
    return plain, json.dumps(hashed)

def consume_backup_code(stored_json, code):
    """If `code` matches one of the stored (hashed) backup codes, returns the
    updated JSON with that code removed. Returns None if there's no match."""
    if not stored_json or not code:
        return None
    try:
        hashes = json.loads(stored_json)
    except (ValueError, TypeError):
        return None
    h = _hash_code(code)
    if h in hashes:
        hashes.remove(h)
        return json.dumps(hashes)
    return None
