# main.py
from crawler.saramin import SaraminCrawler
from datetime import datetime
from zoneinfo import ZoneInfo
from database.connection import save_jobs_to_db, DB_PATH
from database.cleanup import delete_expired_jobs
from job_policy import expired, requires_graduate_degree

def run_pipeline(keyword: str, pages: int = 1):
    print("=" * 50)
    print(f"🚀 [AI-Job-Tracker] '{keyword}' 공고 목록 수집 가동")
    print("=" * 50)

    today = datetime.now(ZoneInfo('Asia/Seoul')).date()
    removed, backup = delete_expired_jobs(DB_PATH, today)
    print(f"마감일이 지난 기존 공고 {removed}개 삭제")
    if backup:
        print(f"삭제 전 백업: {backup}")

    crawler = SaraminCrawler(delay=1.0)
    # 목록에서 제외 조건을 먼저 적용한 뒤 필요한 상세 페이지만 요청한다.
    jobs = crawler.run(keyword=keyword, pages=pages, fetch_detail=False)
    collected_count = len(jobs)
    jobs = [job for job in jobs
            if not requires_graduate_degree(job.get('education'))
            and not expired(job.get('deadline'), today.isoformat(), today)]
    print(f"석사·박사 필수 또는 마감일이 지난 공고 {collected_count - len(jobs)}개 제외")

    if jobs:
        for index, job in enumerate(jobs, 1):
            print(f"상세 수집 {index}/{len(jobs)}: {job['title']}")
            job.update(crawler.parse_detail(job['detail_url']))
        saved_count = save_jobs_to_db(jobs)
        print(f"\n💾 DB 저장 완료: {saved_count}개 신규 저장, 기존 공고 상세 정보 갱신")
    else:
        print("\n⚠️ 수집된 공고가 없습니다.")

if __name__ == "__main__":
    run_pipeline(keyword="데이터분석", pages=1)
