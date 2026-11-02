"""수집 조건과 자동 정리에 쓰는 보수적인 날짜 판정."""
import re
from job_view import deadline_date


def requires_graduate_degree(education):
    value = str(education or '')
    if any(word in value for word in ('우대', '무관', '학사', '대졸', '초대졸')):
        return False
    return '석사' in value or '박사' in value


def expired(deadline, collected_at, today):
    value = str(deadline or '').strip()
    if any(word in value for word in ('상시', '채용시', '채용 시')):
        return False
    parsed = deadline_date(value, collected_at)
    if parsed is None:
        return False
    # 연도 없는 날짜의 연말 추정은 표시에는 유용하지만 삭제 근거로 삼지 않는다.
    if not re.search(r'20\d{2}[./-]\d{1,2}[./-]\d{1,2}', value):
        try:
            from datetime import datetime
            reference = datetime.fromisoformat(str(collected_at)).date()
        except (ValueError, TypeError):
            return False
        if abs(parsed.year - reference.year) and parsed < reference:
            return False
    return parsed < today


def accepts_up_to_two_years(experience):
    """신입·경력무관 또는 표기된 경력 연수가 2년을 넘지 않는 공고."""
    value = str(experience or '').strip()
    if '신입' in value or '무관' in value:
        return True
    years = re.search(r'(\d+)\s*년', value)
    # 범위 표기는 상한까지 2년 이내여야 한다.
    span = re.search(r'(\d+)\s*(?:~|～|–|-)\s*(\d+)\s*년', value)
    if span:
        return int(span.group(1)) <= int(span.group(2)) <= 2
    if years:
        return int(years.group(1)) <= 2
    return False
