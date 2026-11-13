"""ShiftGuard platform: business accounts, the owner login and sign-in lookup.

Each business account has its own SQLite database (see database.py). This
module keeps the platform-level records in a separate file
(config.PLATFORM_DB_PATH):

  accounts     one row per business, with where its data lives and its status
  owners       the platform owner login(s)
  login_index  every account admin's username/email -> account, so the home
               page can find which account a sign-in belongs to
  platform_log sign-ins and owner actions
"""
import os, re, shutil, sqlite3, logging, secrets
from contextlib import contextmanager
from datetime import datetime, date, timedelta
import config, database

logger = logging.getLogger('shiftguard')

STATUSES = ('active', 'suspended', 'pending', 'rejected', 'deleted')

@contextmanager
def _db():
    conn = sqlite3.connect(config.PLATFORM_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _q(sql, p=()):
    with _db() as c:
        return [dict(r) for r in c.execute(sql, p).fetchall()]

def _run(sql, p=()):
    with _db() as c:
        return c.execute(sql, p).lastrowid

def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def _table_columns(table):
    return {r['name'] for r in _q(f'PRAGMA table_info({table})')}

def _ensure_columns(table, coldefs):
    """Add any missing columns to `table`. Never drops or modifies existing data."""
    existing = _table_columns(table)
    missing  = [(n, d) for n, d in coldefs if n not in existing]
    if not missing: return
    with _db() as c:
        for name, decl in missing:
            c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {decl}')

# ══════════════════════════════════════════════════════════════════════════════
# SETUP
# ══════════════════════════════════════════════════════════════════════════════
def init_platform():
    """Create platform tables, register the original database as the first
    account, create the first owner, and rebuild the sign-in index."""
    with _db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS accounts (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL,
            slug           TEXT UNIQUE NOT NULL,
            status         TEXT NOT NULL DEFAULT 'active',
            db_file        TEXT,            -- relative to DATA_DIR
            photo_dir      TEXT NOT NULL,   -- relative to static/
            contact_name   TEXT,
            contact_email  TEXT,
            phone          TEXT,
            signup_pw_hash TEXT,            -- only while a sign-up request is pending
            notes          TEXT,
            signup_ip      TEXT,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at    TIMESTAMP,
            last_activity  TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS owners (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT UNIQUE NOT NULL,
            name          TEXT,
            password_hash TEXT NOT NULL,
            must_change   INTEGER DEFAULT 0,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login    TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS login_index (
            account_id INTEGER NOT NULL,
            username   TEXT NOT NULL,
            email      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_login_email ON login_index (lower(email));
        CREATE INDEX IF NOT EXISTS idx_login_user  ON login_index (username);
        CREATE TABLE IF NOT EXISTS platform_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            event      TEXT NOT NULL,
            actor      TEXT,
            account_id INTEGER,
            ip         TEXT,
            details    TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS password_resets (
            token      TEXT PRIMARY KEY,
            kind       TEXT NOT NULL,   -- 'owner' | 'account'
            ref        TEXT NOT NULL,   -- owner id, or account id (kind='account')
            username   TEXT,            -- admin_users.username, only for kind='account'
            expires_at TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')
    _ensure_columns('owners', [
        ('totp_secret',  'TEXT'),
        ('totp_enabled', 'INTEGER DEFAULT 0'),
        ('backup_codes', 'TEXT'),
    ])
    _ensure_columns('accounts', [
        ('stripe_customer_id',     'TEXT'),
        ('stripe_subscription_id', 'TEXT'),
        ('subscription_status',    'TEXT'),   # NULL | trialing | active | past_due | canceled
        ('trial_ends_at',          'TEXT'),
    ])
    is_new_flag = 'free_forever' not in _table_columns('accounts')
    _ensure_columns('accounts', [('free_forever', 'INTEGER DEFAULT 0')])
    if is_new_flag:
        # Grandfather in every account that already existed the moment this
        # flag was introduced — new accounts created from now on default to
        # payable (free_forever=0) unless the owner opts one in.
        _run('UPDATE accounts SET free_forever=1')

    # The original database becomes account #1, left exactly where it is.
    if not _q('SELECT id FROM accounts LIMIT 1'):
        _run('INSERT INTO accounts (name,slug,status,db_file,photo_dir,approved_at) VALUES (?,?,?,?,?,?)',
             (config.LEGACY_ACCOUNT_NAME, _unique_slug(config.LEGACY_ACCOUNT_NAME), 'active',
              os.path.relpath(config.DATABASE_PATH, config.DATA_DIR), 'photos', _now()))
        logger.info(f"Registered existing data as account '{config.LEGACY_ACCOUNT_NAME}'")

    # Bring every account database up to the current schema.
    for acc in _q("SELECT * FROM accounts WHERE db_file IS NOT NULL AND status != 'deleted'"):
        with database.using(db_path(acc)):
            database.init_db()
            if acc['id'] == first_account_id() and not database.get_admin('admin') \
                    and not database.get_all_admins():
                # Same behaviour as before for the original business.
                database.create_admin('admin', 'admin123', role='superadmin')
                logger.warning("Default admin created: admin / admin123")

    if not _q('SELECT id FROM owners LIMIT 1'):
        default = config.OWNER_PASSWORD == 'owner12345'
        _run('INSERT INTO owners (email,name,password_hash,must_change) VALUES (?,?,?,?)',
             (config.OWNER_EMAIL.strip().lower(), 'Owner', database.hash_pw(config.OWNER_PASSWORD), 1 if default else 0))
        logger.warning(f"Owner login created: {config.OWNER_EMAIL}"
                       + (" / owner12345 (change it after signing in)" if default else ""))
    elif config.OWNER_RESET:
        # The block above only ever runs once, the very first time the
        # platform boots — changing OWNER_EMAIL/OWNER_PASSWORD afterwards
        # normally has no effect on the already-stored owner login. Setting
        # OWNER_RESET forces the stored login to match them. Meant to be
        # turned back off once sign-in is confirmed, so a password changed
        # later from the owner dashboard isn't silently overwritten by a
        # stale environment variable on some future deploy.
        _run('UPDATE owners SET email=?, password_hash=?, must_change=0 WHERE id=(SELECT MIN(id) FROM owners)',
             (config.OWNER_EMAIL.strip().lower(), database.hash_pw(config.OWNER_PASSWORD)))
        logger.warning(f"Owner login reset via OWNER_RESET to: {config.OWNER_EMAIL}")

    if config.SEED_FACEFIT and config.FACEFIT_ADMIN_PASSWORD and not email_in_use(config.FACEFIT_ADMIN_EMAIL):
        aid, err = create_account('FaceFit Studio', '', config.FACEFIT_ADMIN_EMAIL, '', config.FACEFIT_ADMIN_PASSWORD)
        if err:
            logger.error(f"SEED_FACEFIT failed: {err}")
        else:
            acc = get_account(aid)
            with database.using(db_path(acc)):
                for k, v in {'primary':'FA4B13','secondary':'FFF0E8','accent':'FF7A45','dark':'3D1704',
                             'text':'4A2A1A','font':'Poppins','logo_text':'FaceFit Studio','dark_mode':'0'}.items():
                    database.set_setting(f'theme_{k}', v)
            logger.warning(f"Seeded FaceFit Studio account ({config.FACEFIT_ADMIN_EMAIL})")

    rebuild_index()

def first_account_id():
    r = _q('SELECT id FROM accounts ORDER BY id LIMIT 1')
    return r[0]['id'] if r else None

def _slugify(name):
    s = re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')
    return s[:40] or 'account'

def _unique_slug(name):
    base, n = _slugify(name), 1
    slug = base
    while _q('SELECT id FROM accounts WHERE slug=?', (slug,)):
        n += 1
        slug = f'{base}-{n}'
    return slug

def db_path(acc):
    return os.path.join(config.DATA_DIR, acc['db_file'])

# ══════════════════════════════════════════════════════════════════════════════
# LOOKUPS
# ══════════════════════════════════════════════════════════════════════════════
def get_account(aid):
    r = _q('SELECT * FROM accounts WHERE id=?', (aid,))
    return r[0] if r else None

def list_accounts(include_deleted=False):
    sql = 'SELECT * FROM accounts' + ('' if include_deleted else " WHERE status!='deleted'") + ' ORDER BY id'
    return _q(sql)

def get_owner(oid):
    r = _q('SELECT * FROM owners WHERE id=?', (oid,))
    return r[0] if r else None

def get_owner_by_email(email):
    r = _q('SELECT * FROM owners WHERE lower(email)=lower(?)', ((email or '').strip(),))
    return r[0] if r else None

def reindex_account(aid):
    """Refresh the sign-in index for one account from its own database."""
    acc = get_account(aid)
    with _db() as c:
        c.execute('DELETE FROM login_index WHERE account_id=?', (aid,))
        if acc and acc['db_file'] and acc['status'] != 'deleted':
            with database.using(db_path(acc)):
                admins = database.get_all_admins()
            c.executemany('INSERT INTO login_index (account_id,username,email) VALUES (?,?,?)',
                          [(aid, a['username'], a.get('email')) for a in admins if a.get('is_active', 1)])

def rebuild_index():
    with _db() as c:
        c.execute('DELETE FROM login_index')
    for acc in list_accounts():
        try:
            reindex_account(acc['id'])
        except Exception as e:
            logger.error(f"Index rebuild failed for account {acc['id']}: {e}")

def email_in_use(email, except_account=None, except_username=None):
    """True if any owner, account admin or pending sign-up already uses `email`."""
    email = (email or '').strip().lower()
    if not email: return False
    if get_owner_by_email(email): return True
    for r in _q('SELECT account_id,username FROM login_index WHERE lower(email)=?', (email,)):
        if not (r['account_id'] == except_account and r['username'] == except_username):
            return True
    return bool(_q("SELECT id FROM accounts WHERE lower(contact_email)=? AND status='pending'", (email,)))

# ══════════════════════════════════════════════════════════════════════════════
# SIGN-IN
# ══════════════════════════════════════════════════════════════════════════════
def authenticate(login, password, owner_only=False):
    """Find who is signing in. Returns (kind, record, account, error):
       ('owner', owner_row, None, None) | ('account', admin_row, account, None)
       | (None, None, None, message).
       `owner_only` is set by the dedicated owner sign-in form: it never
       falls through to an account match, so a business admin's valid
       credentials typed into the wrong door are rejected the same as any
       other invalid login, not quietly logged in as that business."""
    login = (login or '').strip()
    if not login or not password:
        return None, None, None, 'Enter your email and password'

    if '@' in login:
        own = get_owner_by_email(login)
        if own and database.check_pw(own['password_hash'], password):
            _run('UPDATE owners SET last_login=? WHERE id=?', (_now(), own['id']))
            return 'owner', own, None, None
        if owner_only:
            return None, None, None, 'Invalid email or password'
        rows = _q('SELECT * FROM login_index WHERE lower(email)=lower(?)', (login,))
        pending = _q("SELECT * FROM accounts WHERE lower(contact_email)=lower(?) AND status IN ('pending','rejected')", (login,))
        for acc in pending:
            if acc['signup_pw_hash'] and database.check_pw(acc['signup_pw_hash'], password):
                return None, None, None, ('Your account is waiting for approval. We will let you know once it is ready.'
                                          if acc['status'] == 'pending' else 'This sign-up request was not approved.')
    else:
        if owner_only:
            return None, None, None, 'Invalid email or password'
        rows = _q('SELECT * FROM login_index WHERE username=?', (login,))

    for r in rows:
        acc = get_account(r['account_id'])
        if not acc or acc['status'] == 'deleted': continue
        with database.using(db_path(acc)):
            adm = database.verify_admin(r['username'], password)
        if adm:
            if acc['status'] == 'suspended':
                return None, None, None, 'This account is suspended. Please contact ShiftGuard support.'
            if acc['status'] != 'active':
                return None, None, None, 'This account is not active yet.'
            touch(acc['id'])
            return 'account', adm, acc, None
    return None, None, None, 'Invalid email or password'

def find_account_for_login(login):
    """Best-effort account lookup for a login string, independent of whether
    the password was right. Used to attribute a failed sign-in to the
    business it targeted (for per-account risk signals) even on a wrong
    password, without revealing anything extra to the caller."""
    login = (login or '').strip()
    if not login: return None
    if '@' in login:
        rows = _q('SELECT account_id FROM login_index WHERE lower(email)=lower(?)', (login,))
    else:
        rows = _q('SELECT account_id FROM login_index WHERE username=?', (login,))
    return rows[0]['account_id'] if rows else None

def touch(aid):
    _run('UPDATE accounts SET last_activity=? WHERE id=?', (_now(), aid))

def log(event, actor='', account_id=None, ip='', details=''):
    try:
        _run('INSERT INTO platform_log (event,actor,account_id,ip,details) VALUES (?,?,?,?,?)',
             (event, actor, account_id, ip, details))
    except Exception as e:
        logger.error(f'platform log error: {e}')

def get_log(limit=150):
    return _q('''SELECT l.*, a.name AS account_name FROM platform_log l
                 LEFT JOIN accounts a ON a.id=l.account_id
                 ORDER BY l.id DESC LIMIT ?''', (limit,))

# ══════════════════════════════════════════════════════════════════════════════
# CREATING AND MANAGING ACCOUNTS
# ══════════════════════════════════════════════════════════════════════════════
def _valid_email(email):
    return bool(re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email or ''))

def validate_new(name, email, password):
    if not (name or '').strip(): return 'Enter the business name'
    if not _valid_email((email or '').strip()): return 'Enter a valid email address'
    if len(password or '') < 8: return 'Password must be at least 8 characters'
    if email_in_use(email): return 'That email is already registered'
    return None

def request_signup(name, contact_name, email, phone, password, ip=''):
    """Public sign-up: stored as a pending request until the owner approves it."""
    err = validate_new(name, email, password)
    if err: return None, err
    if len(_q("SELECT id FROM accounts WHERE status='pending' AND signup_ip=? AND date(created_at)=date('now')", (ip,))) >= 5:
        return None, 'Too many requests today. Please try again tomorrow.'
    aid = _run('''INSERT INTO accounts (name,slug,status,photo_dir,contact_name,contact_email,phone,signup_pw_hash,signup_ip)
                  VALUES (?,?,?,?,?,?,?,?,?)''',
               (name.strip(), _unique_slug(name), 'pending', '', (contact_name or '').strip(),
                email.strip().lower(), (phone or '').strip(), database.hash_pw(password), ip))
    log('signup_request', email.strip().lower(), aid, ip, name.strip())
    return aid, None

def _provision(aid, admin_email, password=None, password_hash=None):
    """Create the database, photo folder and first admin for an account."""
    acc = get_account(aid)
    rel = os.path.join('accounts', f"{acc['slug']}.db")
    photo_dir = f"photos/a/{acc['slug']}"
    path = os.path.join(config.DATA_DIR, rel)
    if os.path.exists(path):
        raise RuntimeError('A database for this account already exists')
    with database.using(path):
        database.init_db()
        database.set_setting('theme_logo_text', acc['name'])
        database.run("UPDATE branches SET address=? WHERE id=(SELECT MIN(id) FROM branches)", (acc['name'],))
        database.create_admin('admin', password, role='superadmin', email=admin_email,
                              password_hash=password_hash)
    os.makedirs(os.path.join(config.BASE_DIR, 'static', photo_dir), exist_ok=True)
    trial_ends = (datetime.now() + timedelta(days=config.TRIAL_DAYS)).strftime('%Y-%m-%d %H:%M:%S') \
                 if config.BILLING_ENABLED else None
    _run('''UPDATE accounts SET db_file=?, photo_dir=?, status='active', approved_at=?, signup_pw_hash=NULL,
            subscription_status=?, trial_ends_at=? WHERE id=?''',
         (rel, photo_dir, _now(), 'trialing' if config.BILLING_ENABLED else None, trial_ends, aid))
    reindex_account(aid)

def create_account(name, contact_name, email, phone, password):
    """Owner creates an account directly; it is active straight away."""
    err = validate_new(name, email, password)
    if err: return None, err
    aid = _run('''INSERT INTO accounts (name,slug,status,photo_dir,contact_name,contact_email,phone)
                  VALUES (?,?,?,?,?,?,?)''',
               (name.strip(), _unique_slug(name), 'pending', '', (contact_name or '').strip(),
                email.strip().lower(), (phone or '').strip()))
    try:
        _provision(aid, email.strip().lower(), password=password)
    except Exception:
        _run('DELETE FROM accounts WHERE id=?', (aid,))
        raise
    return aid, None

def approve(aid):
    acc = get_account(aid)
    if not acc or acc['status'] != 'pending': return 'Only pending requests can be approved'
    if not acc['signup_pw_hash']: return 'This request has no password set'
    _provision(aid, acc['contact_email'], password_hash=acc['signup_pw_hash'])
    return None

def reject(aid):
    acc = get_account(aid)
    if not acc or acc['status'] != 'pending': return 'Only pending requests can be rejected'
    _run("UPDATE accounts SET status='rejected' WHERE id=?", (aid,))
    return None

def set_status(aid, status):
    acc = get_account(aid)
    if not acc or acc['status'] not in ('active', 'suspended') or status not in ('active', 'suspended'):
        return 'Only active or suspended accounts can be changed'
    _run('UPDATE accounts SET status=? WHERE id=?', (status, aid))
    return None

def update_account(aid, name=None, contact_name=None, contact_email=None, phone=None, notes=None):
    acc = get_account(aid)
    if not acc: return 'Account not found'
    if name is not None and not name.strip(): return 'Business name cannot be empty'
    _run('''UPDATE accounts SET name=COALESCE(?,name), contact_name=COALESCE(?,contact_name),
            contact_email=COALESCE(?,contact_email), phone=COALESCE(?,phone), notes=COALESCE(?,notes) WHERE id=?''',
         (name.strip() if name else None, contact_name, contact_email, phone, notes, aid))
    return None

def delete_account(aid):
    """Removes the account from the platform. Its database file is moved to
    data/archive/ (not destroyed), so it can be restored by hand if needed."""
    acc = get_account(aid)
    if not acc: return 'Account not found'
    if acc['db_file']:
        src = db_path(acc)
        if os.path.exists(src):
            dest = os.path.join(config.ARCHIVE_DIR, f"{acc['slug']}_{datetime.now():%Y%m%d_%H%M%S}.db")
            shutil.move(src, dest)
    _run("UPDATE accounts SET status='deleted' WHERE id=?", (aid,))
    with _db() as c:
        c.execute('DELETE FROM login_index WHERE account_id=?', (aid,))
    return None

def account_admins(aid):
    acc = get_account(aid)
    if not acc or not acc['db_file']: return []
    with database.using(db_path(acc)):
        return database.get_all_admins()

def reset_admin_password(aid, username, new_pw):
    if len(new_pw or '') < 8: return 'Password must be at least 8 characters'
    acc = get_account(aid)
    if not acc or not acc['db_file']: return 'Account not found'
    with database.using(db_path(acc)):
        if not database.get_admin(username): return 'Admin user not found'
        database.set_admin_password(username, new_pw)
    return None

def account_stats(acc):
    """Headline numbers for one account, read from its own database."""
    out = {'employees': 0, 'checked_in': 0, 'today': 0, 'admins': 0, 'admin_email': None,
           'db_kb': 0, 'last_checkin': None, 'failed_logins_24h': 0, 'off_hours_checkins': 0}
    if not acc['db_file']: return out
    path = db_path(acc)
    if not os.path.exists(path): return out
    out['db_kb'] = round(os.path.getsize(path) / 1024)
    r = _q("SELECT COUNT(*) c FROM platform_log WHERE account_id=? AND event IN ('login_fail','login_2fa_fail') "
           "AND created_at >= datetime('now','-1 day')", (acc['id'],))
    out['failed_logins_24h'] = r[0]['c'] if r else 0
    try:
        with database.using(path):
            out['employees'] = len(database.get_employees(active_only=True))
            today = database.get_today_attendance()
            out['today'] = len([l for l in today if l.get('check_in')])
            out['checked_in'] = len([l for l in today if l.get('check_in') and not l.get('check_out')])
            for l in today:
                ci = l.get('check_in')
                if ci and len(ci) >= 13:
                    try:
                        h = int(ci[11:13])
                        if h < 5 or h >= 23: out['off_hours_checkins'] += 1
                    except ValueError:
                        pass
            admins = database.get_all_admins()
            out['admins'] = len(admins)
            out['admin_email'] = next((a['email'] for a in admins if a.get('email')), None)
            r = database.q('SELECT MAX(check_in) AS m FROM attendance')
            out['last_checkin'] = r[0]['m'] if r else None
    except Exception as e:
        logger.error(f"Stats failed for account {acc['id']}: {e}")
    return out

def account_risk(acc, stats):
    """Combines the available risk signals for one account into a single
    indicator for the owner dashboard: repeated failed sign-ins, off-hours
    check-ins, and an active account that has gone quiet."""
    reasons = []
    if stats.get('failed_logins_24h', 0) >= 3:
        reasons.append(f"{stats['failed_logins_24h']} failed sign-in attempts in the last 24h")
    if stats.get('off_hours_checkins', 0) > 0:
        n = stats['off_hours_checkins']
        reasons.append(f"{n} check-in{'s' if n != 1 else ''} today outside normal hours (11pm–5am)")
    if acc['status'] == 'active':
        cutoff = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
        if not acc['last_activity'] or acc['last_activity'] < cutoff:
            reasons.append('No sign-in activity for 14+ days')
    if not reasons:
        return {'level': 'ok', 'reasons': []}
    level = 'high' if stats.get('failed_logins_24h', 0) >= 3 else 'medium'
    return {'level': level, 'reasons': reasons}

# ══════════════════════════════════════════════════════════════════════════════
# BILLING (Stripe) ──────────────────────────────────────────────────────────────
def set_stripe_customer(aid, customer_id):
    _run('UPDATE accounts SET stripe_customer_id=? WHERE id=?', (customer_id, aid))

def get_account_by_stripe_customer(customer_id):
    r = _q('SELECT * FROM accounts WHERE stripe_customer_id=?', (customer_id,))
    return r[0] if r else None

def set_subscription_status(aid, subscription_id, status):
    _run('UPDATE accounts SET stripe_subscription_id=?, subscription_status=? WHERE id=?',
         (subscription_id, status, aid))

def set_free_forever(aid, flag):
    """Owner-controlled override: accounts marked free_forever are never
    expected to pay, regardless of what billing enforcement looks like
    later. New accounts default to payable (flag=0)."""
    _run('UPDATE accounts SET free_forever=? WHERE id=?', (1 if flag else 0, aid))

# ══════════════════════════════════════════════════════════════════════════════
# OWNER LOGIN
# ══════════════════════════════════════════════════════════════════════════════
def update_owner(oid, email=None, name=None, current_pw=None, new_pw=None):
    own = get_owner(oid)
    if not own: return 'Owner not found'
    if not current_pw or not database.check_pw(own['password_hash'], current_pw):
        return 'Current password is incorrect'
    if email is not None:
        email = email.strip().lower()
        if not _valid_email(email): return 'Enter a valid email address'
        if email != own['email'] and email_in_use(email): return 'That email is already in use'
        _run('UPDATE owners SET email=? WHERE id=?', (email, oid))
    if name is not None:
        _run('UPDATE owners SET name=? WHERE id=?', (name.strip(), oid))
    if new_pw:
        if len(new_pw) < 8: return 'New password must be at least 8 characters'
        _run('UPDATE owners SET password_hash=?, must_change=0 WHERE id=?', (database.hash_pw(new_pw), oid))
    return None

def set_owner_totp_pending(oid, secret):
    _run('UPDATE owners SET totp_secret=?, totp_enabled=0 WHERE id=?', (secret, oid))

def enable_owner_totp(oid, backup_codes_json):
    _run('UPDATE owners SET totp_enabled=1, backup_codes=? WHERE id=?', (backup_codes_json, oid))

def disable_owner_totp(oid):
    _run('UPDATE owners SET totp_secret=NULL, totp_enabled=0, backup_codes=NULL WHERE id=?', (oid,))

def set_owner_backup_codes(oid, backup_codes_json):
    _run('UPDATE owners SET backup_codes=? WHERE id=?', (backup_codes_json, oid))

def set_owner_password(oid, new_pw):
    _run('UPDATE owners SET password_hash=?, must_change=0 WHERE id=?', (database.hash_pw(new_pw), oid))

# ══════════════════════════════════════════════════════════════════════════════
# PASSWORD RESET (forgot password, both owner and business admin logins)
# ══════════════════════════════════════════════════════════════════════════════
def create_password_reset(kind, ref, username=None, ttl_minutes=60):
    token   = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(minutes=ttl_minutes)).strftime('%Y-%m-%d %H:%M:%S')
    _run('INSERT INTO password_resets (token,kind,ref,username,expires_at) VALUES (?,?,?,?,?)',
         (token, kind, str(ref), username, expires))
    return token

def get_password_reset(token):
    r = _q('SELECT * FROM password_resets WHERE token=?', (token,))
    if not r: return None
    row = r[0]
    if row['expires_at'] < _now():
        _run('DELETE FROM password_resets WHERE token=?', (token,))
        return None
    return row

def consume_password_reset(token):
    _run('DELETE FROM password_resets WHERE token=?', (token,))

def request_password_reset(email):
    """Looks up `email` across owners and every account's admin login index.
    Always safe to call with an unregistered email — callers should show the
    same generic message either way, to avoid leaking which emails exist."""
    email = (email or '').strip().lower()
    if not email:
        return None, None, None
    own = get_owner_by_email(email)
    if own:
        return 'owner', create_password_reset('owner', own['id']), None
    for r in _q('SELECT * FROM login_index WHERE lower(email)=lower(?)', (email,)):
        acc = get_account(r['account_id'])
        if acc and acc['status'] not in ('deleted', 'pending', 'rejected'):
            return 'account', create_password_reset('account', acc['id'], r['username']), acc
    return None, None, None
