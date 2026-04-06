from __future__ import annotations

import os
import re

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# ── Page config ──

st.set_page_config(page_title="BioRAG", page_icon="🧬", layout="wide")

# ── CSS ──

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
* { font-family: 'Noto Sans KR', sans-serif; box-sizing: border-box; }

.main { background-color: #f7f8fc !important; }
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #f0fdf4 0%, #dcfce7 100%);
    border-right: 1px solid #bbf7d0;
}

.stChatInput textarea {
    border-radius: 24px !important;
    border: 1.5px solid #86EFAC !important;
    background: #fff !important;
    font-size: 14px !important;
    padding: 12px 18px !important;
}

.res-card {
    background: #ffffff;
    border: 1px solid #e8ebf5;
    border-radius: 4px 20px 20px 20px;
    padding: 18px 20px;
    margin: 4px 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    font-size: 14px;
    line-height: 1.75;
}
.res-card h3 {
    color: #166534;
    font-size: 15px;
    font-weight: 700;
    margin-bottom: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid #dcfce7;
}

.badge-ok {
    display: inline-flex; align-items: center; gap: 4px;
    background: #DCFCE7; color: #166534;
    font-size: 12px; font-weight: 700;
    padding: 3px 10px; border-radius: 20px; margin: 6px 4px 6px 0;
}
.badge-warn {
    display: inline-flex; align-items: center; gap: 4px;
    background: #FEF9C3; color: #854D0E;
    font-size: 12px; font-weight: 700;
    padding: 3px 10px; border-radius: 20px; margin: 6px 0;
}
.badge-weak {
    display: inline-flex; align-items: center; gap: 4px;
    background: #FEF9C3; color: #854D0E;
    font-size: 12px; font-weight: 700;
    padding: 3px 10px; border-radius: 20px; margin: 6px 4px 6px 0;
}
.badge-none {
    display: inline-flex; align-items: center; gap: 4px;
    background: #FEE2E2; color: #991B1B;
    font-size: 12px; font-weight: 700;
    padding: 3px 10px; border-radius: 20px; margin: 6px 0;
}

