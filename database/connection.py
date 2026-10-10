"""
database/connection.py
"""

from pathlib import Path
from sqlalchemy import create_engine, URL, text
from sqlalchemy.orm import sessionmaker
from database.models import Base, JobPosting
from crawler.sections import FIELDS

DB_PATH = Path(__file__).resolve().parents[1] / "jobs_data.db"
DB_URL = URL.create("sqlite", database=str(DB_PATH))
engine = create_engine(DB_URL, echo=False)

def initialize_database(target_engine):
    """기존 행을 유지하며 필요한 열만 추가한다."""
    Base.metadata.create_all(target_engine)
    with target_engine.begin() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(job_postings)")}
        if "application_status" not in columns:
            conn.execute(text("ALTER TABLE job_postings ADD COLUMN application_status VARCHAR(30) NOT NULL DEFAULT '미정'"))
        if "favorite" not in columns:
            conn.execute(text("ALTER TABLE job_postings ADD COLUMN favorite BOOLEAN NOT NULL DEFAULT 0"))
        for column in FIELDS:
            if column not in columns:
                default = '미수집' if column == 'detail_status' else ''
                conn.exec_driver_sql(f"ALTER TABLE job_postings ADD COLUMN {column} TEXT DEFAULT '{default}'")


initialize_database(engine)
SessionLocal = sessionmaker(bind=engine)


def save_jobs_to_db(jobs_list: list) -> int:
    session = SessionLocal()
    saved_count = 0
    seen = set()

    try:
        for job in jobs_list:
            required = ("job_id", "company_name", "title", "detail_url")
            if not isinstance(job, dict) or any(
                not isinstance(job.get(key), str) or not job[key].strip()
                for key in required
            ):
                print("[WARN] 필수 정보가 없는 공고를 건너뜁니다.")
                continue
            job_id = job["job_id"].strip()
            if job_id in seen:
                continue
            seen.add(job_id)
            existing = session.query(JobPosting).filter_by(job_id=job_id).first()
            if existing:
                # 실패한 재수집으로 이전 본문을 지우지 않는다. 수기 필드는 건드리지 않는다.
                if job.get('description'):
                    for field in FIELDS:
                        setattr(existing, field, job.get(field, ''))
                elif job.get('detail_status'):
                    existing.detail_status = job['detail_status']
                continue

            job_posting = JobPosting(
                platform=job.get("platform") or "saramin",
                job_id=job_id,
                company_name=job.get("company_name", ""),
                title=job.get("title", ""),
                experience=job.get("experience", ""),
                education=job.get("education", ""),
                location_summary=job.get("location_summary", ""),
                deadline=job.get("deadline", ""),
                detail_url=job.get("detail_url", ""),
                preference="", # 수기 작성용 빈 칸
                notes="",
                **{field: job.get(field, '미수집' if field == 'detail_status' else '') for field in FIELDS}
            )

            session.add(job_posting)
            saved_count += 1

        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[ERROR] DB 저장 실패: {e}")
        raise
    finally:
        session.close()

    return saved_count
