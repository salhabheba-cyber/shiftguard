"""ShiftGuard — Main Flask Application"""
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from functools import wraps
from datetime import datetime, timedelta, date
import logging, os, sys, shutil, io, base64, calendar, re
from logging.handlers import RotatingFileHandler
import config, database, network_manager, nextdns, reports

# ── TIMEZONE FIX ──────────────────────────────────────────────────────────────
os.environ['TZ'] = 'Asia/Beirut'
try:
    import time as _time
    _time.tzset()  # Apply on Linux/Railway server
except AttributeError:
    pass  # Windows doesn't have tzset — handled by os.environ above

app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=config.SESSION_HOURS)
app.config['MAX_CONTENT_LENGTH'] = config.PHOTO_MAX_MB * 1024 * 1024
CORS(app)

# ── LOGGING ───────────────────────────────────────────────────────────────────
logger = logging.getLogger('shiftguard')
logger.setLevel(logging.INFO)
fh = RotatingFileHandler(config.LOG_FILE, maxBytes=10_485_760, backupCount=5)
fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(fh)
logger.addHandler(logging.StreamHandler(sys.stdout))

# ── AUTH ──────────────────────────────────────────────────────────────────────
login_manager = LoginManager(app)
login_manager.login_view = 'login_page'

class AdminUser(UserMixin):
    def __init__(self, d):
        self.id        = d['username']
        self.username  = d['username']
        self.role      = d.get('role','admin')
        self.branch_id = d.get('branch_id')

@login_manager.user_loader
def load_user(username):
    d = database.get_admin(username)
    return AdminUser(d) if d else None

def api_login_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if not current_user.is_authenticated:
            return jsonify({'success':False,'message':'Login required'}), 401
        database.touch_admin_last_seen(current_user.username)
        return f(*a, **kw)
    return dec

# ── SECURITY HEADERS ──────────────────────────────────────────────────────────
@app.after_request
def sec_headers(r):
    r.headers['X-Content-Type-Options'] = 'nosniff'
    r.headers['X-XSS-Protection']       = '1; mode=block'
    r.headers['X-Frame-Options']         = 'SAMEORIGIN'
    return r

# ── INIT ──────────────────────────────────────────────────────────────────────
with app.app_context():
    database.init_db()
    if not database.get_admin('admin'):
        database.create_admin('admin','admin123',role='superadmin')
        logger.warning("Default admin created: admin / admin123")

# ── PHOTO HELPER ──────────────────────────────────────────────────────────────
def save_photo(b64, emp_name, action):
    try:
        if ',' in b64: b64 = b64.split(',')[1]
        data   = base64.b64decode(b64)
        now    = datetime.now()
        safe   = re.sub(r'[^a-zA-Z0-9_]','_', emp_name)
        folder = os.path.join(config.PHOTOS_DIR, str(now.year), f'{now.month:02d}', f'{now.day:02d}')
        os.makedirs(folder, exist_ok=True)
        fname  = f"{safe}_{action}_{now.strftime('%H%M%S')}.jpg"
        fpath  = os.path.join(folder, fname)
        with open(fpath,'wb') as f: f.write(data)
        return os.path.relpath(fpath, os.path.join(config.BASE_DIR,'static')).replace('\\','/')
    except Exception as e:
        logger.error(f"Photo save error: {e}")
        return None

def _remove_photo_file(rel_path):
    if not rel_path: return
    path = os.path.join(config.BASE_DIR, 'static', rel_path)
    try:
        if os.path.exists(path): os.remove(path)
    except Exception as e:
        logger.error(f"Photo file delete error: {e}")

def _maybe_auto_purge_photos():
    """Runs at most once a day. Deletes check-in/out photos older than the
    configured retention window (default 30 days) so storage doesn't grow
    forever. Attendance records themselves are never touched — only the
    photo file + its reference are cleared."""
    try:
        settings = database.get_photo_settings()
        if not settings['enabled']: return
        if settings['last_purge'] == date.today().isoformat(): return
        old = database.find_old_photos(settings['retention_days'])
        for _, _, relpath in old:
            _remove_photo_file(relpath)
        database.purge_photo_refs([(rid, field) for rid, field, _ in old])
        database.mark_photo_purge_ran()
        if old:
            logger.info(f"Auto-purged {len(old)} photo(s) older than {settings['retention_days']} days")
            database.log_event('photos_auto_purged', 'system', '',
                               f"{len(old)} photo(s) older than {settings['retention_days']}d")
    except Exception as e:
        logger.error(f"Auto photo purge error: {e}")

def _client_ip():
    """Real client IP. Railway (and most hosts) sit behind a reverse proxy,
    so request.remote_addr alone would just be the proxy's internal IP.
    X-Forwarded-For carries the real device IP — we take the RIGHTMOST entry
    (the address Railway's own edge appended from the actual TCP connection
    it saw), not the leftmost, since a malicious client could otherwise
    prepend a fake IP of their own choosing to the header."""
    fwd = request.headers.get('X-Forwarded-For', '')
    if fwd:
        return fwd.split(',')[-1].strip()
    return request.remote_addr or ''

def _nextdns_config():
    return database.get_setting('nextdns_api_key', ''), database.get_setting('nextdns_profile_id', '')

def _effective_branch_id():
    """A superadmin can view/filter across any branch (None = all branches,
    today's behavior). Every other role is always pinned to their own
    branch, regardless of what a client might pass in — this is the actual
    tenant boundary."""
    if current_user.role == 'superadmin':
        return None
    return current_user.branch_id

def _require_superadmin(f):
    @wraps(f)
    def dec(*a, **kw):
        if not current_user.is_authenticated:
            return jsonify({'success':False,'message':'Login required'}), 401
        if current_user.role != 'superadmin':
            return jsonify({'success':False,'message':'Superadmin access required'}), 403
        database.touch_admin_last_seen(current_user.username)
        return f(*a, **kw)
    return dec

# ══════════════════════════════════════════════════════════════════════════════
# KIOSK
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/')
def home(): return redirect(url_for('kiosk'))

