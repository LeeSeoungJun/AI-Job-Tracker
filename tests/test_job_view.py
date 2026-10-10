from datetime import date
import unittest
from sqlalchemy import create_engine
from database.connection import initialize_database
from job_view import deadline_date, matches_deadline


class ViewTests(unittest.TestCase):
    def test_dates_and_filters(self):
        self.assertEqual(deadline_date('~ 01/05(월)', '2026-12-20 12:00:00'), date(2027, 1, 5))
        self.assertEqual(deadline_date('2026-09-20', '2026-09-01'), date(2026, 9, 20))
        self.assertIsNone(deadline_date('상시채용', '2026-09-01'))
        self.assertIsNone(deadline_date('02/30', '2026-09-01'))
        today = date(2026, 9, 16)
        self.assertTrue(matches_deadline('', date(2026, 9, 23), today, '7일 이내'))
        self.assertFalse(matches_deadline('', date(2026, 9, 24), today, '7일 이내'))
        self.assertFalse(matches_deadline('', date(2026, 9, 15), today, '전체', True))
        self.assertTrue(matches_deadline('상시채용', None, today, '상시·날짜 미정'))

    def test_old_database_migration_preserves_data_and_is_repeatable(self):
        engine = create_engine('sqlite://')
        with engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE job_postings (id INTEGER PRIMARY KEY, notes TEXT)')
            conn.exec_driver_sql("INSERT INTO job_postings VALUES (1, 'keep me')")
        initialize_database(engine)
        initialize_database(engine)
        with engine.connect() as conn:
            self.assertEqual(tuple(conn.exec_driver_sql('SELECT notes, application_status, favorite FROM job_postings').one()), ('keep me', '미정', 0))
        engine.dispose()
