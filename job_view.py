"""공고 날짜 표시와 필터."""
import re
from datetime import date, datetime

STATUSES = ["미정", "관심", "지원 예정", "지원 완료", "불합격", "합격"]


def deadline_date(value, collected_at):
    value = str(value or "")
    full = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", value)
    try:
        if full:
            return date(*map(int, full.groups()))
        short = re.search(r"(?<!\d)(\d{1,2})[./-](\d{1,2})(?!\d)", value)
        if not short:
            return None
        reference = datetime.fromisoformat(str(collected_at)).date()
        month, day = map(int, short.groups())
        candidates = []
        for year in (reference.year - 1, reference.year, reference.year + 1):
            try:
                candidates.append(date(year, month, day))
            except ValueError:
                continue
        return min(candidates, key=lambda d: abs((d - reference).days)) if candidates else None
    except (ValueError, TypeError):
        return None


def deadline_label(raw, parsed, today):
    if parsed is None:
        return str(raw or "마감일 미정")
    days = (parsed - today).days
    if days < 0:
        return f"마감 · {parsed:%Y-%m-%d}"
    return f"{'오늘 마감' if days == 0 else f'D-{days}'} · {parsed:%Y-%m-%d}"


def matches_deadline(raw, parsed, today, mode, hide_closed=False):
    closed = (parsed is not None and parsed < today) or str(raw).strip() == '마감' or '접수마감' in str(raw)
    if hide_closed and closed:
        return False
    if mode == '마감된 공고':
        return closed
    if mode == '상시·날짜 미정':
        return parsed is None and not closed
    if mode == '전체':
        return True
    limit = {'오늘 마감': 0, '7일 이내': 7, '30일 이내': 30}[mode]
    return parsed is not None and 0 <= (parsed - today).days <= limit
