import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from crawler.saramin import SaraminCrawler
from database import connection
from database.models import Base, JobPosting


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool,
                                    connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.patch = patch.object(connection, 'SessionLocal', self.sessions)
        self.patch.start()
        self.job = dict(job_id='saramin_123', company_name='Company',
                        title='Analyst [Python]', experience='경력무관', location_summary='서울 강남구', detail_url='https://example.com/123')

    def tearDown(self):
        self.patch.stop()
        self.engine.dispose()

    def test_duplicates_invalid_records_and_notes(self):
        self.assertEqual(connection.save_jobs_to_db(
            [self.job, self.job.copy(), {}, dict(self.job, job_id=' '), None]), 1)
        with self.sessions.begin() as session:
            row = session.scalar(select(JobPosting))
            row.notes = 'Keep this note'
        self.assertEqual(connection.save_jobs_to_db([self.job]), 0)
        with self.sessions() as session:
            self.assertEqual(session.scalar(select(JobPosting)).notes, 'Keep this note')

    def test_commit_failure_is_reported_and_rolled_back(self):
        session = self.sessions()
        with patch.object(connection, 'SessionLocal', return_value=session), \
             patch.object(session, 'commit', side_effect=RuntimeError('disk full')):
            with self.assertRaises(RuntimeError):
                connection.save_jobs_to_db([self.job])
        with self.sessions() as session:
            self.assertEqual(list(session.scalars(select(JobPosting))), [])

    def test_id_fallback_and_incomplete_html(self):
        crawler = SaraminCrawler(delay=0)
        html = '<div><div class="corp_name"><a>Company</a></div><div class="job_tit"><a href="/jobs?rec_idx=123&amp;tracking=x">Analyst</a></div></div>'
        parsed = crawler._parse_search_item(BeautifulSoup(html, 'html.parser').div)
        self.assertEqual(parsed['job_id'], 'saramin_123')
        self.assertEqual(parsed['detail_url'], 'https://www.saramin.co.kr/jobs?rec_idx=123&tracking=x')
        self.assertIsNone(crawler._parse_search_item(BeautifulSoup('<div/>', 'html.parser').div))

    def test_detail_failure_does_not_stop_next_job(self):
        crawler = SaraminCrawler(delay=0)
        jobs = [self.job.copy(), dict(self.job, job_id='saramin_456')]
        with patch.object(crawler, 'search', return_value=jobs), \
             patch.object(crawler, 'parse_detail', side_effect=[RuntimeError('timeout'), {'description': 'OK'}]):
            result = crawler.run('analyst', fetch_detail=True)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]['description'], 'OK')

    def test_mixed_rating_dates_render_all_cards_and_pages(self):
        from streamlit.testing.v1 import AppTest
        from datetime import datetime
        from zoneinfo import ZoneInfo
        connection.save_jobs_to_db([dict(self.job, job_id=f'job_{i}') for i in range(14)])
        with self.sessions.begin() as session:
            rows = list(session.scalars(select(JobPosting).order_by(JobPosting.id)))
            rows[0].jobplanet_checked_on = '2026-10-12'
            rows[0].jobplanet_rating = 3.2
            rows[1].jobplanet_checked_on = 'invalid date'
            rows[2].jobplanet_checked_on = '2099-01-01'
        with patch.object(connection, 'engine', self.engine):
            app = AppTest.from_file(str(connection.DB_PATH.parent / 'app.py'), default_timeout=20).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.text_area), 12)
            app.selectbox(key='page').select(2).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.text_area), 2)

    def test_notes_save_refresh_and_clear_preserves_status_and_rating(self):
        from streamlit.testing.v1 import AppTest
        connection.save_jobs_to_db([self.job])
        with self.sessions.begin() as session:
            row = session.scalar(select(JobPosting))
            row.jobplanet_rating = 3.7
            row.jobplanet_review_count = 42
        with patch.object(connection, 'engine', self.engine):
            app = AppTest.from_file(str(connection.DB_PATH.parent / 'app.py'), default_timeout=20).run()
            self.assertEqual(len(app.number_input), 0)
            self.assertFalse(any(x.label == '잡플래닛 평점 입력' for x in app.expander))
            app.text_area(key='notes_text_1').set_value('면접 일정 확인')
            app.button(key='FormSubmitter:notes_1-메모 저장').click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.text_area), 1)
            connection.save_jobs_to_db([dict(self.job, description='Updated')])
            with self.sessions() as session:
                row = session.scalar(select(JobPosting))
                self.assertEqual(row.notes, '면접 일정 확인')
                self.assertEqual(row.jobplanet_rating, 3.7)
                self.assertEqual(row.jobplanet_review_count, 42)
                self.assertFalse(row.status_updated)
            app.text_area(key='notes_text_1').set_value('')
            app.button(key='FormSubmitter:notes_1-메모 저장').click().run()
            self.assertEqual(len(app.exception), 0)
        with self.sessions() as session:
            self.assertEqual(session.scalar(select(JobPosting)).notes, '')

    def test_not_applying_hides_job_and_preserves_record(self):
        from streamlit.testing.v1 import AppTest
        connection.save_jobs_to_db([self.job, dict(self.job, job_id='second_job')])
        with self.sessions.begin() as session:
            session.scalar(select(JobPosting).where(JobPosting.job_id == self.job['job_id'])).notes = 'Keep hidden note'
        with patch.object(connection, 'engine', self.engine):
            app = AppTest.from_file(str(connection.DB_PATH.parent / 'app.py'), default_timeout=20).run()
            app.button(key='status_1_미지원').click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.metric[0].value, '2개')
            self.assertEqual(len(app.text_area), 1)
            self.assertFalse(any(widget.key == 'status_1_미지원' for widget in app.button))
            connection.save_jobs_to_db([dict(self.job, description='New body')])
            app.run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.text_area), 1)
        with self.sessions() as session:
            row = session.scalar(select(JobPosting).where(JobPosting.job_id == self.job['job_id']))
            self.assertEqual(row.application_status, '미지원')
            self.assertEqual(row.notes, 'Keep hidden note')

    def test_every_updated_status_hidden_by_default_and_recoverable(self):
        from streamlit.testing.v1 import AppTest
        from job_view import STATUSES
        connection.save_jobs_to_db([dict(self.job, job_id=f'status_{i}') for i in range(len(STATUSES))])
        with self.sessions.begin() as session:
            for row, status in zip(session.scalars(select(JobPosting).order_by(JobPosting.id)), STATUSES):
                row.application_status = status
                row.status_updated = status != '미지원'
        with patch.object(connection, 'engine', self.engine):
            app = AppTest.from_file(str(connection.DB_PATH.parent / 'app.py'), default_timeout=20).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.text_area), 1)
            app.checkbox(key='show_updated').check().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.text_area), len(STATUSES))
            app.button(key='status_2_미지원').click().run()
            app.checkbox(key='show_updated').uncheck().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.text_area), 1)

    def test_status_filter_includes_hidden_jobs_without_extra_checkbox(self):
        from streamlit.testing.v1 import AppTest
        from job_view import STATUSES
        connection.save_jobs_to_db([dict(self.job, job_id=f'filtered_{i}') for i in range(3)])
        with self.sessions.begin() as session:
            for row, status in zip(session.scalars(select(JobPosting).order_by(JobPosting.id)), STATUSES):
                row.application_status = status
                row.status_updated = True
        with patch.object(connection, 'engine', self.engine):
            app = AppTest.from_file(str(connection.DB_PATH.parent / 'app.py'), default_timeout=20).run()
            self.assertEqual(len(app.text_area), 0)
            for status in STATUSES:
                app.sidebar.multiselect[0].set_value([status]).run()
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(len(app.text_area), 1)
                self.assertFalse(app.checkbox(key='show_updated').value)
            app.sidebar.multiselect[0].set_value(['지원 예정', '지원 완료']).run()
            self.assertEqual(len(app.text_area), 2)
            app.sidebar.multiselect[0].set_value([]).run()
            self.assertEqual(len(app.text_area), 0)

    def test_dashboard_literal_search_and_one_click_status(self):
        from streamlit.testing.v1 import AppTest
        from sqlalchemy import text
        connection.save_jobs_to_db([self.job])
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE job_postings SET notes = 'Keep me', preference = NULL, favorite = 1"))
        with patch.object(connection, 'engine', self.engine):
            app = AppTest.from_file(str(connection.DB_PATH.parent / 'app.py'), default_timeout=20).run()
            self.assertEqual(len(app.exception), 0)
            app.sidebar.text_input[0].set_value('[').run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.text_area), 1)
            self.assertEqual(app.button(key='status_1_지원 완료').label, '지원완료')
            app.button(key='status_1_지원 완료').click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.metric[3].value, '1개')
            self.assertEqual(len(app.text_area), 0)
            app.checkbox(key='show_updated').check().run()
            self.assertEqual(len(app.exception), 0)
            app.button(key='status_1_지원 예정').click().run()
            self.assertEqual(app.metric[1].value, '1개')
            app.sidebar.multiselect[0].set_value(['지원 완료']).run()
            self.assertEqual(len(app.text_area), 0)
        with self.sessions() as session:
            row = session.scalar(select(JobPosting))
            self.assertEqual(row.notes, 'Keep me')
            self.assertEqual(row.application_status, '지원 예정')
            self.assertTrue(row.favorite)


if __name__ == '__main__':
    unittest.main()
