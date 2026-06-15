import sqlite3, logging, calendar
from datetime import datetime, timedelta, date
from contextlib import contextmanager
import config

logger = logging.getLogger(__name__)

@contextmanager
def get_db():
    conn = None
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        raise
    finally:
        if conn: conn.close()

def q(sql, p=()):
    with get_db() as c:
        return [dict(r) for r in c.execute(sql, p).fetchall()]

def run(sql, p=()):
    with get_db() as c:
        return c.execute(sql, p).lastrowid

def init_db():
    with get_db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS branches (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL UNIQUE,
            address   TEXT,
            phone     TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS employees (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            pin_hash      TEXT NOT NULL,
            position      TEXT,
            phone         TEXT,
            branch_id     INTEGER DEFAULT 1,
            shift_start   TEXT DEFAULT "09:30",
            shift_end     TEXT DEFAULT "18:30",
            working_days  TEXT DEFAULT "Mon,Tue,Wed,Thu,Fri,Sat",
            salary_type   TEXT DEFAULT "monthly",
            salary_amount REAL DEFAULT 0,
            hire_date     DATE,
            is_active     INTEGER DEFAULT 1,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (branch_id) REFERENCES branches(id)
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id      INTEGER NOT NULL,
            branch_id        INTEGER DEFAULT 1,
            date             DATE NOT NULL,
            check_in         TIMESTAMP,
            check_in_photo   TEXT,
            check_in_status  TEXT DEFAULT "no_photo",
            check_out        TIMESTAMP,
            check_out_photo  TEXT,
            check_out_status TEXT DEFAULT "no_photo",
            status           TEXT DEFAULT "pending",
            minutes_late     INTEGER DEFAULT 0,
            hours_worked     REAL DEFAULT 0,
            overtime_hours   REAL DEFAULT 0,
            notes            TEXT,
            edited_by        TEXT,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees(id)
        );
        CREATE INDEX IF NOT EXISTS idx_att_date   ON attendance(date);
        CREATE INDEX IF NOT EXISTS idx_att_emp    ON attendance(employee_id);
        CREATE INDEX IF NOT EXISTS idx_att_branch ON attendance(branch_id);
        CREATE TABLE IF NOT EXISTS salary_records (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id      INTEGER NOT NULL,
            year             INTEGER NOT NULL,
            month            INTEGER NOT NULL,
            base_salary      REAL DEFAULT 0,
            working_days     INTEGER DEFAULT 0,
            days_present     INTEGER DEFAULT 0,
            days_absent      INTEGER DEFAULT 0,
            days_late        INTEGER DEFAULT 0,
            total_late_min   INTEGER DEFAULT 0,
            total_hours      REAL DEFAULT 0,
            overtime_hours   REAL DEFAULT 0,
            absent_deduction REAL DEFAULT 0,
            late_deduction   REAL DEFAULT 0,
            overtime_pay     REAL DEFAULT 0,
            net_salary       REAL DEFAULT 0,
            is_paid          INTEGER DEFAULT 0,
            paid_date        DATE,
            notes            TEXT,
            UNIQUE(employee_id, year, month),
            FOREIGN KEY (employee_id) REFERENCES employees(id)
        );
        CREATE TABLE IF NOT EXISTS blocked_sites (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            domain    TEXT UNIQUE NOT NULL,
            category  TEXT DEFAULT "restricted",
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS access_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            user       TEXT,
            ip         TEXT,
            details    TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (
            key        TEXT PRIMARY KEY,
            value      TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS admin_users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT DEFAULT "admin",
            branch_id     INTEGER,
            is_active     INTEGER DEFAULT 1,
            last_login    TIMESTAMP,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        c.commit()
        if not q('SELECT id FROM branches LIMIT 1'):
            c.execute("INSERT INTO branches (name,address) VALUES ('Main Branch','ShiftGuard HQ')")
            c.commit()
        for domain, cat in config.DEFAULT_BLOCKED_SITES:
            try: c.execute("INSERT OR IGNORE INTO blocked_sites (domain,category) VALUES (?,?)", (domain, cat))
            except: pass
        c.commit()
        for k, v in config.DEFAULT_THEME.items():
            try: c.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", (f'theme_{k}', v))
            except: pass
        c.commit()

# ── HASH ──────────────────────────────────────────────────────────────────────
def hash_pin(pin):
    from werkzeug.security import generate_password_hash
    return generate_password_hash(str(pin))

def check_pin(stored, pin):
    from werkzeug.security import check_password_hash
    return check_password_hash(stored, str(pin))

def hash_pw(pw):
    from werkzeug.security import generate_password_hash
    return generate_password_hash(pw)

def check_pw(stored, pw):
    from werkzeug.security import check_password_hash
    return check_password_hash(stored, pw)

# ── SETTINGS / THEME ──────────────────────────────────────────────────────────
def get_setting(key, default=None):
    r = q('SELECT value FROM settings WHERE key=?', (key,))
    return r[0]['value'] if r else default

def set_setting(key, value):
    if q('SELECT key FROM settings WHERE key=?', (key,)):
        run('UPDATE settings SET value=?,updated_at=CURRENT_TIMESTAMP WHERE key=?', (value, key))
    else:
        run('INSERT INTO settings (key,value) VALUES (?,?)', (key, value))

def get_theme():
    return {k: get_setting(f'theme_{k}', config.DEFAULT_THEME.get(k,''))
            for k in ['primary','secondary','accent','dark','text','font','logo_text','dark_mode']}

# ── BRANCHES ──────────────────────────────────────────────────────────────────
def get_branches(active_only=True):
    return q('SELECT * FROM branches WHERE is_active=1 ORDER BY name' if active_only
             else 'SELECT * FROM branches ORDER BY name')

def add_branch(name, address=None, phone=None):
    return run('INSERT INTO branches (name,address,phone) VALUES (?,?,?)', (name, address, phone))

def update_branch(bid, name, address=None, phone=None):
    run('UPDATE branches SET name=?,address=?,phone=? WHERE id=?', (name, address, phone, bid))

def delete_branch(bid):
    run('UPDATE branches SET is_active=0 WHERE id=?', (bid,))

# ── EMPLOYEES ──────────────────────────────────────────────────────────────────
def get_employees(active_only=True, branch_id=None):
    conds, params = [], []
    if active_only: conds.append('e.is_active=1')
    if branch_id:   conds.append('e.branch_id=?'); params.append(branch_id)
    where = ('WHERE ' + ' AND '.join(conds)) if conds else ''
    return q(f'''SELECT e.*,b.name as branch_name
                 FROM employees e LEFT JOIN branches b ON e.branch_id=b.id
                 {where} ORDER BY e.name''', params)

def get_employee(eid):
    r = q('''SELECT e.*,b.name as branch_name
             FROM employees e LEFT JOIN branches b ON e.branch_id=b.id
             WHERE e.id=?''', (eid,))
    return r[0] if r else None

def search_employees(fragment, branch_id=None):
    if branch_id:
        return q('SELECT * FROM employees WHERE name LIKE ? AND is_active=1 AND branch_id=? ORDER BY name LIMIT 10',
                 (f'%{fragment}%', branch_id))
    return q('SELECT * FROM employees WHERE name LIKE ? AND is_active=1 ORDER BY name LIMIT 10',
             (f'%{fragment}%',))

def add_employee(name, pin, position=None, phone=None, branch_id=1,
                 shift_start='09:30', shift_end='18:30',
                 working_days='Mon,Tue,Wed,Thu,Fri,Sat',
                 salary_type='monthly', salary_amount=0, hire_date=None):
    return run('''INSERT INTO employees
        (name,pin_hash,position,phone,branch_id,shift_start,shift_end,
         working_days,salary_type,salary_amount,hire_date)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
        (name, hash_pin(pin), position, phone, branch_id,
         shift_start, shift_end, working_days, salary_type, salary_amount, hire_date))

def update_employee(eid, **kw):
    allowed = ['name','position','phone','branch_id','shift_start','shift_end',
               'working_days','salary_type','salary_amount','hire_date','is_active']
    sets, vals = [], []
    for k, v in kw.items():
        if k == 'pin': sets.append('pin_hash=?'); vals.append(hash_pin(v))
        elif k in allowed: sets.append(f'{k}=?'); vals.append(v)
    if not sets: return
    vals.append(eid)
    run(f"UPDATE employees SET {','.join(sets)} WHERE id=?", vals)

def delete_employee(eid):
    """Permanently remove employee and all their records."""
    run('DELETE FROM attendance WHERE employee_id=?', (eid,))
    run('DELETE FROM salary_records WHERE employee_id=?', (eid,))
    run('DELETE FROM employees WHERE id=?', (eid,))

def reset_pin(eid, new_pin):
    run('UPDATE employees SET pin_hash=? WHERE id=?', (hash_pin(new_pin), eid))

def verify_employee_pin(eid, pin):
    r = q('SELECT pin_hash FROM employees WHERE id=? AND is_active=1', (eid,))
    return bool(r and check_pin(r[0]['pin_hash'], pin))

# ── ATTENDANCE ─────────────────────────────────────────────────────────────────
def get_today_attendance(branch_id=None):
    today = date.today().isoformat()
    if branch_id:
        return q('''SELECT a.*,e.name,e.position,e.shift_start,e.shift_end,b.name as branch_name
                    FROM attendance a JOIN employees e ON a.employee_id=e.id
                    JOIN branches b ON a.branch_id=b.id
                    WHERE a.date=? AND a.branch_id=? ORDER BY a.check_in DESC''', (today, branch_id))
    return q('''SELECT a.*,e.name,e.position,e.shift_start,e.shift_end,b.name as branch_name
                FROM attendance a JOIN employees e ON a.employee_id=e.id
                JOIN branches b ON a.branch_id=b.id
                WHERE a.date=? ORDER BY a.check_in DESC''', (today,))

def get_attendance_range(start, end, employee_id=None, branch_id=None):
    conds  = ['a.date BETWEEN ? AND ?']
    params = [start, end]
    if employee_id: conds.append('a.employee_id=?'); params.append(employee_id)
    if branch_id:   conds.append('a.branch_id=?');   params.append(branch_id)
    return q(f'''SELECT a.*,e.name,e.position,b.name as branch_name
                 FROM attendance a JOIN employees e ON a.employee_id=e.id
                 JOIN branches b ON a.branch_id=b.id
                 WHERE {' AND '.join(conds)}
                 ORDER BY a.date DESC, a.check_in DESC''', params)

def get_attendance_record(eid, date_str):
    r = q('SELECT * FROM attendance WHERE employee_id=? AND date=?', (eid, date_str))
    return r[0] if r else None

def record_check_in(eid, photo_path=None, photo_status='ok'):
    emp   = get_employee(eid)
    if not emp: return False, "Employee not found"
    today = date.today().isoformat()
    if get_attendance_record(eid, today):
        return False, "Already checked in today"
    now = datetime.now()
    shift_start = datetime.strptime(emp['shift_start'], '%H:%M').replace(
        year=now.year, month=now.month, day=now.day)
    mins_late = max(0, int((now - shift_start).total_seconds() / 60))
    status    = 'late' if mins_late > config.LATE_THRESHOLD_MINUTES else 'on_time'
    run('''INSERT INTO attendance
           (employee_id,branch_id,date,check_in,check_in_photo,check_in_status,status,minutes_late)
           VALUES (?,?,?,?,?,?,?,?)''',
        (eid, emp['branch_id'], today, now, photo_path, photo_status, status, mins_late))
    log_event('check_in', emp['name'], '', f"Status:{status} Late:{mins_late}min")
    return True, f"Welcome, {emp['name']}! Checked in at {now.strftime('%H:%M')}"

def record_check_out(eid, photo_path=None, photo_status='ok'):
    emp = get_employee(eid)
    if not emp: return False, "Employee not found"
    today = date.today().isoformat()
    rec   = get_attendance_record(eid, today)
    if not rec or not rec['check_in']:
        return False, "No check-in found for today"
    if rec['check_out']:
        return False, "Already checked out today"
    now = datetime.now()
    ci  = datetime.fromisoformat(str(rec['check_in']))
    hrs = max(0, (now - ci).total_seconds() / 3600)
    shift_end   = datetime.strptime(emp['shift_end'],   '%H:%M').replace(year=now.year, month=now.month, day=now.day)
    shift_start = datetime.strptime(emp['shift_start'], '%H:%M').replace(year=now.year, month=now.month, day=now.day)
    sched  = (shift_end - shift_start).total_seconds() / 3600
    ot     = max(0, hrs - sched)
    status = 'completed' if now >= shift_end else 'early_departure'
    run('''UPDATE attendance SET check_out=?,check_out_photo=?,check_out_status=?,
           hours_worked=?,overtime_hours=?,status=? WHERE id=?''',
        (now, photo_path, photo_status, round(hrs,2), round(ot,2), status, rec['id']))
    log_event('check_out', emp['name'], '', f"Hours:{hrs:.2f} OT:{ot:.2f}")
    return True, f"Goodbye, {emp['name']}! Checked out at {now.strftime('%H:%M')}"

def admin_edit_attendance(rid, check_in=None, check_out=None, notes=None, admin='admin'):
    sets, vals = ['edited_by=?'], [admin]
    if check_in  is not None: sets.append('check_in=?');  vals.append(check_in)
    if check_out is not None: sets.append('check_out=?'); vals.append(check_out)
    if notes     is not None: sets.append('notes=?');     vals.append(notes)
    if check_in and check_out:
        try:
            hrs = max(0,(datetime.fromisoformat(check_out)-datetime.fromisoformat(check_in)).total_seconds()/3600)
            sets.append('hours_worked=?'); vals.append(round(hrs,2))
        except: pass
    vals.append(rid)
    run(f"UPDATE attendance SET {','.join(sets)} WHERE id=?", vals)

def admin_delete_attendance(rid):
    run('DELETE FROM attendance WHERE id=?', (rid,))

def admin_add_attendance(eid, date_str, check_in_time, check_out_time=None, notes=None):
    emp = get_employee(eid)
    if not emp: return False
    ci = datetime.fromisoformat(f"{date_str}T{check_in_time}")
    shift_start = datetime.strptime(emp['shift_start'], '%H:%M').replace(year=ci.year, month=ci.month, day=ci.day)
    mins_late = max(0, int((ci - shift_start).total_seconds() / 60))
    status = 'late' if mins_late > config.LATE_THRESHOLD_MINUTES else 'on_time'
    hrs = 0; co = None
    if check_out_time:
        co  = datetime.fromisoformat(f"{date_str}T{check_out_time}")
        hrs = max(0, (co - ci).total_seconds() / 3600)
        status = 'completed'
    run('''INSERT INTO attendance
           (employee_id,branch_id,date,check_in,check_out,check_in_status,
            status,minutes_late,hours_worked,notes,edited_by)
           VALUES (?,?,?,?,?,"manual",?,?,?,?,"admin")''',
        (eid, emp['branch_id'], date_str, ci, co, status, mins_late, round(hrs,2), notes))
    return True

def delete_photo(rid, field):
    if field in ('check_in_photo','check_out_photo'):
        run(f'UPDATE attendance SET {field}=NULL WHERE id=?', (rid,))

# ── SALARY ─────────────────────────────────────────────────────────────────────
def calculate_salary(eid, year, month):
    emp = get_employee(eid)
    if not emp: return {}
    first = date(year, month, 1)
    last  = date(year, month, calendar.monthrange(year, month)[1])
    day_abbr = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    wd_list  = [d.strip() for d in (emp['working_days'] or 'Mon,Tue,Wed,Thu,Fri,Sat').split(',')]
    sched    = sum(1 for n in range((last-first).days+1)
                   if day_abbr[(first+timedelta(days=n)).weekday()] in wd_list)
    logs     = get_attendance_range(str(first), str(last), eid)
    present  = len([l for l in logs if l['check_in']])
    absent   = max(0, sched - present)
    late_days= len([l for l in logs if (l['minutes_late'] or 0) > config.LATE_THRESHOLD_MINUTES])
    late_min = sum(l['minutes_late'] or 0 for l in logs)
    total_hrs= sum(l['hours_worked'] or 0 for l in logs)
    ot_hrs   = sum(l['overtime_hours'] or 0 for l in logs)
    base     = float(emp['salary_amount'] or 0)
    daily    = (base / sched) if sched > 0 else 0
    shift_hrs= (datetime.strptime(emp['shift_end'],'%H:%M') -
                datetime.strptime(emp['shift_start'],'%H:%M')).total_seconds() / 3600
    absent_ded = daily * absent
    late_ded   = (daily / shift_hrs / 60) * late_min * 0.5 if shift_hrs > 0 else 0
    hourly     = (base / (sched * shift_hrs)) if sched > 0 and shift_hrs > 0 else 0
    ot_pay     = hourly * 1.5 * ot_hrs
    net        = max(0, base - absent_ded - late_ded + ot_pay)
    return dict(employee_id=eid, employee_name=emp['name'], branch_name=emp.get('branch_name',''),
                year=year, month=month, base_salary=round(base,2),
                working_days=sched, days_present=present, days_absent=absent,
                days_late=late_days, total_late_min=round(late_min,1),
                total_hours=round(total_hrs,2), overtime_hours=round(ot_hrs,2),
                absent_deduction=round(absent_ded,2), late_deduction=round(late_ded,2),
                overtime_pay=round(ot_pay,2), net_salary=round(net,2))

def save_salary(calc):
    run('''INSERT INTO salary_records
           (employee_id,year,month,base_salary,working_days,days_present,days_absent,
            days_late,total_late_min,total_hours,overtime_hours,
            absent_deduction,late_deduction,overtime_pay,net_salary)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(employee_id,year,month) DO UPDATE SET
           base_salary=excluded.base_salary, working_days=excluded.working_days,
           days_present=excluded.days_present, days_absent=excluded.days_absent,
           days_late=excluded.days_late, total_late_min=excluded.total_late_min,
           total_hours=excluded.total_hours, overtime_hours=excluded.overtime_hours,
           absent_deduction=excluded.absent_deduction, late_deduction=excluded.late_deduction,
           overtime_pay=excluded.overtime_pay, net_salary=excluded.net_salary''',
        (calc['employee_id'],calc['year'],calc['month'],calc['base_salary'],
         calc['working_days'],calc['days_present'],calc['days_absent'],calc['days_late'],
         calc['total_late_min'],calc['total_hours'],calc['overtime_hours'],
         calc['absent_deduction'],calc['late_deduction'],calc['overtime_pay'],calc['net_salary']))

def get_salary_records(year=None, month=None, eid=None):
    conds, params = [], []
    if year:  conds.append('s.year=?');        params.append(year)
    if month: conds.append('s.month=?');       params.append(month)
    if eid:   conds.append('s.employee_id=?'); params.append(eid)
    where = ('WHERE ' + ' AND '.join(conds)) if conds else ''
    return q(f'''SELECT s.*,e.name FROM salary_records s JOIN employees e ON s.employee_id=e.id
                 {where} ORDER BY e.name''', params)

def mark_paid(eid, year, month):
    run('UPDATE salary_records SET is_paid=1,paid_date=? WHERE employee_id=? AND year=? AND month=?',
        (date.today().isoformat(), eid, year, month))

# ── BLOCKED SITES ──────────────────────────────────────────────────────────────
def get_blocked_sites():
    return q('SELECT * FROM blocked_sites ORDER BY domain')

def add_blocked_site(domain, category='restricted'):
    try: run('INSERT INTO blocked_sites (domain,category) VALUES (?,?)', (domain.lower().strip(), category)); return True
    except: return False

def remove_blocked_site(sid):
    run('DELETE FROM blocked_sites WHERE id=?', (sid,))

# ── ACCESS LOGS ────────────────────────────────────────────────────────────────
def log_event(event_type, user='', ip='', details=''):
    run('INSERT INTO access_logs (event_type,user,ip,details) VALUES (?,?,?,?)',
        (event_type, user, ip, details))

def get_logs(limit=200):
    return q('SELECT * FROM access_logs ORDER BY created_at DESC LIMIT ?', (limit,))

# ── ADMIN USERS ────────────────────────────────────────────────────────────────
def get_admin(username):
    r = q('SELECT * FROM admin_users WHERE username=? AND is_active=1', (username,))
    return r[0] if r else None

def create_admin(username, password, role='admin', branch_id=None):
    run('INSERT INTO admin_users (username,password_hash,role,branch_id) VALUES (?,?,?,?)',
        (username, hash_pw(password), role, branch_id))

def verify_admin(username, password):
    adm = get_admin(username)
    if adm and check_pw(adm['password_hash'], password):
        run('UPDATE admin_users SET last_login=CURRENT_TIMESTAMP WHERE username=?', (username,))
        return adm
    return None

def change_password(username, current_pw, new_pw):
    adm = get_admin(username)
    if not adm: return False, "User not found"
    if not check_pw(adm['password_hash'], current_pw): return False, "Current password is incorrect"
    if len(new_pw) < 8: return False, "New password must be at least 8 characters"
    run('UPDATE admin_users SET password_hash=? WHERE username=?', (hash_pw(new_pw), username))
    return True, "Password changed. Please login again."

def get_all_admins():
    return q('SELECT id,username,role,branch_id,is_active,last_login FROM admin_users ORDER BY username')