@app.route('/kiosk')
def kiosk():
    theme   = database.get_theme()
    logs    = database.get_today_attendance()
    checked = len([l for l in logs if l['check_in'] and not l['check_out']])
    today   = date.today().strftime('%A, %d %B %Y')
    return render_template('kiosk.html', theme=theme,
                           checked_in_count=checked, today=today)

@app.route('/api/kiosk/signin', methods=['POST'])
def kiosk_signin():
    d        = request.json or {}
    username = (d.get('username') or '').strip()
    pin      = str(d.get('pin','')).strip()
    if not username or not pin:
        return jsonify({'success':False,'message':'Username and PIN are required'}), 400
    emp = database.get_employee_by_username(username)
    if not emp or not database.verify_employee_pin(emp['id'], pin):
        database.log_event('kiosk_signin_fail', username, _client_ip(), '')
        return jsonify({'success':False,'message':'Invalid username or PIN'}), 401
    return jsonify({'success':True,'employee':{
        'id':emp['id'],'name':emp['name'],'position':emp['position'] or '',
        'shift_start':emp['shift_start'],'shift_end':emp['shift_end']}})

@app.route('/api/kiosk/search')
def kiosk_search():
    q         = request.args.get('q','').strip()
    branch_id = request.args.get('branch_id', type=int)
    if not q: return jsonify({'employees':[]})
    emps = database.search_employees(q, branch_id)
    return jsonify({'employees':[{'id':e['id'],'name':e['name'],
        'position':e['position'] or '','shift_start':e['shift_start'],
        'shift_end':e['shift_end']} for e in emps]})

@app.route('/api/kiosk/checkin', methods=['POST'])
def kiosk_checkin():
    d    = request.json or {}
    eid  = d.get('employee_id')
    pin  = str(d.get('pin','')).strip()
    if not eid or not pin:
        return jsonify({'success':False,'message':'Missing data'}), 400
    if not database.verify_employee_pin(eid, pin):
        return jsonify({'success':False,'message':'❌ Incorrect PIN. Try again.'}), 401
    emp   = database.get_employee(eid)
    photo = None
    pstat = d.get('photo_status','ok')
    if d.get('photo'):
        photo = save_photo(d['photo'], emp['name'], 'in')
        if not photo: pstat = 'save_failed'
    ok, msg = database.record_check_in(eid, photo, pstat, _client_ip())
    return jsonify({'success':ok,'message':msg,
                    'photo_path':f'/static/{photo}' if photo else None,
                    'time':datetime.now().strftime('%H:%M')})

@app.route('/api/kiosk/checkout', methods=['POST'])
def kiosk_checkout():
    d    = request.json or {}
    eid  = d.get('employee_id')
    pin  = str(d.get('pin','')).strip()
    if not eid or not pin:
        return jsonify({'success':False,'message':'Missing data'}), 400
    if not database.verify_employee_pin(eid, pin):
        return jsonify({'success':False,'message':'❌ Incorrect PIN. Try again.'}), 401
    emp   = database.get_employee(eid)
    photo = None
    pstat = d.get('photo_status','ok')
    if d.get('photo'):
        photo = save_photo(d['photo'], emp['name'], 'out')
        if not photo: pstat = 'save_failed'
    ok, msg = database.record_check_out(eid, photo, pstat, _client_ip())
    return jsonify({'success':ok,'message':msg,
                    'photo_path':f'/static/{photo}' if photo else None,
                    'time':datetime.now().strftime('%H:%M')})

@app.route('/api/kiosk/status')
def kiosk_status():
    bid  = request.args.get('branch_id', type=int)
    logs = database.get_today_attendance(bid)
    return jsonify({'checked_in_count': len([l for l in logs if l['check_in'] and not l['check_out']])})

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN AUTH
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/admin/login', methods=['GET'])
def login_page():
    return render_template('login.html', theme=database.get_theme())

@app.route('/admin/login', methods=['POST'])
def login_post():
    d    = request.json or {}
    user = database.verify_admin(d.get('username',''), d.get('password',''))
    if not user:
        database.log_event('login_fail', d.get('username',''), _client_ip(), 'Wrong password')
        return jsonify({'success':False,'message':'Invalid username or password'}), 401
    login_user(AdminUser(user), remember=True)
    database.log_event('login_ok', user['username'], _client_ip(), '')
    return jsonify({'success':True})

@app.route('/admin/logout', methods=['POST'])
@login_required
def logout():
    database.log_event('logout', current_user.username, _client_ip(), '')
    logout_user()
    return jsonify({'success':True})

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/admin')
@login_required
def admin():
    return render_template('admin.html', theme=database.get_theme(_effective_branch_id()),
                           branches=database.get_branches(), user=current_user)

# ── DASHBOARD ─────────────────────────────────────────────────────────────────
@app.route('/api/admin/dashboard')
@api_login_required
def api_dashboard():
    _maybe_auto_purge_photos()
    bid  = _effective_branch_id()
    logs = database.get_today_attendance(bid)
    emps = database.get_employees(active_only=True, branch_id=bid)
    checked_in  = [l for l in logs if l['check_in'] and not l['check_out']]
    checked_out = [l for l in logs if l['check_in'] and l['check_out']]
    late        = [l for l in logs if (l['minutes_late'] or 0) > config.LATE_THRESHOLD_MINUTES]
    absent      = max(0, len(emps) - len([l for l in logs if l['check_in']]))
    return jsonify({
        'total_employees': len(emps),
        'checked_in':  len(checked_in),
        'checked_out': len(checked_out),
        'late':        len(late),
        'absent':      absent,
        'today':       date.today().strftime('%A, %d %B %Y'),
        'logs': [{
            'id':              l['id'],
            'name':            l['name'],
            'position':        l['position'] or '',
            'branch_name':     l.get('branch_name',''),
            'check_in':        str(l['check_in'])[:16] if l['check_in'] else None,
            'check_in_photo':  f"/static/{l['check_in_photo']}" if l['check_in_photo'] else None,
            'check_in_ip':     l.get('check_in_ip') or None,
            'check_out':       str(l['check_out'])[:16] if l['check_out'] else None,
            'check_out_photo': f"/static/{l['check_out_photo']}" if l['check_out_photo'] else None,
            'check_out_ip':    l.get('check_out_ip') or None,
            'status':          l['status'],
            'minutes_late':    l['minutes_late'] or 0,
            'hours_worked':    round(l['hours_worked'] or 0, 2),
        } for l in logs]
    })

