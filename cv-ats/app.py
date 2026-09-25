import hmac
import logging
import os
import uuid
from functools import wraps

from flask import (Flask, abort, flash, jsonify, redirect, render_template, request,
                   send_file, session, url_for)
from werkzeug.utils import secure_filename

import db
import worker
from config import (ALLOWED_EXTENSIONS, ANTHROPIC_API_KEY, APP_PASSWORD, CLAUDE_MODEL,
                    MAX_UPLOAD_MB, PORT, SECRET_KEY, UPLOAD_DIR)
from excel import build_workbook

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    MAX_CONTENT_LENGTH=MAX_UPLOAD_MB * 1024 * 1024,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_HTTPONLY=True,
)

db.init_db()
worker.resume_unfinished()


# ── Auth ────────────────────────────────────────────────────────────────

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if APP_PASSWORD and not session.get('ok'):
            return redirect(url_for('login', next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if hmac.compare_digest(request.form.get('password', ''), APP_PASSWORD):
            session['ok'] = True
            session.permanent = True
            nxt = request.args.get('next', '')
            return redirect(nxt if nxt.startswith('/') and not nxt.startswith('//') else url_for('index'))
        flash('Wrong password.', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.context_processor
def inject_globals():
    return {'api_key_missing': not ANTHROPIC_API_KEY, 'model': CLAUDE_MODEL,
            'auth_enabled': bool(APP_PASSWORD)}


# ── Helpers ─────────────────────────────────────────────────────────────

def job_or_404(job_id):
    job = db.get_job(job_id)
    if job is None:
        abort(404)
    return job


def candidate_or_404(cid):
    cand = db.get_candidate(cid)
    if cand is None:
        abort(404)
    return cand


def remove_file(stored_name):
    try:
        os.remove(os.path.join(UPLOAD_DIR, stored_name))
    except OSError:
        pass


def job_form():
    title = request.form.get('title', '').strip()
    if not title:
        flash('Job title is required.', 'error')
    return title, request.form.get('description', '').strip(), request.form.get('criteria', '').strip()


# ── Jobs ────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    return render_template('index.html', jobs=db.list_jobs())


@app.route('/jobs', methods=['POST'])
@login_required
def create_job():
    title, description, criteria = job_form()
    if not title:
        return redirect(url_for('index'))
    return redirect(url_for('job', job_id=db.create_job(title, description, criteria)))


@app.route('/jobs/<int:job_id>')
@login_required
def job(job_id):
    return render_template('job.html', job=job_or_404(job_id),
                           candidates=db.list_candidates(job_id),
                           accept=','.join('.' + e for e in sorted(ALLOWED_EXTENSIONS)))


@app.route('/jobs/<int:job_id>/edit', methods=['POST'])
@login_required
def edit_job(job_id):
    job_or_404(job_id)
    title, description, criteria = job_form()
    if title:
        db.update_job(job_id, title, description, criteria)
        if request.form.get('rerate'):
            worker.enqueue(db.job_candidate_ids(job_id))
            flash('Job saved. All candidates are being re-rated.', 'ok')
        else:
            flash('Job saved.', 'ok')
    return redirect(url_for('job', job_id=job_id))


@app.route('/jobs/<int:job_id>/delete', methods=['POST'])
@login_required
def delete_job(job_id):
    job_or_404(job_id)
    for c in db.list_candidates(job_id):
        remove_file(c['stored_name'])
    db.delete_job(job_id)
    flash('Job deleted.', 'ok')
    return redirect(url_for('index'))


@app.route('/jobs/<int:job_id>/upload', methods=['POST'])
@login_required
def upload(job_id):
    job_or_404(job_id)
    new_ids, skipped = [], []
    for f in request.files.getlist('files'):
        if not f or not f.filename:
            continue
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        if ext not in ALLOWED_EXTENSIONS:
            skipped.append(f.filename)
            continue
        stored = f'{uuid.uuid4().hex}.{ext}'
        f.save(os.path.join(UPLOAD_DIR, stored))
        original = os.path.basename(f.filename) or secure_filename(f.filename)
        new_ids.append(db.add_candidate(job_id, original, stored))
    worker.enqueue(new_ids)
    if new_ids:
        flash(f'{len(new_ids)} CV(s) uploaded — analysing now.', 'ok')
    if skipped:
        flash(f'Skipped unsupported files: {", ".join(skipped)}', 'error')
    return redirect(url_for('job', job_id=job_id))


@app.route('/jobs/<int:job_id>/rerate', methods=['POST'])
@login_required
def rerate(job_id):
    job_or_404(job_id)
    worker.enqueue(db.job_candidate_ids(job_id))
    flash('Re-rating all candidates.', 'ok')
    return redirect(url_for('job', job_id=job_id))


@app.route('/jobs/<int:job_id>/retry', methods=['POST'])
@login_required
def retry_failed(job_id):
    job_or_404(job_id)
    ids = db.ids_with_status(['error'], job_id)
    worker.enqueue(ids)
    flash(f'Retrying {len(ids)} failed CV(s).', 'ok')
    return redirect(url_for('job', job_id=job_id))


@app.route('/jobs/<int:job_id>/export.xlsx')
@login_required
def export_job(job_id):
    job = job_or_404(job_id)
    buf = build_workbook([(job, db.list_candidates(job_id))])
    name = f"candidates_{secure_filename(job['title']) or job_id}.xlsx"
    return send_file(buf, as_attachment=True, download_name=name,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/export.xlsx')
@login_required
def export_all():
    data = [(j, db.list_candidates(j['id'])) for j in db.list_jobs()]
    return send_file(build_workbook(data), as_attachment=True, download_name='all_candidates.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/api/jobs/<int:job_id>/status')
@login_required
def job_status(job_id):
    return jsonify(db.job_status_summary(job_id))


# ── Candidates ──────────────────────────────────────────────────────────

@app.route('/candidates/<int:cid>')
@login_required
def candidate(cid):
    cand = candidate_or_404(cid)
    return render_template('candidate.html', c=cand, job=db.get_job(cand['job_id']))


@app.route('/candidates/<int:cid>/file')
@login_required
def candidate_file(cid):
    cand = candidate_or_404(cid)
    path = os.path.join(UPLOAD_DIR, cand['stored_name'])
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=request.args.get('dl') == '1',
                     download_name=cand['filename'])


@app.route('/candidates/<int:cid>/reanalyze', methods=['POST'])
@login_required
def reanalyze(cid):
    candidate_or_404(cid)
    worker.enqueue([cid])
    flash('Re-analysing this CV.', 'ok')
    return redirect(url_for('candidate', cid=cid))


@app.route('/candidates/<int:cid>/delete', methods=['POST'])
@login_required
def delete_candidate(cid):
    cand = candidate_or_404(cid)
    remove_file(cand['stored_name'])
    db.delete_candidate(cid)
    flash('Candidate deleted.', 'ok')
    return redirect(url_for('job', job_id=cand['job_id']))


@app.route('/health')
def health():
    return {'status': 'ok'}


@app.errorhandler(413)
def too_large(_):
    flash(f'Upload too large (limit {MAX_UPLOAD_MB} MB per upload). Try fewer files at once.', 'error')
    return redirect(request.referrer or url_for('index'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False)
