"""Server-side error log for the admin console: request failures and background-thread errors, kept 30 days.

Only the exception type, where it happened and a short message are stored (no request bodies, credentials or
personal data). `record()` is a no-op until the platform configures a store.
"""
import os
import shutil
import time
import traceback

RETENTION = 30 * 86400
_store = None
STARTED = time.time()


def configure(store):
    global _store
    _store = store
    with store.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS errors (id INTEGER PRIMARY KEY, ts REAL NOT NULL, place TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL)')
        db.execute('DELETE FROM errors WHERE ts<?', (time.time() - RETENTION,))


def record(place, exc):
    """Store the exception type and the innermost code location (file:line), not the message text."""
    if _store is None:
        return
    try:
        frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
        where = f'{os.path.basename(frames[-1].filename)}:{frames[-1].lineno} {frames[-1].name}' if frames else ''
        with _store.db() as db:
            db.execute('INSERT INTO errors(ts,place,kind,detail) VALUES (?,?,?,?)', (time.time(), place[:80], type(exc).__name__, where[:200]))
    except Exception:
        pass


def recent(limit=200):
    if _store is None:
        return []
    with _store.db() as db:
        return [dict(r) for r in db.execute('SELECT * FROM errors ORDER BY id DESC LIMIT ?', (limit,))]


def system(db_path):
    """Host health for the console: load, memory, disk, uptime of the service process and database size."""
    mem = {}
    try:
        for line in open('/proc/meminfo'):
            key, value = line.split(':')
            mem[key] = int(value.split()[0]) // 1024
    except OSError:
        pass
    disk = shutil.disk_usage('/')
    return {'load': os.getloadavg() if hasattr(os, 'getloadavg') else None,
            'memory_mb': {'total': mem.get('MemTotal'), 'available': mem.get('MemAvailable')},
            'disk_gb': {'total': round(disk.total / 1e9, 1), 'free': round(disk.free / 1e9, 1)},
            'service_uptime_s': int(time.time() - STARTED),
            'db_mb': round(os.path.getsize(db_path) / 1e6, 2) if os.path.exists(db_path) else None}