# ── ATTENDANCE ─────────────────────────────────────────────────────────────────
@app.route('/api/admin/attendance')
@api_login_required
def api_attendance():
    start = request.args.get('start', (date.today()-timedelta(days=30)).isoformat())
    end   = request.args.get('end',   date.today().isoformat())
    eid   = request.args.get('employee_id', type=int)
    bid   = _effective_branch_id()
    logs  = database.get_attendance_range(start, end, eid, bid)
    return jsonify({'logs':[{
        'id':              l['id'],
        'name':            l['name'],
        'position':        l['position'] or '',
        'branch_name':     l.get('branch_name',''),
        'date':            l['date'],
        'check_in':        str(l['check_in'])[:19]  if l['check_in']  else '',
        'check_in_photo':  f"/static/{l['check_in_photo']}"  if l['check_in_photo']  else None,
        'check_in_ip':     l.get('check_in_ip') or None,
        'check_out':       str(l['check_out'])[:19] if l['check_out'] else '',
        'check_out_photo': f"/static/{l['check_out_photo']}" if l['check_out_photo'] else None,
        'check_out_ip':    l.get('check_out_ip') or None,
        'status':          l['status'] or '',
        'minutes_late':    l['minutes_late'] or 0,
        'hours_worked':    round(l['hours_worked'] or 0, 2),
        'overtime_hours':  round(l['overtime_hours'] or 0, 2),
        'notes':           l['notes'] or '',
    } for l in logs], 'count':len(logs)})

@app.route('/api/admin/attendance/<int:rid>', methods=['PUT'])
@api_login_required
def api_edit_att(rid):
    d = request.json or {}
    database.admin_edit_attendance(rid, d.get('check_in') or None,
                                   d.get('check_out') or None, d.get('notes'),
                                   current_user.username)
    return jsonify({'success':True,'message':'Record updated'})

@app.route('/api/admin/attendance/<int:rid>', methods=['DELETE'])
@api_login_required
def api_del_att(rid):
    database.admin_delete_attendance(rid)
    return jsonify({'success':True})

@app.route('/api/admin/attendance/add', methods=['POST'])
@api_login_required
def api_add_att():
    d  = request.json or {}
    ok = database.admin_add_attendance(d.get('employee_id'), d.get('date'),
                                       d.get('check_in'), d.get('check_out'), d.get('notes'))
    return jsonify({'success':ok})

@app.route('/api/admin/attendance/<int:rid>/delete-photo', methods=['POST'])
@api_login_required
def api_del_photo(rid):
    d     = request.json or {}
    field = d.get('field','check_in_photo')
    r     = database.q('SELECT * FROM attendance WHERE id=?',(rid,))
    if r and r[0].get(field):
        _remove_photo_file(r[0][field])
    database.delete_photo(rid, field)
    return jsonify({'success':True})

# ── EMPLOYEES ──────────────────────────────────────────────────────────────────
@app.route('/api/admin/employees', methods=['GET'])
@api_login_required
def api_employees():
    bid  = _effective_branch_id()
    emps = database.get_employees(active_only=True, branch_id=bid)
    for e in emps: e.pop('pin_hash', None)
    return jsonify({'employees': emps})

@app.route('/api/admin/employees', methods=['POST'])
@api_login_required
def api_add_emp():
    d    = request.json or {}
    name = (d.get('name') or '').strip()
    pin  = str(d.get('pin','')).strip()
    if not name: return jsonify({'success':False,'message':'Name required'}), 400
    if not pin or len(pin)!=4 or not pin.isdigit():
        return jsonify({'success':False,'message':'PIN must be exactly 4 digits'}), 400
    branch_id = current_user.branch_id if current_user.role != 'superadmin' else int(d.get('branch_id') or 1)
    try:
        eid = database.add_employee(
            name=name, pin=pin,
            position=d.get('position') or None, phone=d.get('phone') or None,
            branch_id=branch_id,
            shift_start=d.get('shift_start','09:30'), shift_end=d.get('shift_end','18:30'),
            working_days=d.get('working_days','Mon,Tue,Wed,Thu,Fri,Sat'),
            salary_type=d.get('salary_type','monthly'),
            salary_amount=float(d.get('salary_amount') or 0),
            hire_date=d.get('hire_date') or None,
            username=d.get('username') or None)
        return jsonify({'success':True,'message':f'{name} added!','id':eid})
    except Exception as e:
        return jsonify({'success':False,'message':str(e)}), 500

@app.route('/api/admin/employees/<int:eid>', methods=['PUT'])
@api_login_required
def api_upd_emp(eid):
    d  = request.json or {}
    kw = {}
    for f in ['name','position','phone','branch_id','shift_start','shift_end',
              'working_days','salary_type','salary_amount','hire_date','is_active','username']:
        if f in d: kw[f] = d[f]
    if current_user.role != 'superadmin':
        kw.pop('branch_id', None)
    if 'pin' in d and d['pin']:
        pin = str(d['pin']).strip()
        if len(pin)!=4 or not pin.isdigit():
            return jsonify({'success':False,'message':'PIN must be 4 digits'}), 400
        kw['pin'] = pin
    database.update_employee(eid, **kw)
    return jsonify({'success':True,'message':'Employee updated'})

@app.route('/api/admin/employees/<int:eid>/reset-pin', methods=['POST'])
@api_login_required
def api_reset_pin(eid):
    d   = request.json or {}
    pin = str(d.get('pin','')).strip()
    if len(pin)!=4 or not pin.isdigit():
        return jsonify({'success':False,'message':'PIN must be 4 digits'}), 400
    database.reset_pin(eid, pin)
    emp = database.get_employee(eid)
    return jsonify({'success':True,'message':f"PIN reset for {emp['name'] if emp else 'employee'}"})

@app.route('/api/admin/employees/<int:eid>', methods=['DELETE'])
@api_login_required
def api_del_emp(eid):
    database.delete_employee(eid)
    return jsonify({'success':True,'message':'Employee permanently deleted'})

