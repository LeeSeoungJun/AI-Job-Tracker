import unittest
from unittest.mock import patch
from types import SimpleNamespace
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from crawler.saramin import SaraminCrawler
from database import connection
from database.models import Base, JobPosting


def response(html, status=200):
    return SimpleNamespace(text=html, content=html.encode('utf-8'), status_code=status, url='https://www.saramin.co.kr/jobs/view')


class DetailTests(unittest.TestCase):
    def test_dynamic_page_and_emoji_headings(self):
        shell = response("<script>var url='/zf_user/jobs/relay/view-ajax';</script>")
        ajax = response('<iframe id="iframe_content_0" src="/body"></iframe>')
        body = response('<meta charset="utf-8"><body>📋 우대사항<p>SQL을 활용한 데이터 분석 경험</p>🏠 근무조건<p>서울 근무</p></body>')
        with patch('crawler.saramin.requests.get', side_effect=[shell, body]), patch('crawler.saramin.requests.post', return_value=ajax) as post:
            result = SaraminCrawler(delay=0).parse_detail('https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=123')
        self.assertEqual(result['auto_preference'], 'SQL을 활용한 데이터 분석 경험')
        self.assertEqual(post.call_args.kwargs['data']['rec_idx'], '123')

    def test_iframe_sections_and_boundaries(self):
        body = '<meta charset="utf-8"><body><h3>주요 업무</h3><p>데이터 분석 및 보고서 작성</p><h3>자격요건</h3><p>Python 사용 가능</p><h3>우대사항</h3><p>SQL 경험</p><h3>복리후생</h3><p>식대 지원</p></body>'
        with patch('crawler.saramin.requests.get', side_effect=[response('<div class="wrap_jv_cont">다른 페이지 안내문</div><iframe id="iframe_content_0" src="/body"></iframe>'), response(body)]):
            result = SaraminCrawler(delay=0).parse_detail('https://www.saramin.co.kr/jobs/view')
        self.assertEqual(result['auto_preference'], 'SQL 경험')
        self.assertEqual(result['qualifications'], 'Python 사용 가능')
        self.assertIn('데이터 분석', result['responsibilities'])
        self.assertIn('식대 지원', result['description'])

    def test_image_and_failed_requests_are_not_success(self):
        for content, status, expected in [('<div class="user_content"><img src="job.png"></div>', 200, '이미지 공고'), ('', 403, '요청 실패')]:
            with patch('crawler.saramin.requests.get', return_value=response(content, status)):
                result = SaraminCrawler(delay=0).parse_detail('https://example.com')
            self.assertIn(expected, result['detail_status'])
            self.assertEqual(result['description'], '')

    def test_refresh_keeps_user_notes_and_previous_body_on_failure(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        job = dict(job_id='test', company_name='Company', title='Job', detail_url='https://example.com', description='Old body', auto_preference='Old preference', detail_status='텍스트 수집 완료')
        with patch.object(connection, 'SessionLocal', sessions):
            connection.save_jobs_to_db([job])
            with sessions.begin() as session:
                row = session.scalar(select(JobPosting))
                row.notes = 'My note'
                row.preference = 'My preference'
                row.favorite = True
            connection.save_jobs_to_db([dict(job, description='New body', auto_preference='New preference')])
            connection.save_jobs_to_db([dict(job, description='', auto_preference='', detail_status='요청 실패')])
            with sessions() as session:
                row = session.scalar(select(JobPosting))
                self.assertEqual(row.description, 'New body')
                self.assertEqual(row.auto_preference, 'New preference')
                self.assertEqual(row.notes, 'My note')
                self.assertEqual(row.preference, 'My preference')
                self.assertTrue(row.favorite)
                self.assertEqual(row.detail_status, '요청 실패')
        engine.dispose()
