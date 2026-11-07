"""Consistent SQLite backup with rotation. Run daily by curri-backup.timer on the service server.

Usage: python3 tools/backup_db.py <db> <backup dir> [keep=14]
"""
import sqlite3
import sys
import time
from pathlib import Path


def backup(db, folder, keep=14):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'curri-{time.strftime("%Y%m%d-%H%M")}.sqlite'
    source, dest = sqlite3.connect(db), sqlite3.connect(target)
    with dest:
        source.backup(dest)
    source.close()
    dest.close()
    target.chmod(0o600)
    for old in sorted(folder.glob('curri-*.sqlite'))[:-keep]:
        old.unlink()
    return target


if __name__ == '__main__':
    print(backup(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 14))
