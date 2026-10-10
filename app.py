"""카드로 확인하고 지원 상황을 관리하는 채용 공고 보관함."""
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
from sqlalchemy import text
from database.connection import engine
from job_view import STATUSES, deadline_date, deadline_label, matches_deadline

st.set_page_config(page_title="내 채용 공고", page_icon="💼", layout="wide")


def load_data():
    data = pd.read_sql("SELECT * FROM job_postings ORDER BY id DESC", engine)
    for column in ['preference', 'notes', 'company_name', 'title', 'deadline',
                   'experience', 'education', 'location_summary', 'detail_url',
                   'description', 'responsibilities', 'qualifications', 'auto_preference', 'detail_status']:
        data[column] = data[column].fillna('')
    data['application_status'] = data['application_status'].fillna('미정')
    data['favorite'] = data['favorite'].fillna(0).astype(bool)
    data['parsed_deadline'] = pd.Series(
        [deadline_date(row.deadline, row.created_at) for row in data.itertuples()],
        index=data.index, dtype=object)
    return data


def update_job(job_id, pref, notes, status, favorite):
    if status not in STATUSES:
        raise ValueError("지원 상태가 올바르지 않습니다.")
    with engine.begin() as conn:
        result = conn.execute(text(
            "UPDATE job_postings SET preference=:pref, notes=:notes, "
            "application_status=:status, favorite=:favorite WHERE id=:id"
        ), dict(pref=pref, notes=notes, status=status, favorite=bool(favorite), id=int(job_id)))
        if result.rowcount != 1:
            raise ValueError("공고가 없습니다. 화면을 새로고침해 주세요.")


st.title("💼 내 채용 공고")
st.caption("관심 공고를 모으고, 마감일과 지원 상황을 한눈에 확인하세요.")
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
cols[1].metric("메모 작성", f"{df['notes'].str.strip().ne('').sum()}개")
cols[2].metric("즐겨찾기", f"{df['favorite'].sum()}개")
cols[3].metric("지원 완료", f"{df['application_status'].eq('지원 완료').sum()}개")

st.sidebar.header("공고 찾기")
keyword = st.sidebar.text_input("기업명 또는 공고 제목 검색").strip()
favorites_only = st.sidebar.checkbox("즐겨찾기만 보기")
statuses = st.sidebar.multiselect("지원 상태", STATUSES)
deadline_filter = st.sidebar.selectbox("마감일", ["전체", "오늘 마감", "7일 이내", "30일 이내", "마감된 공고", "상시·날짜 미정"])
hide_closed = st.sidebar.checkbox("마감된 공고 숨기기")
sort_order = st.sidebar.selectbox("정렬", ["최근 수집순", "마감 임박순"])
view = st.sidebar.radio("보기 방식", ["카드", "표"])
st.sidebar.caption("연도 없는 마감일은 수집 시점에 가까운 연도로 추정합니다. 정확한 마감 여부는 원문을 확인하세요.")

filtered = df.copy()
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

st.subheader(f"공고 {len(filtered)}개")
if filtered.empty:
    st.info("표시할 공고가 없습니다. 검색어나 필터를 바꿔보세요.")
    st.stop()
if view == '표':
    st.dataframe(filtered[['company_name', 'title', 'location_summary', 'experience', 'deadline',
                          'application_status', 'favorite', 'detail_url']], hide_index=True,
                 column_config={'detail_url': st.column_config.LinkColumn('원문', display_text='공고 열기')},
                 width='stretch')
    st.caption("아래 공고에서 지원 상태와 메모를 수정할 수 있습니다.")

page_count = (len(filtered) + 11) // 12
filter_key = repr((keyword, favorites_only, statuses, deadline_filter, hide_closed, sort_order, view))
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
            with st.expander("지원 상태 · 즐겨찾기 · 메모 수정"):
                with st.form(f"edit_{job_id}"):
                    current_status = row['application_status'] if row['application_status'] in STATUSES else '미정'
                    status = st.selectbox("지원 상태", STATUSES, index=STATUSES.index(current_status), key=f'status_{job_id}')
                    favorite = st.checkbox("즐겨찾기", value=bool(row['favorite']), key=f'favorite_{job_id}')
                    pref = st.text_area("우대사항 개인 메모", value=row['preference'], key=f'pref_{job_id}')
                    notes = st.text_area("개인 메모", value=row['notes'], key=f'notes_{job_id}')
                    submitted = st.form_submit_button("저장하기")
                if submitted:
                    try:
                        update_job(job_id, pref, notes, status, favorite)
                    except Exception as exc:
                        st.error(f"저장하지 못했습니다: {exc}")
                    else:
                        st.session_state['saved_message'] = f"{row['company_name']} 공고를 저장했습니다."
                        st.rerun()