.pill-wrap { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.pill-src {
    background: #EFF6FF; color: #1E40AF;
    border: 1px solid #BFDBFE;
    font-size: 11px; font-weight: 600;
    padding: 3px 10px; border-radius: 20px;
    text-decoration: none;
}
.pill-src:hover { background: #DBEAFE; }

.score-bar-wrap {
    display: flex; align-items: center; gap: 8px; margin: 8px 0;
}
.score-bar-bg {
    flex: 1; height: 6px; background: #E2E8F0;
    border-radius: 4px; overflow: hidden;
}
.score-bar-fill { height: 100%; border-radius: 4px; }
.score-label { font-size: 11px; color: #64748B; font-weight: 600; min-width: 36px; text-align: right; }

.combo-warning {
    background: #FFFBEB;
    border-radius: 10px; padding: 10px 14px;
    font-size: 12.5px; color: #92400E; margin: 10px 0;
}

.meta-bar {
    display: flex; gap: 8px; flex-wrap: wrap;
    margin-top: 12px; padding-top: 10px;
    border-top: 1px solid #f0f0f0;
}
.meta-pill {
    background: #F1F5F9; color: #475569;
    border: 1px solid #CBD5E1;
    font-size: 12px; font-weight: 700;
    padding: 3px 10px; border-radius: 20px;
}

.stButton > button {
    border-radius: 20px !important;
    font-weight: 500 !important;
}
</style>
""", unsafe_allow_html=True)


# ── Backend 호출 ──

def call_backend(question: str) -> dict | None:
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/ask",
            json={"question": question},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error("백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.")
        return None
    except Exception as e:
        st.error(f"요청 실패: {e}")
        return None


def check_backend_health() -> dict | None:
    try:
        resp = requests.get(f"{BACKEND_URL}/api/health", timeout=5)
        return resp.json()
    except Exception:
        return None


# ── 답변 렌더링 ──

def render_score_bar(score: float) -> str:
    pct = int(score * 100)
    color = "#22C55E" if score >= 0.75 else "#F59E0B" if score >= 0.5 else "#EF4444"
    return (
        f'<div class="score-bar-wrap">'
        f'<span style="font-size:11px;color:#64748B;font-weight:600;min-width:60px">논문 관련도</span>'
        f'<div class="score-bar-bg"><div class="score-bar-fill" style="width:{pct}%;background:{color}"></div></div>'
        f'<span class="score-label">{pct}%</span>'
        f'</div>'
    )


def render_source_pills(sources: list[dict]) -> str:
    if not sources:
        return ""
    pills = []
    for s in sources[:5]:
        label = s.get("journal") or s.get("source_type", "출처")
        year = s.get("year", "")
        url = s.get("url", "")
        pmid = s.get("pmid", "")

        if url:
            pills.append(f'<a class="pill-src" href="{url}" target="_blank">{label} {year}</a>')
        elif pmid:
            pills.append(
                f'<a class="pill-src" href="https://pubmed.ncbi.nlm.nih.gov/{pmid}/" '
                f'target="_blank">{label} {year}</a>'
            )
        else:
            pills.append(f'<span class="pill-src">{label} {year}</span>')

    return f'<div class="pill-wrap">{"".join(pills)}</div>'


def render_answer_card(result: dict) -> str:
    answer = result.get("answer", "")
    paper_sources = result.get("paper_sources", [])
    aux_sources = result.get("aux_sources", [])
    has_evidence = result.get("has_paper_evidence", True)
    paper_score = result.get("paper_score", 0.0)
    category = result.get("category", "")
    query_type = result.get("query_type", "general")
    matched = result.get("matched_terms", [])

    # 답변 본문 — HTML 태그 완전 제거 후 파싱
    clean_answer = re.sub(r"<[^>]+>", "", answer)  # HTML 태그 제거
    clean_answer = re.sub(r'(?<!\n)(※)', r'\n\n\1', clean_answer)
    lines = clean_answer.split("\n")
    body_parts = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            body_parts.append("<br>")
        elif "⚠️" in stripped or "의사 또는 약사와 상담" in stripped:
            body_parts.append(f'<div class="combo-warning">{stripped}</div>')
        elif "※ 검색된 논문의 관련도가 낮아" in stripped:
            pass
        else:
            body_parts.append(f"<p style='margin:4px 0'>{stripped}</p>")
    body_html = "<div style='margin-top:12px'>" + "\n".join(body_parts) + "<div style='margin-bottom:12px'></div></div>" 

    # 근거 뱃지
    if has_evidence:
        badge = '<div class="badge-ok">✓ 논문 근거 있음</div>'
    else:
        badge = '<div class="badge-none">✗ 직접 근거 없음</div>'

    # score 바
    score_html = render_score_bar(paper_score) if has_evidence else ""

    # 출처 pills
    source_html = render_source_pills(paper_sources)

    # 용어 매칭 정보
    term_html = ""
    if matched:
        term_pills = " ".join(
            f'<span class="meta-pill">{t["alias"]} → {", ".join(t.get("expansions", [])[:3])}</span>'
            for t in matched
        )
        term_html = f'<div style="margin-top:8px">{term_pills}</div>'

    # 메타 바 (general은 표시 안 함)
    meta_pills = []
    if category:
        meta_pills.append(f'<span class="meta-pill">📂 {category}</span>')
    if query_type and query_type != "general":
        meta_pills.append(f'<span class="meta-pill">🏷️ {query_type}</span>')
    if result.get("needs_web"):
        meta_pills.append('<span class="meta-pill">🌐 웹검색 사용</span>')
    meta_html = f'<div class="meta-bar">{"".join(meta_pills)}</div>' if meta_pills else ""

    return f"""
    <div class="res-card">
        <h3>🧬 BioRAG 분석 리포트</h3>
        {badge}
        {score_html}
        {body_html}
        {source_html}
        {term_html}
        {meta_html}
    </div>
    """


# ── Session ──

if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat_history" not in st.session_state:
    st.session_state.chat_history = {}
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None
if "pending_input" not in st.session_state:
    st.session_state.pending_input = None


# ── Sidebar ──

with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding:16px 0 8px">
        <div style="font-size:36px">🧬</div>
        <div style="font-size:20px; font-weight:700; color:#166534">BioRAG</div>
        <div style="font-size:12px; color:#6b7280">논문 기반 건강 팩트체커</div>
    </div>
    """, unsafe_allow_html=True)

    # 서버 상태
    health = check_backend_health()
    if health and health.get("status") == "ok":
        cols = health.get("collections", {})
        st.success(f"서버 연결됨 · 논문 {cols.get('papers', 0)}개 · 보조 {cols.get('aux', 0)}개")
    else:
        st.warning("백엔드 서버 연결 대기 중...")

    st.divider()

    if st.button("✏️ 새 채팅", use_container_width=True):
        st.session_state.messages = []
        st.session_state.current_chat_id = None
        st.rerun()

    st.caption("예시 질문")
    examples = [
        "마운자로의 효과",
        "콜라겐이 피부에 도움이 돼?",
    ]
    for ex in examples:
        if st.button(f"💬 {ex}", key=f"ex_{ex}", use_container_width=True):
            st.session_state.pending_input = ex
            st.session_state.current_chat_id = ex[:15]
            st.rerun()

    # 대화 기록
    if st.session_state.chat_history:
        st.divider()
        st.caption("대화 기록")
        for chat_id in list(st.session_state.chat_history.keys()):
            c1, c2 = st.columns([0.85, 0.15])
            if c1.button(f"📝 {chat_id}", key=f"load_{chat_id}", use_container_width=True):
                st.session_state.messages = st.session_state.chat_history[chat_id]
                st.session_state.current_chat_id = chat_id
                st.rerun()
            if c2.button("✕", key=f"del_{chat_id}"):
                del st.session_state.chat_history[chat_id]
                if st.session_state.current_chat_id == chat_id:
                    st.session_state.messages = []
                    st.session_state.current_chat_id = None
                st.rerun()


# ── Main chat area ──

st.title("🧬 BioRAG")
st.caption("논문 기반 건강 팩트체커 — PubMed + MedlinePlus + Glossary")

for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="🧬" if m["role"] == "assistant" else None):
        if m["role"] == "assistant" and m.get("result"):
            st.markdown(render_answer_card(m["result"]), unsafe_allow_html=True)
        else:
            st.markdown(m["content"], unsafe_allow_html=True)

# 예시 질문 버튼으로 들어온 입력 처리
pending = st.session_state.pop("pending_input", None)
user_input = st.chat_input("건강 트렌드에 대해 물어보세요!") or pending

if user_input:
    if st.session_state.current_chat_id is None:
        st.session_state.current_chat_id = user_input[:15]

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant", avatar="🧬"):
        with st.spinner("논문 검색 + 분석 중..."):
            result = call_backend(user_input)

        if result:
            # answer 필드에서 잔여 HTML 태그를 한 번 더 제거해서 저장
            clean_text = re.sub(r"<[^>]+>", "", result.get("answer", ""))
            result["answer"] = clean_text

            card_html = render_answer_card(result)
            st.markdown(card_html, unsafe_allow_html=True)
            st.session_state.messages.append({
                "role": "assistant",
                "content": clean_text,
                "result": result,
            })
        else:
            fallback = "서버 연결에 실패했습니다. 잠시 후 다시 시도해주세요."
            st.warning(fallback)
            st.session_state.messages.append({"role": "assistant", "content": fallback})

        # 기록 저장
        st.session_state.chat_history[st.session_state.current_chat_id] = (
            st.session_state.messages.copy()
        )