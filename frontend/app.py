"""
BioRAG Unified — Streamlit Frontend.
"""
from __future__ import annotations

import os

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="BioRAG", page_icon="🧬", layout="wide")

st.markdown(
    """
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
        padding: 18px 20px; margin: 4px 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        font-size: 14px; line-height: 1.75;
    }
    .res-card h3 {
        color: #166534; font-size: 15px; font-weight: 700;
        margin-bottom: 10px; padding-bottom: 8px;
        border-bottom: 1px solid #dcfce7;
    }
    .badge-ok {
        display: inline-flex; align-items: center; gap: 4px;
        background: #DCFCE7; color: #166534;
        font-size: 12px; font-weight: 700;
        padding: 3px 10px; border-radius: 20px; margin: 6px 0;
    }
    .badge-weak {
        display: inline-flex; align-items: center; gap: 4px;
        background: #FEF9C3; color: #854D0E;
        font-size: 12px; font-weight: 700;
        padding: 3px 10px; border-radius: 20px; margin: 6px 0;
    }
    .badge-none {
        display: inline-flex; align-items: center; gap: 4px;
        background: #FEE2E2; color: #991B1B;
        font-size: 12px; font-weight: 700;
        padding: 3px 10px; border-radius: 20px; margin: 6px 0;
    }
    .score-bar-wrap {
        display: flex; align-items: center; gap: 8px;
        margin: 8px 0 4px; font-size: 12px; color: #6b7280;
    }
    .score-bar-bg {
        flex: 1; height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden;
    }
    .score-bar-fill {
        height: 100%; border-radius: 4px;
        transition: width 0.3s;
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
    .combo-warning {
        background: #FFFBEB; border: 1px solid #FDE68A;
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
        font-size: 10px; font-weight: 600;
        padding: 2px 8px; border-radius: 12px;
    }
    .stButton > button {
        border-radius: 20px !important; font-weight: 500 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


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
        st.error("백엔드 서버에 연결할 수 없습니다.")
        return None
    except Exception as e:
        st.error(f"요청 실패: {e}")
        return None


def check_backend_health() -> dict | None:
    try:
        return requests.get(f"{BACKEND_URL}/api/health", timeout=5).json()
    except Exception:
        return None


# ── 카테고리/타입 한글 매핑 ──

_CAT = {
    "diet_glp1": "다이어트 & GLP-1",
    "skin_beauty_regeneration": "피부/뷰티 & 재생",
    "supplement_trends": "영양제 트렌드",
    "morning_fasted_routines": "아침 공복 루틴",
}
_QT = {"medicine": "의약품", "combo": "조합 건강법", "diet": "식이요법"}


# ── 답변 렌더링 ──

def _source_pills(sources: list[dict]) -> str:
    if not sources:
        return ""
    pills = []
    for s in sources[:5]:
        label = (s.get("journal") or s.get("source_type", "출처")).strip()
        year = s.get("year", "").strip()
        display = f"{label} {year}".strip()
        url = s.get("url", "")
        pmid = s.get("pmid", "")
        if url:
            pills.append(f'<a class="pill-src" href="{url}" target="_blank">{display}</a>')
        elif pmid:
            pills.append(
                f'<a class="pill-src" href="https://pubmed.ncbi.nlm.nih.gov/{pmid}/"'
                f' target="_blank">{display}</a>'
            )
        else:
            pills.append(f'<span class="pill-src">{display}</span>')
    return f'<div class="pill-wrap">{"".join(pills)}</div>'


def _score_bar(score: float) -> str:
    """논문 관련도 점수 바."""
    pct = int(score * 100)
    if pct >= 60:
        color = "#22c55e"
    elif pct >= 30:
        color = "#eab308"
    else:
        color = "#ef4444"
    return (
        '<div class="score-bar-wrap">'
        '<span>논문 관련도</span>'
        '<div class="score-bar-bg">'
        f'<div class="score-bar-fill" style="width:{pct}%;background:{color}"></div>'
        '</div>'
        f'<span>{pct}%</span>'
        '</div>'
    )


def render_card(result: dict) -> str:
    answer = result.get("answer", "")
    has_evidence = result.get("has_paper_evidence", False)
    weak = result.get("weak_evidence", False)
    score = result.get("paper_score", 0.0)
    category = result.get("category") or ""
    query_type = result.get("query_type", "")
    matched = result.get("matched_terms", [])

    # 본문
    parts = []
    for line in answer.split("\n"):
        s = line.strip()
        if not s:
            continue
        if "⚠️" in s or "의사 또는 약사와 상담" in s:
            parts.append(f'<div class="combo-warning">{s}</div>')
        else:
            parts.append(f"<p style='margin:4px 0'>{s}</p>")
    body = "\n".join(parts)

    # 뱃지
    if has_evidence and not weak:
        badge = '<div class="badge-ok">✓ 논문 근거 있음</div>'
    elif has_evidence and weak:
        badge = '<div class="badge-weak">△ 간접 근거</div>'
    else:
        badge = '<div class="badge-none">✗ 직접 근거 없음</div>'

    # 점수 바 (논문이 있을 때만)
    score_html = _score_bar(score) if score > 0 else ""

    # 출처
    sources = _source_pills(result.get("paper_sources", []))


    # 빈 값으로 인한 빈 줄 방지 → compact 이어붙임
    inner = "".join(filter(None, [badge, score_html, body_html, source_html]))
    return f'<div class="res-card"><h3>🧬 BioRAG 분석 리포트</h3>{inner}</div>'


# ── 질문 처리 ──

def process_question(question: str):
    st.session_state.messages.append({"role": "user", "content": question})
    if st.session_state.current_chat_id is None:
        st.session_state.current_chat_id = question[:15]

    result = call_backend(question)
    if result:
        card = render_card(result)
        st.session_state.messages.append({"role": "assistant", "content": card})
    else:
        st.session_state.messages.append({
            "role": "assistant",
            "content": "서버 연결에 실패했습니다. 잠시 후 다시 시도해주세요.",
        })
    st.session_state.chat_history[st.session_state.current_chat_id] = (
        st.session_state.messages.copy()
    )


# ── Session ──

if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat_history" not in st.session_state:
    st.session_state.chat_history = {}
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None


# ── Sidebar ──

with st.sidebar:
    st.markdown(
        '<div style="text-align:center;padding:16px 0 8px">'
        '<div style="font-size:36px">🧬</div>'
        '<div style="font-size:20px;font-weight:700;color:#166534">BioRAG</div>'
        '<div style="font-size:12px;color:#6b7280">논문 기반 건강 팩트체커</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    health = check_backend_health()
    if health and health.get("status") == "ok":
        c = health.get("collections", {})
        st.success(f"서버 연결됨 · 논문 {c.get('papers',0)}개 · 보조 {c.get('aux',0)}개")
    else:
        st.warning("백엔드 서버 연결 대기 중...")

    st.divider()

    if st.button("✏️ 새 채팅", use_container_width=True):
        st.session_state.messages = []
        st.session_state.current_chat_id = None
        st.rerun()

    st.caption("예시 질문")
    for ex in [
        "마운자로 부작용이 뭐야?",
        "올레샷 먹으면 효과 있어?",
        "콜라겐 보충제가 피부에 도움 돼?",
        "오메가3가 심혈관에 도움 되나?",
        "간헐적 단식의 대사 효과는?",
    ]:
        if st.button(f"💬 {ex}", key=f"ex_{ex}", use_container_width=True):
            st.session_state.pending_question = ex
            st.rerun()

    if st.session_state.chat_history:
        st.divider()
        st.caption("대화 기록")
        for cid in list(st.session_state.chat_history.keys()):
            c1, c2 = st.columns([0.85, 0.15])
            if c1.button(f"📝 {cid}", key=f"load_{cid}", use_container_width=True):
                st.session_state.messages = st.session_state.chat_history[cid]
                st.session_state.current_chat_id = cid
                st.rerun()
            if c2.button("✕", key=f"del_{cid}"):
                del st.session_state.chat_history[cid]
                if st.session_state.current_chat_id == cid:
                    st.session_state.messages = []
                    st.session_state.current_chat_id = None
                st.rerun()


# ── Main ──

st.title("🧬 BioRAG")
st.caption("논문 기반 건강 팩트체커 — PubMed + MedlinePlus + LangGraph")

for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="🧬" if m["role"] == "assistant" else None):
        if m["role"] == "assistant":
            st.markdown(m["content"], unsafe_allow_html=True)
        else:
            st.markdown(m["content"])

# 예시 버튼 pending 처리
if st.session_state.pending_question:
    q = st.session_state.pending_question
    st.session_state.pending_question = None
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant", avatar="🧬"):
        with st.spinner("논문 검색 + 분석 중..."):
            process_question(q)
        last = st.session_state.messages[-1]
        if last["role"] == "assistant":
            st.markdown(last["content"], unsafe_allow_html=True)

elif user_input := st.chat_input("건강 트렌드에 대해 물어보세요!"):
    with st.chat_message("user"):
        st.markdown(user_input)
    with st.chat_message("assistant", avatar="🧬"):
        with st.spinner("논문 검색 + 분석 중..."):
            process_question(user_input)
        last = st.session_state.messages[-1]
        if last["role"] == "assistant":
            st.markdown(last["content"], unsafe_allow_html=True)