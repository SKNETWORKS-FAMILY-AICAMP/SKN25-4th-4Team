# SKN25-4th-4Team- BioRAG

</br>

## 1. 팀 소개

| 이름 | 담당 업무 |
|---|---|
| 김주희 | Docker 환경 구성 및 시스템 아키텍처 설계 |
| 김찬영 | Render · Neon PostgreSQL 배포, 화면설계서 · 요구사항정의서 작성 |
| 조민서 | Django · DRF 인증 서버 구축, Airflow 테스트 자동화 설계, 문서 작성 |
| 최현우 | Frontend 개발 및 backend 연동, Neon PostgreSQL 연동, PPT 및 발표 |

</br>
</br>

## 2. 프로젝트 개요

### BioRAG
> 건강 트렌드 질의응답 챗봇 (LLM 연동 논문 기반의 건강 지식 서비스)

</br>

### 프로젝트 배경 및 목적
SNS와 커뮤니티에 넘쳐나는 건강 정보는 출처가 불명확하고 과장·왜곡된 경우가 많다. </br>
특히 GLP-1 주사, 영양제, 공복 루틴 등 건강 트렌드 관련 질문에 대해 신뢰할 수 있는 정보를 얻기 어렵다. </br>
</br>
본 프로젝트는 세계 최대 의학 논문 데이터베이스인 **PubMed**를 기반으로,
환각(Hallucination) 방지를 위한 질의응답 RAG 챗봇을 구축하는 것을 목적으로 한다.

</br>

### 3차 → 4차 주요 변경사항

| 항목 | 3차 | 4차 |
|---|---|---|
| 프론트엔드 | Streamlit | React + TypeScript |
| 백엔드 | FastAPI 단일 서버 | FastAPI (RAG) + Django (인증·세션) |
| 인프라 | 로컬 단일 실행 | Docker Compose 멀티서비스 |
| 데이터 수집 | 수동 스크립트 | Airflow 자동화 파이프라인 |
| 배포 | 미배포 | Render.com 클라우드 배포 |

</br>

### 주요 기능
- **논문 근거 기반 답변** </br>
  PubMed 333개 논문 초록을 벡터 검색해 출처(논문 제목·연도) 자동 표기. 컨텍스트에 없는 내용은 생성하지 않는 환각 방지 구조 적용

- **3단계 근거 판정** </br>
  LLM이 논문 내용과 유사도 점수를 함께 평가해 **직접 근거 / 간접 근거 / 근거 없음** 3단계로 판정, 뱃지와 색상 바로 시각화

- **웹 검색 보완** </br>
  논문 유사도 낮거나 신조어 미등록 용어일 경우 Tavily 웹검색으로 자동 보완. MedlinePlus·Glossary 보조 문서도 병렬 검색

- **사용자 인증 및 대화 기록** </br>
  회원가입·로그인 기반 개인화 서비스. 세션별 대화 기록 저장 및 조회

- **Airflow 데이터 수집 자동화** </br>
  PubMed 크롤링 → 벡터DB 업데이트 → 품질 테스트 보고서 생성까지 DAG 파이프라인으로 자동화

</br>

### 기대 효과
- 사용자가 건강 정보의 신뢰도를 논문 출처와 함께 직접 확인 가능
- 신조어·유행어 기반 질문도 학술 근거로 연결
- 환각 방지 구조로 잘못된 의료 정보 전달 최소화

</br>
</br>

## 3. 프로젝트 구조