# ── BRANCHES ───────────────────────────────────────────────────────────────────
@app.route('/api/admin/branches', methods=['GET'])
@api_login_required
def api_branches():
    return jsonify({'branches': database.get_branches(active_only=False)})

@app.route('/api/admin/branches', methods=['POST'])
@_require_superadmin
def api_add_branch():
    d    = request.json or {}
    name = (d.get('name') or '').strip()
    if not name: return jsonify({'success':False,'message':'Name required'}), 400
    try:
        bid = database.add_branch(name, d.get('address'), d.get('phone'),
                                  d.get('slug'), d.get('logo_url'))
    except ValueError as e:
        return jsonify({'success':False,'message':str(e)}), 400
    return jsonify({'success':True,'id':bid,'message':f'Branch "{name}" added'})

@app.route('/api/admin/branches/<int:bid>', methods=['PUT'])
@_require_superadmin
def api_upd_branch(bid):
    d = request.json or {}
    try:
        database.update_branch(bid, d.get('name',''), d.get('address'), d.get('phone'),
                               d.get('slug'), d.get('logo_url'))
    except ValueError as e:
        return jsonify({'success':False,'message':str(e)}), 400
    return jsonify({'success':True})

@app.route('/api/admin/branches/<int:bid>', methods=['DELETE'])
@_require_superadmin
def api_del_branch(bid):
    database.delete_branch(bid)
    return jsonify({'success':True})

# ── SALARY ─────────────────────────────────────────────────────────────────────
@app.route('/api/admin/salary/calculate', methods=['POST'])
@api_login_required
def api_calc():
    d     = request.json or {}
    year  = int(d.get('year',  date.today().year))
    month = int(d.get('month', date.today().month))
    eid   = d.get('employee_id')
    emps  = [database.get_employee(int(eid))] if eid else database.get_employees()
    recs  = []
    for e in emps:
        if not e: continue
        calc = database.calculate_salary(e['id'], year, month)
        database.save_salary(calc)
        recs.append(calc)
    return jsonify({'success':True,'records':recs})

@app.route('/api/admin/salary/records')
@api_login_required
def api_sal_records():
    return jsonify({'records': database.get_salary_records(
        request.args.get('year',type=int),
        request.args.get('month',type=int),
        request.args.get('employee_id',type=int))})

@app.route('/api/admin/salary/mark-paid', methods=['POST'])
@api_login_required
def api_mark_paid():
    d = request.json or {}
    database.mark_paid(d['employee_id'], d['year'], d['month'])
    return jsonify({'success':True})

# ── LEAVE TYPES ──────────────────────────────────────────────────────────────
@app.route('/api/admin/leave-types', methods=['GET'])
@api_login_required
def api_leave_types():
    bid = _effective_branch_id()
    return jsonify({'leave_types': database.get_leave_types(active_only=False, branch_id=bid)})

@app.route('/api/admin/leave-types', methods=['POST'])
@api_login_required
def api_add_leave_type():
    d    = request.json or {}
    name = (d.get('name') or '').strip()
    if not name: return jsonify({'success':False,'message':'Name required'}), 400
    branch_id = _effective_branch_id() or int(d.get('branch_id') or 1)
    try:
        lid = database.add_leave_type(name, d.get('is_paid', 1), d.get('color'), branch_id=branch_id)
        return jsonify({'success':True,'id':lid,'message':f'Leave type "{name}" added'})
    except Exception as e:
        return jsonify({'success':False,'message':'That leave type already exists'}), 400

@app.route('/api/admin/leave-types/<int:lid>', methods=['PUT'])
@api_login_required
def api_upd_leave_type(lid):
    d = request.json or {}
    database.update_leave_type(lid, name=d.get('name'), is_paid=d.get('is_paid'),
                               color=d.get('color'), is_active=d.get('is_active'))
    return jsonify({'success':True,'message':'Leave type updated'})

@app.route('/api/admin/leave-types/<int:lid>', methods=['DELETE'])
@api_login_required
def api_del_leave_type(lid):
    database.delete_leave_type(lid)
    return jsonify({'success':True})

# ── LEAVE RECORDS ─────────────────────────────────────────────────────────────
@app.route('/api/admin/leave', methods=['GET'])
@api_login_required
def api_leave():
    start = request.args.get('start', (date.today()-timedelta(days=90)).isoformat())
    end   = request.args.get('end',   (date.today()+timedelta(days=90)).isoformat())
    eid   = request.args.get('employee_id', type=int)
    recs  = database.get_leave_records(start, end, eid)
    for r in recs:
        r['days'] = (date.fromisoformat(str(r['end_date'])) - date.fromisoformat(str(r['start_date']))).days + 1
    return jsonify({'records': recs})

@app.route('/api/admin/leave', methods=['POST'])
@api_login_required
def api_add_leave():
    d     = request.json or {}
    eid   = d.get('employee_id')
    ltid  = d.get('leave_type_id')
    start = d.get('start_date')
    end   = d.get('end_date') or start
    if not eid or not ltid or not start:
        return jsonify({'success':False,'message':'Employee, leave type and start date are required'}), 400
    if end < start:
        return jsonify({'success':False,'message':'End date cannot be before start date'}), 400
    is_paid = d.get('is_paid') if 'is_paid' in d and d.get('is_paid') is not None else None
    lid = database.add_leave_record(int(eid), int(ltid), start, end, d.get('notes'),
                                    is_paid, current_user.username)
    return jsonify({'success':True,'id':lid,'message':'Leave recorded'})

@app.route('/api/admin/leave/<int:lid>', methods=['PUT'])
@api_login_required
def api_upd_leave(lid):
    d  = request.json or {}
    kw = {}
    for f in ['leave_type_id','start_date','end_date','is_paid','notes']:
        if f in d: kw[f] = d[f]
    database.update_leave_record(lid, **kw)
    return jsonify({'success':True,'message':'Leave record updated'})

@app.route('/api/admin/leave/<int:lid>', methods=['DELETE'])
@api_login_required
def api_del_leave(lid):
    database.delete_leave_record(lid)
    return jsonify({'success':True})

