# main.py
from datetime import datetime
from zoneinfo import ZoneInfo

from crawler.jobkorea import JobkoreaCrawler
from crawler.saramin import SaraminCrawler
from database.cleanup import delete_expired_jobs
from database.connection import DB_PATH, save_jobs_to_db
from job_identity import duplicate_key
from job_policy import accepts_up_to_two_years, expired, requires_graduate_degree
from job_view import region_priority, songdo_distance


def run_pipeline(keyword: str, pages: int = 1):
    print("=" * 50)
    print(f"🚀 [AI-Job-Tracker] '{keyword}' 공고 목록 수집 가동")
    print("=" * 50)

    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    removed, backup = delete_expired_jobs(DB_PATH, today)
    print(f"마감일이 지난 기존 공고 {removed}개 삭제")
    if backup:
        print(f"삭제 전 백업: {backup}")

    crawlers = {
        crawler.platform_name: crawler
        for crawler in (SaraminCrawler(delay=1.0), JobkoreaCrawler(delay=1.0))
    }
    # 목록에서 제외 조건을 먼저 적용한 뒤 필요한 상세 페이지만 요청한다.
    jobs = []
    for crawler in crawlers.values():
        jobs.extend(crawler.run(keyword=keyword, pages=pages, fetch_detail=False))
    seen = {}
    unique_jobs = []
    for job in jobs:
        key = duplicate_key(job)
        if key and key in seen and seen[key] != job["platform"]:
            continue
        if key:
            seen[key] = job["platform"]
        unique_jobs.append(job)
    print(f"플랫폼 간 중복 공고 {len(jobs) - len(unique_jobs)}개 제외")
    jobs = unique_jobs
    collected_count = len(jobs)
    jobs = [
        job
        for job in jobs
        if region_priority(job.get("location_summary")) is not None
        and accepts_up_to_two_years(job.get("experience"))
        and not requires_graduate_degree(job.get("education"))
        and not expired(job.get("deadline"), today.isoformat(), today)
    ]
    print(
        f"수도권 외·근무지 미정, 경력 조건 불일치, 석사·박사 필수 또는 마감일이 지난 공고 {collected_count - len(jobs)}개 제외"
    )

    jobs.sort(
        key=lambda job: (
            songdo_distance(job.get("location_summary"))
            if songdo_distance(job.get("location_summary")) is not None
            else float("inf")
        )
    )

    if jobs:
        for index, job in enumerate(jobs, 1):
            print(f"상세 수집 {index}/{len(jobs)}: {job['title']}")
            job.update(crawlers[job["platform"]].parse_detail(job["detail_url"]))
        saved_count = save_jobs_to_db(jobs)
        print(f"\n💾 DB 저장 완료: {saved_count}개 신규 저장, 기존 공고 상세 정보 갱신")
    else:
        print("\n⚠️ 수집된 공고가 없습니다.")


if __name__ == "__main__":
    run_pipeline(keyword="데이터분석", pages=1)
