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
                        title='Analyst [Python]', detail_url='https://example.com/123')

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

    def test_dashboard_null_metrics_literal_search_and_save(self):
        from streamlit.testing.v1 import AppTest
        from sqlalchemy import text
        connection.save_jobs_to_db([self.job])
        with self.engine.begin() as conn:
            conn.execute(text('UPDATE job_postings SET notes = NULL, preference = NULL'))
        with patch.object(connection, 'engine', self.engine):
            app = AppTest.from_file(str(connection.DB_PATH.parent / 'app.py'), default_timeout=20).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.metric[1].value, '0개')
            app.sidebar.text_input[0].set_value('[').run()
            self.assertEqual(len(app.exception), 0)
            app.text_area[1].set_value('Applied')
            app.selectbox(key='status_1').select('지원 완료')
            app.checkbox(key='favorite_1').check()
            app.button[0].click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.metric[2].value, '1개')
            self.assertEqual(app.metric[3].value, '1개')
            app.sidebar.checkbox[0].check().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.text_area), 2)
            app.sidebar.multiselect[0].set_value(['합격']).run()
            self.assertEqual(len(app.text_area), 0)
        with self.sessions() as session:
            row = session.scalar(select(JobPosting))
            self.assertEqual(row.notes, 'Applied')
            self.assertEqual(row.application_status, '지원 완료')
            self.assertTrue(row.favorite)


if __name__ == '__main__':
    unittest.main()
