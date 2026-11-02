"""공고 날짜 표시와 필터."""
import re
from datetime import date, datetime

STATUSES = ["미지원", "지원 예정", "지원 완료"]


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


def region_priority(location):
    """수도권 근무지가 여러 곳이면 가장 선호하는 지역을 기준으로 한다."""
    value = str(location or '')
    for priority, region in enumerate(('인천', '서울', '경기')):
        if re.search(rf'(?<![가-힣]){region}(?:광역시|특별시|도)?(?![가-힣])', value):
            return priority
    return None


# 구·시의 대략적인 중심 좌표. 정확한 사업장 주소나 이동 시간을 뜻하지 않는다.
SONGDO_CENTER = (37.392, 126.640)
REGION_CENTERS = {
    '인천': {
        '연수구': (37.410, 126.678), '남동구': (37.447, 126.731),
        '미추홀구': (37.463, 126.650), '중구': (37.474, 126.621),
        '동구': (37.474, 126.643), '부평구': (37.507, 126.721),
        '계양구': (37.537, 126.737), '서구': (37.545, 126.676),
        '강화군': (37.747, 126.488),
    },
    '서울': {
        '강남구': (37.517, 127.047), '강동구': (37.530, 127.124),
        '강북구': (37.640, 127.026), '강서구': (37.551, 126.850),
        '관악구': (37.478, 126.951), '광진구': (37.538, 127.082),
        '구로구': (37.495, 126.887), '금천구': (37.456, 126.895),
        '노원구': (37.655, 127.056), '도봉구': (37.669, 127.047),
        '동대문구': (37.574, 127.040), '동작구': (37.512, 126.939),
        '마포구': (37.566, 126.901), '서대문구': (37.579, 126.937),
        '서초구': (37.483, 127.032), '성동구': (37.563, 127.037),
        '성북구': (37.589, 127.016), '송파구': (37.514, 127.106),
        '양천구': (37.517, 126.867), '영등포구': (37.526, 126.896),
        '용산구': (37.532, 126.990), '은평구': (37.603, 126.929),
        '종로구': (37.573, 126.979), '중구': (37.564, 126.998),
        '중랑구': (37.606, 127.093),
    },
    '경기': {
        '시흥시': (37.380, 126.803), '안산시': (37.322, 126.830),
        '부천시': (37.503, 126.766), '광명시': (37.479, 126.865),
        '김포시': (37.615, 126.715), '안양시': (37.394, 126.957),
        '군포시': (37.361, 126.935), '의왕시': (37.344, 126.968),
        '과천시': (37.430, 126.987), '수원시': (37.263, 127.028),
        '화성시': (37.199, 126.832), '오산시': (37.150, 127.077),
        '평택시': (36.992, 127.113), '성남시': (37.420, 127.126),
        '분당구': (37.382, 127.119), '용인시': (37.241, 127.178),
        '기흥구': (37.280, 127.115), '수지구': (37.322, 127.098),
        '광주시': (37.429, 127.255), '하남시': (37.539, 127.214),
        '고양시': (37.658, 126.832), '파주시': (37.760, 126.780),
        '의정부시': (37.738, 127.034), '양주시': (37.785, 127.046),
        '남양주시': (37.636, 127.217), '구리시': (37.594, 127.130),
        '동두천시': (37.903, 127.060), '포천시': (37.895, 127.200),
        '이천시': (37.272, 127.435), '여주시': (37.298, 127.638),
        '안성시': (37.008, 127.279), '양평군': (37.491, 127.487),
        '가평군': (37.831, 127.510), '연천군': (38.096, 127.075),
    },
}


def songdo_distance(location):
    """송도 기준 대략적인 직선거리(km). 위치를 특정할 수 없으면 미정."""
    from math import radians, sin, cos, asin, sqrt
    value = str(location or '')
    candidates = []
    if '송도' in value and region_priority(value) == 0:
        candidates.append(0.0)
    # 지역별 구 이름 충돌을 피하고, 한 지역에서 더 구체적인 구를 우선한다.
    segments = re.split(r'(?=(?:인천(?:광역시)?|서울(?:특별시)?|경기(?:도)?)(?![가-힣]))', value)
    for segment in segments:
        priority = region_priority(segment)
        if priority is None:
            continue
        region = ('인천', '서울', '경기')[priority]
        matches = [(name, point) for name, point in REGION_CENTERS[region].items()
                   if name in segment]
        districts = [point for name, point in matches if name.endswith('구')]
        for lat, lon in districts or [point for _, point in matches]:
            lat1, lon1 = map(radians, SONGDO_CENTER)
            lat2, lon2 = radians(lat), radians(lon)
            a = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
            candidates.append(6371 * 2 * asin(sqrt(a)))
    return min(candidates) if candidates else None