```
biorag-health-chatbot/
├── .env                          # 환경변수 설정
├── .env.sample                   # 환경변수 예시
├── docker-compose.yml            # 멀티서비스 컨테이너 구성
│
├── backend/
│   ├── Dockerfile.fastapi        # FastAPI 컨테이너
│   ├── Dockerfile.django         # Django 컨테이너
│   │
│   ├── app/                      # FastAPI 앱
│   │   ├── main.py               # FastAPI 진입점
│   │   ├── schemas.py            # 요청/응답 스키마
│   │   └── settings.py           # 앱 설정
│   │
│   ├── accounts/                 # Django 인증 앱
│   │   ├── models.py             # 사용자 모델
│   │   ├── views.py              # 회원가입·로그인 API
│   │   └── urls.py
│   │
│   ├── chat/                     # Django 채팅 앱
│   │   ├── models.py             # ChatSession · Message 모델
│   │   ├── views.py              # 질의응답·스트리밍·세션 API
│   │   └── urls.py
│   │
│   ├── config/                   # Django 설정
│   │   ├── settings.py
│   │   └── urls.py
│   │
│   ├── configs/
│   │   ├── glossary.json         # 의학 용어 사전
│   │   ├── pubmed_topics.json    # PubMed 수집 토픽 목록
│   │   └── domain_scope.json     # 도메인 범위 설정
│   │
│   ├── ingestion/
│   │   ├── crawl_pubmed.py       # PubMed 논문 크롤러
│   │   ├── crawl_aux_docs.py     # 보조 문서 크롤러
│   │   └── build_vectorstores.py # 벡터스토어 빌드
│   │
│   ├── pipeline/
│   │   ├── state.py              # LangGraph 상태 정의
│   │   ├── graph.py              # RAG 파이프라인 그래프
│   │   ├── nodes.py              # 그래프 노드 함수
│   │   ├── rag_service.py        # RAG 서비스
│   │   ├── retriever.py          # 벡터스토어 검색기
│   │   ├── category_router.py    # 질문 카테고리 분류
│   │   ├── korean_rewriter.py    # 한국어 재작성기
│   │   ├── glossary_matcher.py   # 용어 사전 매처
│   │   └── external_search.py    # 외부 검색 (Tavily)
│   │
│   └── requirements.txt
│
├── frontend/
│   ├── Dockerfile
│   ├── src/
│   │   ├── App.tsx               # 메인 컴포넌트
│   │   ├── api.ts                # API 호출 함수
│   │   ├── types.ts              # TypeScript 타입 정의
│   │   └── styles.css            # 전역 스타일
│   └── package.json
│
├── airflow/
│   ├── Dockerfile
│   └── dags/
│       └── biorag_report_pipeline.py  # 데이터 수집 + 품질 테스트 DAG
│
└── docs/
    ├── wireframe.html            # 화면설계서
    ├── architecture.html         # 요구사항정의서 (시스템 구성도)
    └── test_report.md  # 테스트 계획 및 결과 보고서
```

</br>
</br>

## 4. 시스템 아키텍처
<img width="1000" height="994" alt="Image" src="https://github.com/user-attachments/assets/4690ca4c-33b3-4fa7-8a12-8ab85a9aa1a6" />

</br>

```
┌─────────────┐     HTTP/SSE     ┌──────────────┐     HybridRAGService
│   Browser   │ ──────────────▶ │    Django    │ ──────────────────────▶ RAG Pipeline
│  React+TS   │                  │  (인증·세션) │
└─────────────┘                  └──────────────┘
                                        │
                                        ▼
                                 ┌──────────────┐
                                 │   FastAPI    │  ◀── Airflow (데이터 수집)
                                 │  (RAG API)   │
                                 └──────────────┘
                                        │
                              ┌─────────┴─────────┐
                              ▼                   ▼
                          ChromaDB            OpenAI API
                         (벡터스토어)         (GPT-4o · Embeddings)
```

</br>

### 3단계 근거 판정

| 단계 | 유사도 점수 | 조건 | 뱃지 |
|---|---|---|---|
| 직접 근거 | 50% 이상 | LLM이 직접 관련 논문 있다고 판단 (`weak_evidence=False`) | 초록 `◎ 논문 근거 있음` |
| 간접 근거 | 10~49% | LLM이 간접 관련만 있다고 판단 (`weak_evidence=True`) | 노랑 `△ 간접 근거` |
| 근거 없음 | 10% 미만 | 유사도 하드 컷오프 (`paper_score < 0.1`) | 빨강 `✕ 직접 근거 없음` |

</br>
</br>

## 5. 데이터 수집 및 전처리

### Airflow 자동화 파이프라인

```
crawl_pubmed → crawl_aux_docs → build_vectorstores → run_quality_tests → generate_report
```

| Task | 설명 |
|---|---|
| `crawl_pubmed` | PubMed Entrez API로 4개 카테고리 논문 수집 |
| `crawl_aux_docs` | MedlinePlus · Glossary 보조문서 수집 |
| `build_vectorstores` | OpenAI Embeddings → ChromaDB 저장 |
| `run_quality_tests` | 12개 벤치마크 질문으로 RAG 품질 자동 측정 |
| `generate_report` | JSON 품질 보고서 자동 저장 |

</br>

### 수집 데이터

| 구분 | 출처 | 건수 | 저장 형식 |
|---|---|---|---|
| 메인 데이터 | PubMed Entrez API | 333개 논문 초록 | `papers.jsonl` |
| 보조 데이터 | MedlinePlus · Glossary | 120개 | `aux_docs.jsonl` |

</br>
</br>

## 6. 화면 구성

### 인증

| 로그인 | 회원가입 |
|---|---|
| <img width="500" src="https://github.com/user-attachments/assets/4e588342-e547-42ad-9872-15f7d3ee42c4" /> | <img width="500" alt="Image" src="https://github.com/user-attachments/assets/18461749-0eab-41ac-92d0-a06a1e99b4cd" /> |

</br>

