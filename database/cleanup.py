"""기한이 지난 공고를 백업 후 제거한다."""
from datetime import datetime
from contextlib import closing
from pathlib import Path
import sqlite3
from uuid import uuid4

from job_policy import expired


def delete_expired_jobs(db_path, today):
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    backup_path = None
    with closing(sqlite3.connect(path, timeout=30)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        rows = conn.execute('SELECT id, deadline, created_at FROM job_postings').fetchall()
        ids = [(job_id,) for job_id, deadline, collected_at in rows
               if expired(deadline, collected_at, today)]
        if not ids:
            return 0, None
        backup_dir = path.parent / 'backups'
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / f'jobs_before_cleanup_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}.db'
        # 별도 읽기 연결로 SQLite 백업을 생성한다. 실패하면 삭제하지 않는다.
        with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup_path)) as destination:
            source.backup(destination)
        conn.executemany('DELETE FROM job_postings WHERE id = ?', ids)
    return len(ids), backup_path
