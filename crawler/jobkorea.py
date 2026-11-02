"""잡코리아 공개 검색 목록과 상세 본문 수집."""
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .base import BaseCrawler
from .sections import FIELDS, body_text, extract_sections


class JobkoreaCrawler(BaseCrawler):
    DOMAIN = 'https://www.jobkorea.co.kr'
    BASE_URL = DOMAIN + '/Search/'

    def __init__(self, delay=1.5):
        super().__init__('jobkorea', delay)

    def _get_soup(self, url, **kwargs):
        response = requests.get(url, headers=self.headers, timeout=20, **kwargs)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        text = soup.get_text(' ', strip=True)
        if '보안정책' in str(soup.title) or '접속이 일시적으로 제한' in text:
            raise RuntimeError('잡코리아 보안 정책으로 접속 제한됨')
        return soup

    def _parse_search_item(self, item):
        title = item.select_one('a.title, .post-list-info a[href*="GI_Read"], a[href*="GI_Read"]')
        company = item.select_one('.name, .corp-name, .corpName')
        if not title or not company:
            return None
        url = urljoin(self.DOMAIN, title.get('href', ''))
        match = re.search(r'/GI_Read/(\d+)', url, re.I)
        if not match or urlparse(url).hostname != 'www.jobkorea.co.kr':
            return None
        def text(selector):
            node = item.select_one(selector)
            return node.get_text(' ', strip=True) if node else ''
        result = dict(platform='jobkorea', job_id='jobkorea_' + match[1],
                      company_name=company.get_text(' ', strip=True),
                      title=title.get_text(' ', strip=True), detail_url=url,
                      experience=text('.exp'), education=text('.edu'),
                      location_summary=text('.loc, .location'), deadline=text('.date, .deadline'))
        return result if result['company_name'] and result['title'] else None

    def search(self, keyword, pages=1):
        jobs, seen = [], set()
        for page in range(1, pages + 1):
            try:
                soup = self._get_soup(self.BASE_URL, params={'stext': keyword, 'Page_No': page})
                items = soup.select('.list-post > li, .post-list > li, .recruit-info .list-item')
                parsed = [job for item in items if (job := self._parse_search_item(item))]
                if not parsed:
                    if not any(value in soup.get_text() for value in ('검색 결과가 없습니다', '검색결과가 없습니다', '검색된 채용정보가 없습니다')):
                        raise RuntimeError('잡코리아 목록 구조 확인 필요 (수집 실패)')
                    break
                for job in parsed:
                    if job['job_id'] not in seen:
                        seen.add(job['job_id'])
                        jobs.append(job)
            except (requests.RequestException, RuntimeError) as exc:
                print(f'[WARN] 잡코리아 {page}페이지 수집 실패: {exc}')
                break
            finally:
                time.sleep(self.delay)
        return jobs

    def parse_detail(self, detail_url):
        result = {field: '' for field in FIELDS}
        try:
            soup = self._get_soup(detail_url)
            content = soup.select_one('#gib_frame, .gib_frame, .recruit-detail')
            if content and content.name == 'iframe' and content.get('src'):
                url = urljoin(detail_url, content['src'])
                if urlparse(url).scheme not in ('http', 'https') or not (urlparse(url).hostname or '').endswith('.jobkorea.co.kr'):
                    raise RuntimeError('본문 주소 확인 필요')
                time.sleep(self.delay)
                frame = self._get_soup(url)
                content = frame.body or frame
            if content is None:
                raise RuntimeError('본문 영역 없음 · 원문 확인 필요')
            body = body_text(content)
            if len(body) < 20:
                raise RuntimeError('이미지 또는 본문 부족 · 원문 확인 필요')
            result.update(description=body, detail_status='텍스트 수집 완료')
            result.update(extract_sections(body))
            if content.select('img'):
                result['detail_status'] += ' · 이미지 내용은 원문 확인'
        except (requests.RequestException, RuntimeError) as exc:
            result['detail_status'] = f'상세 수집 실패: {exc}'
        finally:
            time.sleep(self.delay)
        return result
