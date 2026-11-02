"""카드로 확인하고 지원 상황을 관리하는 채용 공고 보관함."""
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, urlencode

import pandas as pd
import streamlit as st
from sqlalchemy import text
from database.connection import engine
from job_policy import accepts_up_to_two_years
from job_view import STATUSES, deadline_date, deadline_label, matches_deadline, region_priority, songdo_distance

st.set_page_config(page_title="내 채용 공고", page_icon="💼", layout="wide")


def load_data():
    data = pd.read_sql("SELECT * FROM job_postings ORDER BY id DESC", engine)
    for column in ['preference', 'notes', 'company_name', 'title', 'deadline',
                   'experience', 'education', 'location_summary', 'detail_url',
                   'description', 'responsibilities', 'qualifications', 'auto_preference', 'detail_status', 'jobplanet_checked_on',
                   'jobplanet_source', 'jobplanet_source_url']:
        data[column] = data[column].fillna('')
    data['_region_priority'] = data['location_summary'].map(region_priority)
    data = data[data['_region_priority'].notna() & data['experience'].map(accepts_up_to_two_years)].copy()
    data['_songdo_distance'] = data['location_summary'].map(songdo_distance)
    data['application_status'] = data['application_status'].fillna('미지원')
    data['status_updated'] = data['status_updated'].fillna(0).astype(bool)
    data['favorite'] = data['favorite'].fillna(0).astype(bool)
    data['parsed_deadline'] = pd.Series(
        [deadline_date(row.deadline, row.created_at) for row in data.itertuples()],
        index=data.index, dtype=object)
    return data


def update_status(job_id, status):
    if status not in STATUSES:
        raise ValueError('지원 상태가 올바르지 않습니다.')
    with engine.begin() as conn:
        result = conn.execute(text(
            'UPDATE job_postings SET application_status=:status, status_updated=1 WHERE id=:id'
        ), dict(status=status, id=int(job_id)))
        if result.rowcount != 1:
            raise ValueError('공고가 없습니다. 화면을 새로고침해 주세요.')


def update_notes(job_id, notes):
    with engine.begin() as conn:
        result = conn.execute(text('UPDATE job_postings SET notes=:notes WHERE id=:id'),
                              dict(notes=notes, id=int(job_id)))
        if result.rowcount != 1:
            raise ValueError('공고가 없습니다. 화면을 새로고침해 주세요.')


st.title("💼 내 채용 공고")
st.caption("신입·경력무관 및 경력 표기가 2년 이내인 수도권 공고를 송도에서 가까운 순으로 표시합니다. 구·시 중심 기준의 대략적인 직선거리이며 출퇴근 시간과는 다릅니다.")
if message := st.session_state.pop('saved_message', None):
    st.success(message)
try:
    df = load_data()
except Exception as exc:
    st.error(f"공고를 불러오지 못했습니다: {exc}")
    st.stop()

today = datetime.now(ZoneInfo('Asia/Seoul')).date()
cols = st.columns(4)
cols[0].metric("전체 공고", f"{len(df)}개")
cols[1].metric("지원 예정", f"{df['application_status'].eq('지원 예정').sum()}개")
cols[2].metric("즐겨찾기", f"{df['favorite'].sum()}개")
cols[3].metric("지원 완료", f"{df['application_status'].eq('지원 완료').sum()}개")

st.sidebar.header("공고 찾기")
keyword = st.sidebar.text_input("기업명 또는 공고 제목 검색").strip()
favorites_only = st.sidebar.checkbox("즐겨찾기만 보기")
show_updated = st.sidebar.checkbox("상태 변경한 공고도 보기", key="show_updated")
statuses = st.sidebar.multiselect("지원 상태", STATUSES)
deadline_filter = st.sidebar.selectbox("마감일", ["전체", "오늘 마감", "7일 이내", "30일 이내", "마감된 공고", "상시·날짜 미정"])
hide_closed = st.sidebar.checkbox("마감된 공고 숨기기")
sort_order = st.sidebar.selectbox("정렬", ["송도에서 가까운 순", "최근 수집순", "마감 임박순"])
view = st.sidebar.radio("보기 방식", ["카드", "표"])
st.sidebar.caption('송도 센트럴파크 기준입니다. 거리 계산이 어려운 공고는 가까운 순 정렬에서 마지막에 표시합니다.')
st.sidebar.caption("연도 없는 마감일은 수집 시점에 가까운 연도로 추정합니다. 정확한 마감 여부는 원문을 확인하세요.")

filtered = df.copy()
if not show_updated and not statuses:
    filtered = filtered[~filtered['status_updated']]
if keyword:
    filtered = filtered[filtered['company_name'].str.contains(keyword, case=False, regex=False) |
                        filtered['title'].str.contains(keyword, case=False, regex=False)]
if favorites_only:
    filtered = filtered[filtered['favorite']]
if statuses:
    filtered = filtered[filtered['application_status'].isin(statuses)]
if not filtered.empty:
    filtered = filtered[filtered.apply(lambda row: matches_deadline(
        row['deadline'], row['parsed_deadline'], today, deadline_filter, hide_closed), axis=1)]
