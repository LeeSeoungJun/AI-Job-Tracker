"""
crawler/saramin.py
- 사람인 목록 및 상세 페이지(iframe 본문 포함) 파싱 크롤러
"""

import time
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

from .base import BaseCrawler


class SaraminCrawler(BaseCrawler):
    BASE_URL = "https://www.saramin.co.kr/zf_user/search"
    DOMAIN = "https://www.saramin.co.kr"

    def __init__(self, delay: float = 1.5):
        super().__init__(platform_name="saramin", delay=delay)

    def search(self, keyword: str, pages: int = 1) -> List[Dict[str, Any]]:
        job_list = []
        seen = set()

        for page in range(1, pages + 1):
            params = {
                "searchword": keyword,
                "recruitPage": page,
                "recruitSort": "relation",
                "recruitPageCount": "40",
            }

            try:
                res = requests.get(self.BASE_URL, headers=self.headers, params=params, timeout=10)
                if res.status_code != 200:
                    print(f"[ERROR] 검색 페이지 요청 실패 (상태 코드: {res.status_code})")
                    break

                soup = BeautifulSoup(res.text, "html.parser")
                items = soup.select(".item_recruit")

                for item in items:
                    parsed_item = self._parse_search_item(item)
                    if parsed_item and parsed_item['job_id'] not in seen:
                        seen.add(parsed_item['job_id'])
                        job_list.append(parsed_item)

            except Exception as e:
                print(f"[ERROR] {page}페이지 수집 실패: {e}")

            time.sleep(self.delay)

        return job_list

    def _parse_search_item(self, item) -> Optional[Dict[str, Any]]:
        try:
            job_id = item.get("value", "")
            corp_elem = item.select_one(".corp_name a")
            company_name = corp_elem.text.strip() if corp_elem else ""

            title_elem = item.select_one(".job_tit a")
            title = title_elem.text.strip() if title_elem else ""
            href = title_elem.get("href", "") if title_elem else ""
            if not href or not company_name or not title:
                return None
            detail_url = urljoin(self.BASE_URL, href)
            if urlparse(detail_url).scheme not in ("http", "https"):
                return None
            job_id = str(job_id or "").strip()
            if not job_id:
                job_id = parse_qs(urlparse(detail_url).query).get("rec_idx", [""])[0]
            if not job_id:
                return None

            conditions = [c.text.strip() for c in item.select(".job_condition span")]
            location = conditions[0] if len(conditions) > 0 else ""
            experience = conditions[1] if len(conditions) > 1 else ""
            education = conditions[2] if len(conditions) > 2 else ""

            date_elem = item.select_one(".job_date .date")
            deadline = date_elem.text.strip() if date_elem else ""

            return {
                "platform": self.platform_name,
                "job_id": f"saramin_{job_id}",
                "company_name": company_name,
                "title": title,
                "experience": experience,
                "education": education,
                "location_summary": location,
                "deadline": deadline,
                "detail_url": detail_url,
            }
        except Exception:
            return None

    def parse_detail(self, detail_url: str) -> Dict[str, Any]:
        """상세 본문과 iframe을 읽고 제목별 원문을 분리한다."""
        from .sections import extract_sections, body_text
        result = dict(description='', responsibilities='', qualifications='',
                      auto_preference='', detail_status='본문 확인 불가')
        try:
            res = requests.get(detail_url, headers=self.headers, timeout=10)
            if res.status_code != 200:
                result['detail_status'] = f'요청 실패 (HTTP {res.status_code})'
                return result
            soup = BeautifulSoup(res.content, 'html.parser')
            if not soup.select_one('.user_content, iframe#iframe_content_0, iframe[src*="relay"]'):
                rec_idx = parse_qs(urlparse(detail_url).query).get('rec_idx', [''])[0]
                if rec_idx and '/zf_user/jobs/relay/view-ajax' in res.text:
                    time.sleep(self.delay)
                    ajax = requests.post(
                        urljoin(self.DOMAIN, '/zf_user/jobs/relay/view-ajax'),
                        data={'rec_idx': rec_idx, 'rec_seq': 0},
                        headers={**self.headers, 'Referer': detail_url, 'X-Requested-With': 'XMLHttpRequest'},
                        timeout=10)
                    if ajax.status_code != 200:
                        result['detail_status'] = f'상세 요청 실패 (HTTP {ajax.status_code})'
                        return result
                    soup = BeautifulSoup(ajax.content, 'html.parser')
            content = soup.select_one('.user_content')
            iframe = soup.select_one('iframe#iframe_content_0') or soup.select_one("iframe[src*='relay']")
            # 페이지 전체 레이아웃을 본문으로 오인하지 않고 상세 iframe을 우선 확인한다.
            if iframe and iframe.get('src') and (content is None or not content.get_text(strip=True)):
                iframe_url = urljoin(res.url or detail_url, iframe['src'])
                if urlparse(iframe_url).scheme not in ('http', 'https'):
                    return result
                time.sleep(self.delay)
                response = requests.get(iframe_url, headers={**self.headers, 'Referer': detail_url}, timeout=10)
                if response.status_code != 200:
                    result['detail_status'] = f'본문 요청 실패 (HTTP {response.status_code})'
                    return result
                frame = BeautifulSoup(response.content, 'html.parser')
                content = frame.select_one('.user_content') or frame.body or frame
            if content is None:
                result['detail_status'] = '본문 영역 없음 · 원문 확인 필요'
                return result
            has_images = bool(content.select('img'))
            body = body_text(content)
            if len(body) < 20:
                result['detail_status'] = '이미지 공고 · 원문 확인 필요' if has_images else '본문 부족 · 원문 확인 필요'
                return result
            result['description'] = body
            result.update(extract_sections(body))
            result['detail_status'] = '텍스트 수집 완료'
            if has_images:
                result['detail_status'] += ' · 이미지 내용은 원문 확인'
            if not any(result[key] for key in ('responsibilities', 'qualifications', 'auto_preference')):
                result['detail_status'] += ' · 항목 구분 불가'
        except Exception as exc:
            result['detail_status'] = '요청 또는 본문 처리 실패 · 재수집 필요'
            print(f"[ERROR] 상세 수집 실패: {exc}")
        finally:
            time.sleep(self.delay)
        return result
