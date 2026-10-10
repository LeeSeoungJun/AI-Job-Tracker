"""
database/models.py
- 불필요한 빈 컬럼들을 정리한 간소화 DB 모델
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class JobPosting(Base):
    __tablename__ = 'job_postings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(20), nullable=False)           # saramin
    job_id = Column(String(100), unique=True, nullable=False) # 고유 ID
    company_name = Column(String(100), nullable=False)       # 기업명
    title = Column(String(200), nullable=False)              # 공고 제목
    
    # 공고 핵심 조건
    experience = Column(String(50))            # 경력 (e.g., 신입·경력)
    education = Column(String(100))            # 학력 (e.g., 대졸 이상)
    location_summary = Column(String(100))     # 근무지 (e.g., 서울 강남구)
    deadline = Column(String(50))              # 마감일
    detail_url = Column(Text, nullable=False)  # 상세 공고 링크 (수기 확인용)

    # 📝 통합 우대사항 및 메모 (수기 입력용)
    preference = Column(Text, default="")      # 수기로 정리할 자격증/스킬/전공 등
    notes = Column(Text, default="")           # 지원 여부, 메모 등
    application_status = Column(String(30), nullable=False, default="미정", server_default="미정")
    favorite = Column(Boolean, nullable=False, default=False, server_default="0")
    description = Column(Text, default="", server_default="")
    responsibilities = Column(Text, default="", server_default="")
    qualifications = Column(Text, default="", server_default="")
    auto_preference = Column(Text, default="", server_default="")
    detail_status = Column(Text, default="미수집", server_default="미수집")

    created_at = Column(DateTime, default=datetime.now)