if sort_order == '마감 임박순' and not filtered.empty:
    filtered = filtered.assign(_order=filtered['parsed_deadline'].map(
        lambda d: (d - today).days if d is not None and d >= today else 999999
    )).sort_values(['_order', 'id'], ascending=[True, False])
elif sort_order == '송도에서 가까운 순':
    filtered = filtered.sort_values(['_songdo_distance', 'id'], ascending=[True, False], na_position='last')
else:
    filtered = filtered.sort_values('id', ascending=False)

st.subheader(f"공고 {len(filtered)}개")
if filtered.empty:
    st.info("표시할 공고가 없습니다. 검색어나 필터를 바꿔보세요.")
    st.stop()
if view == '표':
    st.dataframe(filtered[['company_name', 'title', 'location_summary', 'experience', 'deadline',
                          'application_status', 'favorite', 'detail_url']], hide_index=True,
                 column_config={'detail_url': st.column_config.LinkColumn('원문', display_text='공고 열기')},
                 width='stretch')
    st.caption("아래 공고의 버튼을 누르면 지원 상태가 바로 저장됩니다.")

page_count = (len(filtered) + 11) // 12
filter_key = repr((keyword, favorites_only, show_updated, statuses, deadline_filter, hide_closed, sort_order, view))
if st.session_state.get('last_filters') != filter_key:
    st.session_state['page'] = 1
    st.session_state['last_filters'] = filter_key
if st.session_state.get('page', 1) > page_count:
    st.session_state['page'] = 1
page = st.selectbox("페이지", range(1, page_count + 1), key='page')
visible = filtered.iloc[(page - 1) * 12:page * 12]
card_columns = st.columns(2)
for position, (_, row) in enumerate(visible.iterrows()):
    job_id = int(row['id'])
    with card_columns[position % 2]:
        with st.container(border=True):
            st.caption(f"{'⭐ ' if row['favorite'] else ''}{row['company_name']} · {row['application_status']}")
            st.subheader(row['title'])
            st.write(' · '.join(value for value in [row['location_summary'], row['experience'], row['education']] if value))
            st.write(deadline_label(row['deadline'], row['parsed_deadline'], today))
            if urlparse(row['detail_url']).scheme in ('http', 'https'):
                st.link_button("원문 보기 ↗", row['detail_url'])
            if row['jobplanet_source_url']:
                st.link_button('잡플래닛 평점 보기 ↗', row['jobplanet_source_url'])
            else:
                st.link_button('잡플래닛에서 회사 검색 ↗',
                               'https://www.jobplanet.co.kr/search/companies?' + urlencode({
                                   'query': row['company_name']}))
            if pd.notna(row['jobplanet_rating']):
                count_label = f" · 리뷰 {int(row['jobplanet_review_count'])}개" if pd.notna(row['jobplanet_review_count']) else ''
                st.caption(f"잡플래닛 {row['jobplanet_rating']:.1f}/5{count_label} · 확인 {row['jobplanet_checked_on']} · {row['jobplanet_source'] or '직접 입력'}")
                if row['jobplanet_source_url']:
                    st.caption('공개 검색 결과에서 확인한 값으로 최신 평점과 다를 수 있습니다. 공고 등록 회사 기준입니다.')
            with st.expander("공고 내용 · 자동 수집"):
                st.caption(f"최근 수집 상태: {row['detail_status'] or '미수집'}")
                for field, label in [('responsibilities', '주요 업무'), ('qualifications', '자격요건'), ('auto_preference', '우대사항')]:
                    st.write(f"**{label}**")
                    st.text(row[field] or '항목을 구분하지 못했습니다. 아래 전체 본문이나 원문을 확인하세요.')
                if row['description']:
                    st.write('**수집한 전체 본문**')
                    st.text(row['description'])
                else:
                    st.info('본문이 아직 없습니다. main.py를 실행하면 검색된 공고의 상세 내용을 수집합니다. 이미지 공고는 원문 확인이 필요합니다.')
            st.caption('지원 상태 · 누르면 바로 저장됩니다.')
            status_columns = st.columns(3)
            for status_column, status in zip(status_columns, STATUSES):
                if status_column.button(status.replace(' ', ''), key=f'status_{job_id}_{status}', width='stretch'):
                    try:
                        update_status(job_id, status)
                    except Exception as exc:
                        st.error(f'저장하지 못했습니다: {exc}')
                    else:
                        st.session_state['saved_message'] = f"{row['company_name']} · {status} 저장 완료"
                        st.rerun()

            with st.form(f'notes_{job_id}'):
                notes = st.text_area('메모', value=row['notes'], height=80,
                                     placeholder='간단한 메모를 남겨보세요.', key=f'notes_text_{job_id}')
                notes_submitted = st.form_submit_button('메모 저장')
            if notes_submitted:
                try:
                    update_notes(job_id, notes)
                except Exception as exc:
                    st.error(f'메모를 저장하지 못했습니다: {exc}')
                else:
                    st.session_state['saved_message'] = f"{row['company_name']} 메모를 저장했습니다."
                    st.rerun()
