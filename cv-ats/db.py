import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    criteria    TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id         INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    filename       TEXT NOT NULL,
    stored_name    TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',  -- pending | processing | done | error
    error          TEXT,
    name           TEXT,
    email          TEXT,
    phone          TEXT,
    score          INTEGER,
    recommendation TEXT,
    data_json      TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidates_job ON candidates(job_id);
"""


def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


@contextmanager
def connect():
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as c:
        c.execute('PRAGMA journal_mode = WAL')
        c.executescript(SCHEMA)


# ── Jobs ────────────────────────────────────────────────────────────────

def list_jobs():
    with connect() as c:
        return c.execute("""
            SELECT j.*,
                   COUNT(ca.id) AS total,
                   SUM(ca.status = 'done') AS done,
                   SUM(ca.status IN ('pending','processing')) AS queued,
                   MAX(ca.score) AS top_score
            FROM jobs j LEFT JOIN candidates ca ON ca.job_id = j.id
            GROUP BY j.id ORDER BY j.id DESC
        """).fetchall()


def get_job(job_id):
    with connect() as c:
        return c.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()


def create_job(title, description, criteria):
    with connect() as c:
        cur = c.execute(
            'INSERT INTO jobs (title, description, criteria, created_at) VALUES (?,?,?,?)',
            (title, description, criteria, now()))
        return cur.lastrowid


def update_job(job_id, title, description, criteria):
    with connect() as c:
        c.execute('UPDATE jobs SET title=?, description=?, criteria=? WHERE id=?',
                  (title, description, criteria, job_id))


def delete_job(job_id):
    with connect() as c:
        c.execute('DELETE FROM jobs WHERE id = ?', (job_id,))


# ── Candidates ──────────────────────────────────────────────────────────

def _decode(row):
    if row is None:
        return None
    d = dict(row)
    d['data'] = json.loads(d['data_json']) if d.get('data_json') else {}
    return d


def list_candidates(job_id):
    with connect() as c:
        rows = c.execute("""
            SELECT * FROM candidates WHERE job_id = ?
            ORDER BY (status = 'done') DESC, score DESC, id DESC
        """, (job_id,)).fetchall()
    return [_decode(r) for r in rows]


def get_candidate(cid):
    with connect() as c:
        return _decode(c.execute('SELECT * FROM candidates WHERE id = ?', (cid,)).fetchone())


def add_candidate(job_id, filename, stored_name):
    ts = now()
    with connect() as c:
        cur = c.execute("""
            INSERT INTO candidates (job_id, filename, stored_name, status, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', ?, ?)
        """, (job_id, filename, stored_name, ts, ts))
        return cur.lastrowid


def set_status(cid, status, error=None):
    with connect() as c:
        c.execute('UPDATE candidates SET status=?, error=?, updated_at=? WHERE id=?',
                  (status, error, now(), cid))


def save_result(cid, data):
    with connect() as c:
        c.execute("""
            UPDATE candidates
            SET status='done', error=NULL, name=?, email=?, phone=?, score=?,
                recommendation=?, data_json=?, updated_at=?
            WHERE id=?
        """, (data.get('full_name'), data.get('email'), data.get('phone'),
              data.get('score'), data.get('recommendation'),
              json.dumps(data, ensure_ascii=False), now(), cid))


def delete_candidate(cid):
    with connect() as c:
        c.execute('DELETE FROM candidates WHERE id = ?', (cid,))


def ids_with_status(statuses, job_id=None):
    q = f"SELECT id FROM candidates WHERE status IN ({','.join('?' * len(statuses))})"
    params = list(statuses)
    if job_id is not None:
        q += ' AND job_id = ?'
        params.append(job_id)
    with connect() as c:
        return [r['id'] for r in c.execute(q, params).fetchall()]


def job_candidate_ids(job_id):
    with connect() as c:
        return [r['id'] for r in c.execute(
            'SELECT id FROM candidates WHERE job_id = ?', (job_id,)).fetchall()]


def job_status_summary(job_id):
    with connect() as c:
        rows = c.execute(
            'SELECT status, COUNT(*) AS n FROM candidates WHERE job_id = ? GROUP BY status',
            (job_id,)).fetchall()
    return {r['status']: r['n'] for r in rows}
