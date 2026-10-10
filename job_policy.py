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