# ── MONTHLY NOTES ──────────────────────────────────────────────────────────────
@app.route('/api/admin/notes', methods=['GET'])
@api_login_required
def api_notes():
    year  = request.args.get('year',  type=int, default=date.today().year)
    month = request.args.get('month', type=int, default=date.today().month)
    bid   = _effective_branch_id()
    emps  = database.get_employees_with_notes(year, month, bid)
    for e in emps: e.pop('pin_hash', None)
    return jsonify({'employees': emps, 'year': year, 'month': month})

@app.route('/api/admin/notes', methods=['POST'])
@api_login_required
def api_save_note():
    d     = request.json or {}
    eid   = d.get('employee_id'); year = d.get('year'); month = d.get('month')
    if not eid or not year or not month:
        return jsonify({'success':False,'message':'Missing data'}), 400
    database.set_monthly_note(int(eid), int(year), int(month), d.get('note',''), current_user.username)
    return jsonify({'success':True,'message':'Note saved'})

# ── BLOCKED SITES ──────────────────────────────────────────────────────────────
@app.route('/api/admin/blocked-sites', methods=['GET'])
@api_login_required
def api_blocked():
    return jsonify({'sites': database.get_blocked_sites(branch_id=_effective_branch_id())})

@app.route('/api/admin/blocked-sites', methods=['POST'])
@api_login_required
def api_add_blocked():
    d         = request.json or {}
    domain    = d.get('domain','').strip().lower()
    branch_id = _effective_branch_id() or int(d.get('branch_id') or 1)
    ok        = database.add_blocked_site(domain, d.get('category','restricted'), branch_id=branch_id)
    msg    = 'Added' if ok else 'Already exists'
    api_key, profile_id = _nextdns_config()
    if ok and api_key:
        synced, err = nextdns.add_domain(api_key, profile_id, domain)
        msg += ' — synced to NextDNS (all WiFi networks)' if synced else f' — NextDNS sync failed: {err}'
    return jsonify({'success':ok,'message':msg})

@app.route('/api/admin/blocked-sites/<int:sid>', methods=['DELETE'])
@api_login_required
def api_del_blocked(sid):
    sites  = {s['id']: s['domain'] for s in database.get_blocked_sites(branch_id=_effective_branch_id())}
    domain = sites.get(sid)
    if not domain:
        return jsonify({'success':False,'message':'Not found'}), 404
    database.remove_blocked_site(sid)
    api_key, profile_id = _nextdns_config()
    if domain and api_key:
        nextdns.remove_domain(api_key, profile_id, domain)
    return jsonify({'success':True})

# ── WIFI NETWORKS ────────────────────────────────────────────────────────────────
@app.route('/api/admin/wifi-networks', methods=['GET'])
@api_login_required
def api_wifi_list():
    return jsonify({'networks': database.get_wifi_networks(branch_id=_effective_branch_id())})

@app.route('/api/admin/wifi-networks', methods=['POST'])
@api_login_required
def api_wifi_add():
    d    = request.json or {}
    ssid = d.get('ssid','').strip()
    if not ssid:
        return jsonify({'success':False,'message':'Network name is required'}), 400
    branch_id = _effective_branch_id() or int(d.get('branch_id') or 1)
    database.add_wifi_network(ssid, d.get('password',''), d.get('label',''), branch_id=branch_id)
    database.log_event('wifi_added', current_user.username, _client_ip(), ssid, branch_id=branch_id)
    return jsonify({'success':True,'message':'Saved'})

@app.route('/api/admin/wifi-networks/<int:wid>', methods=['DELETE'])
@api_login_required
def api_wifi_del(wid):
    nets = {n['id'] for n in database.get_wifi_networks(branch_id=_effective_branch_id())}
    if wid not in nets:
        return jsonify({'success':False,'message':'Not found'}), 404
    database.remove_wifi_network(wid)
    return jsonify({'success':True})

# ── NETWORK SECURITY ───────────────────────────────────────────────────────────
@app.route('/api/admin/network/info')
@api_login_required
def api_net_info():
    return jsonify({'info':network_manager.get_network_info(),
                    'hosts_status':network_manager.get_hosts_status()})

@app.route('/api/admin/network/scan')
@api_login_required
def api_net_scan():
    devices = network_manager.scan_network()
    return jsonify({'devices':devices,'count':len(devices)})

@app.route('/api/admin/network/apply-hosts', methods=['POST'])
@api_login_required
def api_apply_hosts():
    sites   = database.get_blocked_sites()
    domains = [s['domain'] for s in sites if s['is_active']]
    ok, msg = network_manager.apply_hosts_blocking(domains)
    if ok: database.log_event('hosts_applied', current_user.username, _client_ip(), f'{len(domains)} domains')
    return jsonify({'success':ok,'message':msg})

@app.route('/api/admin/network/remove-hosts', methods=['POST'])
@api_login_required
def api_remove_hosts():
    ok, msg = network_manager.remove_hosts_blocking()
    if ok: database.log_event('hosts_removed', current_user.username, _client_ip(), '')
    return jsonify({'success':ok,'message':msg})

# ── NEXTDNS (network-wide blocking, all WiFi networks / routers) ───────────────
@app.route('/api/admin/network/nextdns', methods=['GET'])
@api_login_required
def api_nextdns_get():
    api_key, profile_id = _nextdns_config()
    connected = False
    if api_key and profile_id:
        connected, _ = nextdns.test_connection(api_key, profile_id)
    return jsonify({
        'configured': bool(api_key and profile_id),
        'connected': connected,
        'profile_id': profile_id,
        'api_key_set': bool(api_key)
    })

@app.route('/api/admin/network/nextdns', methods=['POST'])
@api_login_required
def api_nextdns_save():
    d          = request.json or {}
    api_key    = d.get('api_key','').strip()
    profile_id = d.get('profile_id','').strip()
    if not api_key or not profile_id:
        return jsonify({'success':False,'message':'API key and Profile ID are required'}), 400
    ok, message = nextdns.test_connection(api_key, profile_id)
    if not ok:
        return jsonify({'success':False,'message':f'Could not connect: {message}'}), 400
    database.set_setting('nextdns_api_key', api_key)
    database.set_setting('nextdns_profile_id', profile_id)
    database.log_event('nextdns_configured', current_user.username, _client_ip(), profile_id)
    return jsonify({'success':True,'message':message})

