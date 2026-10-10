"""본문 제목을 기준으로 원문을 분리한다. 없는 내용을 생성하지 않는다."""
import re

FIELDS = ('description', 'responsibilities', 'qualifications', 'auto_preference', 'detail_status')
HEADINGS = {
    '주요업무': 'responsibilities', '담당업무': 'responsibilities', '업무내용': 'responsibilities',
    '자격요건': 'qualifications', '지원자격': 'qualifications', '필수요건': 'qualifications',
    '우대사항': 'auto_preference', '우대조건': 'auto_preference',
    '근무조건': None, '복리후생': None, '전형절차': None, '지원방법': None,
    '접수기간': None, '유의사항': None, '제출서류': None, '회사소개': None,
    '복지및혜택': None, '채용절차': None, '접수방법': None, '모집분야': None,
    '지원자격및우대사항': 'qualifications', '자격요건및우대사항': 'qualifications',
    '어떤업무를담당하게되나요?': 'responsibilities',
    '이런분을찾고있어요!': 'qualifications', '이런분이면좋아요': 'auto_preference',
    '채용절차및안내사항': None,
}


def extract_sections(body):
    buckets = {key: [] for key in ('responsibilities', 'qualifications', 'auto_preference')}
    active = None
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        heading, separator, remainder = re.sub(r'^[^가-힣A-Za-z]+', '', line).replace('：', ':').partition(':')
        normalized = re.sub(r'[\s\]】：]', '', heading)
        if normalized in HEADINGS:
            active = HEADINGS[normalized]
            if active and separator and remainder.strip():
                buckets[active].append(remainder.strip())
        elif active:
            buckets[active].append(line)
    return {key: '\n'.join(lines) for key, lines in buckets.items()}


def body_text(element):
    for node in element.select('script, style, noscript'):
        node.decompose()
    # 인라인 강조 태그는 문장/제목을 끊지 않는다.
    for node in element.select('span, strong, b, em, a'):
        node.unwrap()
    return '\n'.join(line.strip() for line in element.get_text('\n').splitlines() if line.strip())
