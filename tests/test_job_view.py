from datetime import date
import unittest
from sqlalchemy import create_engine
from database.connection import initialize_database
from job_view import deadline_date, matches_deadline, region_priority, songdo_distance


class ViewTests(unittest.TestCase):
    def test_songdo_distance(self):
        self.assertEqual(songdo_distance('인천 연수구 송도'), 0)
        self.assertLess(songdo_distance('경기 시흥시'), songdo_distance('서울 강남구'))
        self.assertLess(songdo_distance('인천 연수구'), songdo_distance('인천 부평구'))
        self.assertIsNone(songdo_distance('서울 전체'))
        self.assertIsNone(songdo_distance('부산 중구'))
        self.assertAlmostEqual(songdo_distance('서울 강남구, 경기 시흥시'), songdo_distance('경기 시흥시'))
        self.assertAlmostEqual(songdo_distance('경기 성남시 분당구'), songdo_distance('경기 분당구'))

    def test_region_priority(self):
        for location, expected in [('인천 남동구', 0), ('서울특별시', 1),
                                   ('경기도 성남시', 2), ('서울, 인천', 0),
                                   ('부산 해운대구', None), ('전국', None),
                                   ('', None), (None, None), ('경기광주시', None)]:
            self.assertEqual(region_priority(location), expected)

    def test_experience_limit(self):
        from job_policy import accepts_up_to_two_years
        for value in ['신입', '경력무관', '신입·경력', '경력1년↑', '경력2년↑', '경력 1~2년', '경력2년↓']:
            self.assertTrue(accepts_up_to_two_years(value), value)
        for value in ['경력 2~5년', '경력 1~7년', '경력5년↓', '경력3년↑', '경력 3~8년', '경력 7~12년', '경력', '', None]:
            self.assertFalse(accepts_up_to_two_years(value), value)

    def test_status_migration_preserves_hidden_flag(self):
        engine = create_engine('sqlite://')
        with engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE job_postings (id INTEGER PRIMARY KEY, application_status TEXT)')
            for index, status in enumerate(['미정', '관심', '지원 예정', '미지원', '지원 완료', '합격', '불합격']):
                conn.exec_driver_sql('INSERT INTO job_postings VALUES (?, ?)', (index, status))
        initialize_database(engine)
        initialize_database(engine)
        with engine.connect() as conn:
            rows = [tuple(row) for row in conn.exec_driver_sql('SELECT application_status,status_updated FROM job_postings ORDER BY id')]
            self.assertEqual(rows, [('미지원', 0), ('지원 예정', 1), ('지원 예정', 1), ('미지원', 1), ('지원 완료', 1), ('지원 완료', 1), ('지원 완료', 1)])
        engine.dispose()

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
            self.assertEqual(tuple(conn.exec_driver_sql('SELECT notes, application_status, favorite FROM job_postings').one()), ('keep me', '미지원', 0))
        engine.dispose()