@app.route('/api/admin/network/nextdns/sync', methods=['POST'])
@api_login_required
def api_nextdns_sync():
    api_key, profile_id = _nextdns_config()
    if not api_key or not profile_id:
        return jsonify({'success':False,'message':'NextDNS is not configured yet'}), 400
    domains = [s['domain'] for s in database.get_blocked_sites() if s['is_active']]
    added, failed = nextdns.sync_all(api_key, profile_id, domains)
    database.log_event('nextdns_synced', current_user.username, _client_ip(), f'{added} added, {len(failed)} failed')
    msg = f'Synced {added} domain(s) to NextDNS'
    if failed: msg += f' — failed: {", ".join(failed)}'
    return jsonify({'success':True,'message':msg,'added':added,'failed':failed})

# ── THEME / SETTINGS ───────────────────────────────────────────────────────────
@app.route('/api/admin/theme', methods=['GET'])
@api_login_required
def api_get_theme():
    return jsonify({'theme':database.get_theme(_effective_branch_id())})

@app.route('/api/admin/theme', methods=['POST'])
@api_login_required
def api_save_theme():
    bid = _effective_branch_id()
    if not bid:
        return jsonify({'success':False,'message':'Select a specific branch first'}), 400
    d = request.json or {}
    updates = {}
    for k in ['primary','secondary','accent','dark','text','font','logo_text','dark_mode','logo_url']:
        if k in d:
            v = d[k]
            updates[k] = v if k in ('font','logo_text','logo_url') else str(v).replace('#','')
    database.save_theme(bid, updates)
    return jsonify({'success':True,'message':'Theme saved'})

@app.route('/api/admin/change-password', methods=['POST'])
@api_login_required
def api_change_pw():
    d    = request.json or {}
    ok, msg = database.change_password(current_user.username,
                                       d.get('current_password',''), d.get('new_password',''))
    if ok: logout_user()
    return jsonify({'success':ok,'message':msg})

# ── ADMIN USERS ────────────────────────────────────────────────────────────────
@app.route('/api/admin/users', methods=['GET'])
@api_login_required
def api_users():
    return jsonify({'users':database.get_all_admins()})

@app.route('/api/admin/users', methods=['POST'])
@_require_superadmin
def api_add_user():
    d = request.json or {}
    try:
        database.create_admin(d['username'],d['password'],d.get('role','admin'),d.get('branch_id'))
        return jsonify({'success':True,'message':'User created'})
    except Exception as e:
        return jsonify({'success':False,'message':str(e)}), 500

# ── OWNER DASHBOARD ────────────────────────────────────────────────────────────
@app.route('/api/admin/owner/overview')
@_require_superadmin
def api_owner_overview():
    return jsonify(database.get_owner_overview())

@app.route('/api/admin/owner/inbox')
@_require_superadmin
def api_owner_inbox():
    return jsonify({'messages': database.get_support_messages(request.args.get('status') or None)})

@app.route('/api/admin/owner/inbox/<int:mid>/resolve', methods=['POST'])
@_require_superadmin
def api_owner_resolve(mid):
    d = request.json or {}
    database.resolve_support_message(mid, d.get('reply') or None)
    return jsonify({'success':True,'message':'Marked resolved'})

# ── SUPPORT (branch admin → owner) ────────────────────────────────────────────
@app.route('/api/admin/support', methods=['GET'])
@api_login_required
def api_my_support():
    return jsonify({'messages': database.get_my_support_messages(current_user.username)})

@app.route('/api/admin/support', methods=['POST'])
@api_login_required
def api_send_support():
    d       = request.json or {}
    subject = (d.get('subject') or '').strip()
    message = (d.get('message') or '').strip()
    if not subject or not message:
        return jsonify({'success':False,'message':'Subject and message are required'}), 400
    database.create_support_message(current_user.branch_id, current_user.username, subject, message)
    return jsonify({'success':True,'message':'Sent to ShiftGuard support'})

# ── LOGS ───────────────────────────────────────────────────────────────────────
@app.route('/api/admin/logs')
@api_login_required
def api_logs():
    return jsonify({'logs':database.get_logs()})

# ── PHOTOS ─────────────────────────────────────────────────────────────────────
@app.route('/api/admin/photos')
@api_login_required
def api_photos():
    start = request.args.get('start',(date.today()-timedelta(days=30)).isoformat())
    end   = request.args.get('end',  date.today().isoformat())
    logs  = database.get_attendance_range(start, end)
    photos= []
    for l in logs:
        for field,label in [('check_in_photo','Check In'),('check_out_photo','Check Out')]:
            if l.get(field):
                photos.append({'att_id':l['id'],'field':field,'employee':l['name'],
                                'date':l['date'],'type':label,'url':f"/static/{l[field]}"})
    return jsonify({'photos':photos})

@app.route('/api/admin/photo-settings', methods=['GET'])
@api_login_required
def api_get_photo_settings():
    return jsonify(database.get_photo_settings())

@app.route('/api/admin/photo-settings', methods=['POST'])
@api_login_required
def api_set_photo_settings():
    d = request.json or {}
    database.set_photo_settings(enabled=d.get('enabled'), retention_days=d.get('retention_days'))
    return jsonify({'success':True,'message':'Photo settings saved'})

@app.route('/api/admin/photos/purge', methods=['POST'])
@api_login_required
def api_purge_photos():
    settings = database.get_photo_settings()
    old = database.find_old_photos(settings['retention_days'])
    for _, _, relpath in old:
        _remove_photo_file(relpath)
    database.purge_photo_refs([(rid, field) for rid, field, _ in old])
    database.mark_photo_purge_ran()
    database.log_event('photos_manual_purge', current_user.username, _client_ip(), f'{len(old)} photo(s)')
    return jsonify({'success':True,'deleted':len(old)})

