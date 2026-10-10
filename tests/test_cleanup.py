from datetime import date
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from database.cleanup import delete_expired_jobs
from job_policy import expired, requires_graduate_degree


class CleanupTests(unittest.TestCase):
    def test_degree_filter(self):
        for value in ('석사', '석사 이상', '박사', '대학원졸(석사)', '석사·박사'):
            self.assertTrue(requires_graduate_degree(value))
        for value in ('대졸 이상', '학력무관', '석사 우대', '학사/석사', None):
            self.assertFalse(requires_graduate_degree(value))

    def test_date_boundaries(self):
        today = date(2026, 9, 16)
        self.assertTrue(expired('~ 09/15', '2026-09-01', today))
        for value in ('09/16', '09/17', '상시채용', '', '02/30'):
            self.assertFalse(expired(value, '2026-09-01', today))
        self.assertFalse(expired('12/31', '2026-01-01', today))
        self.assertFalse(expired('01/05', '2026-12-20', date(2026, 12, 25)))
        self.assertTrue(expired('01/05', '2026-12-20', date(2027, 1, 6)))

    def test_cleanup_backup_and_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'test.db'
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.execute('CREATE TABLE job_postings (id INTEGER PRIMARY KEY, deadline TEXT, created_at TEXT, notes TEXT)')
                conn.executemany('INSERT INTO job_postings VALUES (?, ?, ?, ?)', [
                    (1, '09/15', '2026-09-01', 'preserve in backup'),
                    (2, '09/16', '2026-09-01', 'today'),
                    (3, '상시채용', '2026-09-01', 'keep')])
            # 백업 생성 실패 시에도 기존 공고를 유지한다.
            with patch('database.cleanup.Path.mkdir', side_effect=OSError('backup failed')):
                with self.assertRaises(OSError):
                    delete_expired_jobs(path, date(2026, 9, 16))
            with closing(sqlite3.connect(path)) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM job_postings').fetchone()[0], 3)
            count, backup = delete_expired_jobs(path, date(2026, 9, 16))
            self.assertEqual(count, 1)
            with closing(sqlite3.connect(backup)) as conn:
                self.assertEqual(conn.execute('SELECT notes FROM job_postings WHERE id=1').fetchone()[0], 'preserve in backup')
            with closing(sqlite3.connect(path)) as conn:
                self.assertEqual(conn.execute('SELECT id FROM job_postings ORDER BY id').fetchall(), [(2,), (3,)])
            self.assertEqual(delete_expired_jobs(path, date(2026, 9, 16)), (0, None))
