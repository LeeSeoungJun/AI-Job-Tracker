"""플랫폼 간 중복은 회사·제목·근무지가 모두 같은 경우만 판정한다."""
import re
import unicodedata


def duplicate_key(job):
    def normalize(value, company=False):
        value = unicodedata.normalize('NFKC', str(value or '')).casefold()
        if company:
            value = re.sub(r'주식회사|\(주\)|㈜', '', value)
        return re.sub(r'[^\w]', '', value)

    key = (normalize(job.get('company_name'), True), normalize(job.get('title')),
           normalize(job.get('location_summary')))
    return key if all(key) else None