@app.route('/api/admin/photos/bulk-delete', methods=['POST'])
@api_login_required
def api_bulk_delete_photos():
    d     = request.json or {}
    items = d.get('items') or []
    pairs = []
    for it in items:
        rid, field = it.get('att_id'), it.get('field')
        if not rid or field not in ('check_in_photo','check_out_photo'): continue
        r = database.q('SELECT * FROM attendance WHERE id=?', (rid,))
        if r and r[0].get(field): _remove_photo_file(r[0][field])
        pairs.append((rid, field))
    database.delete_photos_bulk(pairs)
    database.log_event('photos_bulk_delete', current_user.username, _client_ip(), f'{len(pairs)} photo(s)')
    return jsonify({'success':True,'deleted':len(pairs)})

# ── BACKUP ─────────────────────────────────────────────────────────────────────
@app.route('/api/admin/backup')
@api_login_required
def api_backup():
    ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = os.path.join(config.BACKUP_DIR, f'shiftguard_backup_{ts}.db')
    shutil.copy2(config.DATABASE_PATH, dest)
    return send_file(dest, as_attachment=True, download_name=f'shiftguard_backup_{ts}.db')

# ── REPORTS (daily / monthly, each exportable as Excel, Word or PDF) ───────────
EXPORT_MIME = {
    'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'word':  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'pdf':   'application/pdf',
}

@app.route('/api/admin/report/daily')
@app.route('/api/admin/report/daily/<fmt>')
@api_login_required
def api_daily_report(fmt='excel'):
    day = request.args.get('date', date.today().isoformat())
    bid = _effective_branch_id()
    return _make_report('daily', fmt, day=day, branch_id=bid)

@app.route('/api/admin/report/monthly')
@app.route('/api/admin/report/monthly/<fmt>')
@api_login_required
def api_monthly_report(fmt='excel'):
    month_str = request.args.get('month', date.today().strftime('%Y-%m'))
    bid       = _effective_branch_id()
    return _make_report('monthly', fmt, month_str=month_str, branch_id=bid)

def _daily_sections(day, branch_id=None):
    logs = database.get_attendance_range(day, day, branch_id=branch_id)
    headers = ['Employee','Branch','Position','Date','Check In','Check In IP','Check Out','Check Out IP','Hours','Late(min)','Status']
    rows = [[l['name'], l.get('branch_name',''), l['position'] or '', l['date'],
             str(l['check_in'])[:16] if l['check_in'] else '—', l.get('check_in_ip') or '—',
             str(l['check_out'])[:16] if l['check_out'] else '—', l.get('check_out_ip') or '—',
             round(l['hours_worked'] or 0,2), l['minutes_late'] or 0, l['status'] or '—'] for l in logs]
    return [('Daily Attendance', headers, rows)]

def _monthly_sections(year, month, branch_id=None):
    first = f'{year}-{month:02d}-01'
    last  = f'{year}-{month:02d}-{calendar.monthrange(year,month)[1]}'
    emps  = database.get_employees(active_only=True, branch_id=branch_id)
    logs  = database.get_attendance_range(first, last, branch_id=branch_id)
    leave = database.get_leave_records(first, last, None)
    if branch_id:
        emp_ids = {e['id'] for e in emps}
        leave = [r for r in leave if r['employee_id'] in emp_ids]
    notes = database.get_monthly_notes(year, month)
    if branch_id:
        emp_ids = {e['id'] for e in emps}
        notes = [n for n in notes if n['employee_id'] in emp_ids]

    sum_headers = ['Employee','Branch','Scheduled','Present','Paid Leave','Unpaid Leave',
                   'Absent','Late Days','Total Hours','Overtime','Late Min']
    sal_headers = ['Employee','Type','Base / Rate','Leave Pay','Absent Ded.','Late Ded.','OT Pay','Net Salary']
    sum_rows, sal_rows = [], []
    for e in emps:
        c = database.calculate_salary(e['id'], year, month)
        sum_rows.append([e['name'], e.get('branch_name',''), c['working_days'], c['days_present'],
                          c['days_leave_paid'], c['days_leave_unpaid'], c['days_absent'],
                          c['days_late'], c['total_hours'], c['overtime_hours'], c['total_late_min']])
        sal_rows.append([e['name'], c['salary_type'].title(), c['base_salary'], c['leave_pay'],
                          c['absent_deduction'], c['late_deduction'], c['overtime_pay'], c['net_salary']])

    daily_headers = ['Employee','Date','Check In','Check In IP','Check Out','Check Out IP','Hours','OT','Late(min)','Status']
    daily_rows = [[l['name'], l['date'],
                   str(l['check_in'])[:16] if l['check_in'] else '—', l.get('check_in_ip') or '—',
                   str(l['check_out'])[:16] if l['check_out'] else '—', l.get('check_out_ip') or '—',
                   round(l['hours_worked'] or 0,2), round(l['overtime_hours'] or 0,2),
                   l['minutes_late'] or 0, l['status'] or '—'] for l in logs]

    leave_headers = ['Employee','Leave Type','Start','End','Paid?','Notes']
    leave_rows = [[r['employee_name'], r['leave_type_name'], r['start_date'], r['end_date'],
                   'Yes' if r['is_paid'] else 'No', r['notes'] or ''] for r in leave]

    notes_headers = ['Employee','Note']
    notes_rows = [[n['employee_name'], n['note'] or ''] for n in notes]

    return [
        ('Attendance Summary', sum_headers, sum_rows),
        ('Salary Breakdown',   sal_headers, sal_rows),
        ('Daily Log',          daily_headers, daily_rows),
        ('Leave',              leave_headers, leave_rows),
        ('Monthly Notes',      notes_headers, notes_rows),
    ]

def _make_report(rtype, fmt='excel', **kw):
    if fmt not in EXPORT_MIME:
        return jsonify({'error':'Invalid format. Use excel, word or pdf.'}), 400
    try:
        if rtype == 'daily':
            day = kw['day']; bid = kw.get('branch_id')
            sections = _daily_sections(day, bid)
            title = f'ShiftGuard — Daily Report — {day}'
            base  = f'ShiftGuard_Daily_{day}'
        else:
            ms = kw['month_str']; bid = kw.get('branch_id')
            year, month = map(int, ms.split('-'))
            mname = calendar.month_name[month]
            sections = _monthly_sections(year, month, bid)
            title = f'ShiftGuard — Monthly Report — {mname} {year}'
            base  = f'ShiftGuard_Monthly_{ms}'

        if fmt == 'excel':
            sheets = [(h, hdrs, rows, None) for h, hdrs, rows in sections]
            buf, fname = reports.excel_multi(title, sheets, base)
        elif fmt == 'word':
            buf, fname = reports.word_table(title, None, None, base, sections=sections)
        else:
            buf, fname = reports.pdf_multi(title, sections, base)

        return send_file(buf, mimetype=EXPORT_MIME[fmt], as_attachment=True, download_name=fname)
    except Exception as e:
        logger.error(f"Report error: {e}")
        return jsonify({'error':str(e)}), 500

