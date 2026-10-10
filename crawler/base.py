from abc import ABC, abstractmethod
from typing import Dict, List, Any


class BaseCrawler(ABC):
    def __init__(self, platform_name: str, delay: float = 1.0):
        """
        :param platform_name: 플랫폼 이름 (e.g., 'saramin', 'wanted', 'jobkorea')
        :param delay: 서버 부하 방지 및 IP 차단 회피를 위한 요청 간 대기 시간 (초)
        """
        self.platform_name = platform_name
        self.delay = delay
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

    @abstractmethod
    def search(self, keyword: str, pages: int = 1) -> List[Dict[str, Any]]:
        """
        검색어 기반으로 채용공고 목록을 수집합니다.
        
        :param keyword: 검색할 직무/기술 키워드 (예: '파이썬', '데이터 엔지니어')
        :param pages: 수집할 페이지 수
        :return: 채용공고 기본 정보 리스트 [Dict, Dict, ...]
        """
        pass

    @abstractmethod
    def parse_detail(self, detail_url: str) -> Dict[str, Any]:
        """
        공고 상세 페이지 URL에 접속하여 상세 정보(JD, 주요업무, 자격요건 등)를 파싱합니다.
        
        :param detail_url: 공고 상세페이지 URL
        :return: 상세 정보 Dict
        """
        pass

    def run(self, keyword: str, pages: int = 1, fetch_detail: bool = False) -> List[Dict[str, Any]]:
        """
        크롤링 전체 프로세스 실행 메서드
        
        :param keyword: 검색어
        :param pages: 페이지 수
        :param fetch_detail: 상세 페이지 내용까지 수집할지 여부
        """
        print(f"[{self.platform_name.upper()}] '{keyword}' 키워드로 수집을 시작합니다. (페이지: {pages})")
        results = self.search(keyword, pages=pages)

        if fetch_detail:
            print(f"[{self.platform_name.upper()}] 상세 페이지 수집 시작 ({len(results)}개 항목)...")
            for item in results:
                if item.get("detail_url"):
                    try:
                        detail_info = self.parse_detail(item["detail_url"])
                        item.update(detail_info)
                    except Exception as e:
                        print(f"[ERROR] 상세 수집 실패 ({item['detail_url']}): {e}")

        print(f"[{self.platform_name.upper()}] 수집 완료! 총 {len(results)}건")
        return results
