import unittest
from types import SimpleNamespace
from unittest.mock import patch
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from crawler.jobkorea import JobkoreaCrawler
from database import connection
from database.models import Base, JobPosting


class JobkoreaTests(unittest.TestCase):
    def test_list_and_conditions(self):
        html = '''<li><a class="name">테스트㈜</a><a class="title" href="/Recruit/GI_Read/123">분석가</a><span class="exp">신입</span><span class="edu">대졸↑</span><span class="loc">서울 강남구</span><span class="date">~12/31</span></li>'''
        job = JobkoreaCrawler(0)._parse_search_item(BeautifulSoup(html, 'html.parser').li)
        self.assertEqual(job['job_id'], 'jobkorea_123')
        self.assertEqual(job['experience'], '신입')
        self.assertEqual(job['location_summary'], '서울 강남구')

    def test_blocked_page_is_reported(self):
        response = SimpleNamespace(content='<title>보안정책</title>'.encode(), raise_for_status=lambda: None)
        with patch('crawler.jobkorea.requests.get', return_value=response), patch('builtins.print') as output:
            self.assertEqual(JobkoreaCrawler(0).search('분석'), [])
            self.assertIn('접속 제한', str(output.call_args_list))

    def test_cross_platform_database_duplicates_preserve_notes(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        job = dict(platform='saramin', job_id='saramin_1', company_name='주식회사 테스트', title='데이터 분석가', location_summary='서울 강남구', detail_url='https://example.com')
        other = dict(job, platform='jobkorea', job_id='jobkorea_1', company_name='테스트㈜', title='데이터분석가')
        with patch.object(connection, 'SessionLocal', sessions):
            self.assertEqual(connection.save_jobs_to_db([job, other]), 1)
            with sessions.begin() as session:
                session.scalar(select(JobPosting)).notes = '보존'
            self.assertEqual(connection.save_jobs_to_db([other]), 0)
            self.assertEqual(connection.save_jobs_to_db([dict(other, job_id='jobkorea_2', title='데이터 엔지니어')]), 1)
            self.assertEqual(connection.save_jobs_to_db([dict(other, job_id='jobkorea_3', location_summary='경기 수원시')]), 1)
            with sessions() as session:
                self.assertEqual(session.scalar(select(JobPosting).where(JobPosting.job_id == 'saramin_1')).notes, '보존')
        engine.dispose()