# ── GENERIC TABLE EXPORTS (Attendance / Employees / Salary / Leave / Notes) ────
def _export_data(section):
    bid = _effective_branch_id()

    if section == 'attendance':
        start = request.args.get('start', (date.today()-timedelta(days=30)).isoformat())
        end   = request.args.get('end',   date.today().isoformat())
        eid   = request.args.get('employee_id', type=int)
        logs  = database.get_attendance_range(start, end, eid, bid)
        headers = ['Employee','Branch','Date','Check In','Check In IP','Check Out','Check Out IP','Hours','OT','Late(min)','Status','Notes']
        rows = [[l['name'], l.get('branch_name',''), l['date'],
                 str(l['check_in'])[:16] if l['check_in'] else '—', l.get('check_in_ip') or '—',
                 str(l['check_out'])[:16] if l['check_out'] else '—', l.get('check_out_ip') or '—',
                 round(l['hours_worked'] or 0,2), round(l['overtime_hours'] or 0,2),
                 l['minutes_late'] or 0, l['status'] or '—', l['notes'] or ''] for l in logs]
        return f'Attendance Records ({start} to {end})', headers, rows, f'ShiftGuard_Attendance_{start}_{end}'

    if section == 'employees':
        emps = database.get_employees(active_only=True, branch_id=bid)
        headers = ['Name','Position','Branch','Phone','Shift Start','Shift End',
                   'Working Days','Salary Type','Salary Amount','Hire Date']
        rows = [[e['name'], e['position'] or '', e.get('branch_name',''), e['phone'] or '',
                 e['shift_start'], e['shift_end'], (e['working_days'] or '').replace(',', ' '),
                 (e['salary_type'] or 'monthly').title(), e['salary_amount'], e['hire_date'] or ''] for e in emps]
        return 'Employee List', headers, rows, 'ShiftGuard_Employees'

    if section == 'salary':
        year  = request.args.get('year',  type=int)
        month = request.args.get('month', type=int)
        eid   = request.args.get('employee_id', type=int)
        recs  = database.get_salary_records(year, month, eid)
        headers = ['Employee','Year','Month','Type','Base / Rate','Present','Paid Leave','Unpaid Leave',
                   'Absent','Late Days','Late Ded.','Absent Ded.','OT Pay','Leave Pay','Net Salary','Paid']
        rows = [[r['name'], r['year'], r['month'], (r.get('salary_type') or 'monthly').title(),
                 r['base_salary'], r['days_present'], r.get('days_leave_paid',0), r.get('days_leave_unpaid',0),
                 r['days_absent'], r['days_late'], r['late_deduction'], r['absent_deduction'],
                 r['overtime_pay'], r.get('leave_pay',0), r['net_salary'],
                 'Yes' if r['is_paid'] else 'No'] for r in recs]
        return 'Salary Records', headers, rows, 'ShiftGuard_Salary'

    if section == 'leave':
        start = request.args.get('start', (date.today()-timedelta(days=90)).isoformat())
        end   = request.args.get('end',   (date.today()+timedelta(days=90)).isoformat())
        eid   = request.args.get('employee_id', type=int)
        recs  = database.get_leave_records(start, end, eid)
        headers = ['Employee','Leave Type','Start Date','End Date','Days','Paid?','Notes']
        rows = []
        for r in recs:
            days = (date.fromisoformat(str(r['end_date'])) - date.fromisoformat(str(r['start_date']))).days + 1
            rows.append([r['employee_name'], r['leave_type_name'], r['start_date'], r['end_date'],
                         days, 'Yes' if r['is_paid'] else 'No', r['notes'] or ''])
        return f'Leave Records ({start} to {end})', headers, rows, 'ShiftGuard_Leave'

    if section == 'notes':
        year  = request.args.get('year',  type=int, default=date.today().year)
        month = request.args.get('month', type=int, default=date.today().month)
        emps  = database.get_employees_with_notes(year, month, bid)
        mname = calendar.month_name[month]
        headers = ['Employee','Branch','Note']
        rows = [[e['name'], e.get('branch_name',''), e['note'] or ''] for e in emps]
        return f'Monthly Notes — {mname} {year}', headers, rows, f'ShiftGuard_Notes_{year}_{month:02d}'

    raise ValueError('Unknown export section')

@app.route('/api/admin/export/<section>/<fmt>')
@api_login_required
def api_export(section, fmt):
    if fmt not in EXPORT_MIME:
        return jsonify({'error':'Invalid format. Use excel, word or pdf.'}), 400
    try:
        title, headers, rows, base = _export_data(section)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    try:
        if fmt == 'excel':
            buf, fname = reports.excel_table(title, headers, rows, base)
        elif fmt == 'word':
            buf, fname = reports.word_table(title, headers, rows, base)
        else:
            buf, fname = reports.pdf_table(title, headers, rows, base)
        return send_file(buf, mimetype=EXPORT_MIME[fmt], as_attachment=True, download_name=fname)
    except Exception as e:
        logger.error(f"Export error: {e}")
        return jsonify({'error':str(e)}), 500

# ── ERRORS ─────────────────────────────────────────────────────────────────────
@app.errorhandler(404)
def e404(e): return render_template('error.html',error='Page not found',theme=database.get_theme()),404
@app.errorhandler(500)
def e500(e): return render_template('error.html',error='Server error',theme=database.get_theme()),500

# ── START ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    logger.info(f"Starting ShiftGuard on port {config.PORT}")
    try:
        from waitress import serve
        logger.info("Production server: Waitress")
        serve(app, host=config.HOST, port=config.PORT, threads=4)
    except ImportError:
        logger.warning("Waitress not found, using Flask dev server")
        app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True)
