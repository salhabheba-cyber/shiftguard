"""Background queue: CVs are analysed in threads so uploads return instantly."""
import logging
import os
from concurrent.futures import ThreadPoolExecutor

import db
from analyzer import AnalysisError, analyze
from config import MAX_WORKERS, UPLOAD_DIR
from extractor import ExtractionError, to_content_blocks

log = logging.getLogger('ats.worker')
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


def process(cid):
    cand = db.get_candidate(cid)
    if cand is None:
        return
    job = db.get_job(cand['job_id'])
    if job is None:
        return
    db.set_status(cid, 'processing')
    try:
        blocks = to_content_blocks(os.path.join(UPLOAD_DIR, cand['stored_name']), cand['filename'])
        db.save_result(cid, analyze(job, blocks))
    except (ExtractionError, AnalysisError) as e:
        db.set_status(cid, 'error', str(e))
    except Exception as e:  # keep the worker alive whatever happens
        log.exception('Failed to process candidate %s', cid)
        db.set_status(cid, 'error', f'Unexpected error: {e}')


def enqueue(cids):
    for cid in cids:
        db.set_status(cid, 'pending')
        _executor.submit(process, cid)


def resume_unfinished():
    """Re-queue anything that was in flight when the server last stopped."""
    ids = db.ids_with_status(['pending', 'processing'])
    if ids:
        log.info('Resuming %d unfinished CVs', len(ids))
        enqueue(ids)