### 챗봇

**직접 근거 답변** — 논문 관련도 93%

<img width="900" src="https://github.com/user-attachments/assets/a8a37d9a-a0a4-451c-9219-0633fc9ef2b5" />

</br>

**간접 근거 답변** — 논문 관련도 38%

<img width="900" src="https://github.com/user-attachments/assets/1cc69889-e192-46b6-92f7-d6faf974855f" />


</br>
</br>

## 7. 빠른 시작

### 클라우드 배포 (Render)

Render 무료 플랜 특성상 ChromaDB 파일을 git으로 직접 포함해야 했습니다. </br>
팀원이 별도 배포 전용 레포를 생성해 `.gitignore`에서 ChromaDB를 제외하고 푸시한 뒤 Render에 연결했습니다.

> 배포 전용 레포: https://github.com/Chyoung812/SKN25-4th

</br>

**데이터 저장소 분리**

| 데이터 | 저장소 | 역할 |
|---|---|---|
| 회원, 채팅 세션, 메시지 | Neon PostgreSQL | Django ORM 모델 기반 관계형 DB |
| 논문·보조문서 임베딩 | ChromaDB (벡터DB) | RAG 검색용 |

</br>

**배포 구조**
```
Render Web Service (Django)
│
│ DATABASE_URL (환경변수)
▼
Neon PostgreSQL
(accounts_user / chat_chatsession / chat_message)
```

</br>

### Docker Compose

```bash
# 1. 환경변수 설정
cp .env.sample .env
# .env 파일에 아래 값 입력

# 2. 전체 서비스 실행
docker compose up -d

# 3. 접속
# 프론트엔드: http://localhost:5173
# Django API: http://localhost:8001
# FastAPI:    http://localhost:8000
# Airflow:    http://localhost:8080  (admin / admin1234)
```

</br>

### 데이터 초기화 (Airflow)

```bash
# Airflow UI 접속 후 DAG 수동 실행
# URL: http://localhost:8080
# 계정: admin / admin1234
# DAG: biorag_report_pipeline → [Trigger DAG ▶] 클릭
```

</br>
</br>

## 8. 기술 스택

| 구분 | 기술 |
|---|---|
| **Frontend** | ![React](https://img.shields.io/badge/React-61DAFB?style=flat&logo=react&logoColor=black) ![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat&logo=typescript&logoColor=white) ![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat&logo=vite&logoColor=white) |
| **Backend** | ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white) ![Django](https://img.shields.io/badge/Django-092E20?style=flat&logo=django&logoColor=white) ![DRF](https://img.shields.io/badge/DRF-FF1709?style=flat&logo=django&logoColor=white) ![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=flat&logo=langchain&logoColor=white) ![ChromaDB](https://img.shields.io/badge/ChromaDB-FF6B35?style=flat&logoColor=white) |
| **AI / 데이터** | ![OpenAI](https://img.shields.io/badge/OpenAI-412991?style=flat&logo=openai&logoColor=white) ![PubMed](https://img.shields.io/badge/PubMed-326599?style=flat&logoColor=white) ![Tavily](https://img.shields.io/badge/Tavily-000000?style=flat&logoColor=white) |
| **인프라 / 배포** | ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white) ![Airflow](https://img.shields.io/badge/Airflow-017CEE?style=flat&logo=apacheairflow&logoColor=white) ![Render](https://img.shields.io/badge/Render-46E3B7?style=flat&logo=render&logoColor=white) ![NeonDB](https://img.shields.io/badge/NeonDB-00E699?style=flat&logo=neon&logoColor=black) |




</br>
</br>


## 9. 팀원 회고

> 김주희 </br>

Docker 환경 구축 과정에서 사소한 설정 하나로 볼륨이 연결되지 않아 많은 시간을 소모했지만, 이를 통해 작은 차이가 전체 시스템에 큰 영향을 미칠 수 있음을 배우며 문제 해결 역량을 한층 키울 수 있었다.

> 김찬영 </br>

3차 개선안을 4차에서 팀과 함께 안정적으로 구현하고, Render 배포까지 성공하며 기획부터 배포까지 한 사이클을 완주한 가치 있던 프로젝트였다고 생각합니다.

> 조민서 </br>

Django 인증 서버부터 Airflow 테스트 자동화까지 구축하며 서비스 전체 흐름을 경험할 수 있었고, 3차 아이디어를 팀원들과 함께 발전시켜 배포까지 성공적으로 마무리한 프로젝트였다. 

> 최현우 </br>

프론트엔드 배포를 진행하면서 로컬 환경과 실제 배포 환경의 API 연결 방식이 다르다는 점을 직접 확인했고, 환경변수와 백엔드 URL 설정의 중요성을 체감할 수 있었다.


