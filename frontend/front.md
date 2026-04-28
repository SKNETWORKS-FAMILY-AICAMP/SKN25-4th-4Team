# Frontend Handoff

## 프로젝트 흐름 확인

현재 방향은 프로젝트 주제와 맞다.

- Django 기반 백엔드가 인증, 채팅 세션, RAG 질의응답 API를 제공한다.
- React + TypeScript 프론트가 로그인 화면과 채팅 화면을 제공한다.
- LLM/RAG는 백엔드에서 실행하고, 프론트는 질문 입력과 답변 표시를 담당한다.
- CI/CD, Docker, Render 배포는 별도 담당자가 백엔드/프론트 빌드 방식을 합쳐 정리하면 된다.

필수 산출물과 연결하면 다음 흐름이다.

- 요구사항 정의서: 로그인, 회원가입, 채팅 세션, 질문/답변, 근거 표시, 서버 상태 표시
- 화면설계서: 로그인/회원가입 화면, 채팅 화면
- 개발된 웹 애플리케이션: Django API + React TypeScript UI
- 시스템 구성도: React Frontend -> Django REST API -> RAG Pipeline -> ChromaDB/LLM
- 테스트 계획 및 결과 보고서: 인증, 세션, 질문 전송, 답변 표시, 에러 처리
- 발표 자료: 문제 정의, 시스템 구조, 주요 화면, 시연 흐름, 한계/개선점

## 프론트 구조

프론트는 `frontend/`에 만든 Vite + React + TypeScript 앱이다.

- 진입점: `frontend/src/main.tsx`
- 화면/상태 관리: `frontend/src/App.tsx`
- API 호출 모듈: `frontend/src/api.ts`
- 타입 정의: `frontend/src/types.ts`
- 스타일: `frontend/src/styles.css`
- 개발 서버 설정: `frontend/vite.config.ts`

로컬 개발에서는 Vite proxy가 `/api` 요청을 `http://127.0.0.1:8000`으로 넘긴다.

## 화면 구성

### 1. 로그인/회원가입 화면

사용자는 첫 화면에서 로그인하거나 회원가입한다.

사용 API:

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `GET /api/auth/me/`
- `POST /api/auth/logout/`

프론트 처리:

- 로그인 성공 시 access/refresh JWT를 `localStorage`에 저장한다.
- 이후 API 요청에는 `Authorization: Bearer <access>` 헤더를 붙인다.
- 현재 백엔드는 회원가입 때 `username=email`로 저장하므로, 로그인 요청 시 이메일을 `username` 값으로도 보낸다.

### 2. 채팅 화면

로그인 후 채팅 화면으로 이동한다.

사용 API:

- `GET /api/chat/health/`
- `GET /api/chat/sessions/`
- `POST /api/chat/sessions/`
- `DELETE /api/chat/sessions/{id}/`
- `GET /api/chat/sessions/{id}/messages/`
- `POST /api/chat/ask/`

프론트 처리:

- 좌측에는 채팅 세션 목록을 보여준다.
- 새 채팅을 만들 수 있다.
- 질문을 보내면 사용자 메시지를 먼저 화면에 표시하고, 백엔드 응답이 오면 assistant 메시지로 교체한다.
- 답변에 논문 근거 여부, 관련도 점수, 출처가 있으면 함께 표시한다.

현재 프론트는 일반 응답 API인 `POST /api/chat/ask/`를 사용한다. 스트리밍 API인 `POST /api/chat/ask/stream/`은 백엔드에 있으나 아직 프론트에 연결하지 않았다.

## 프론트가 기대하는 API 데이터

### 회원가입 요청

```json
{
  "email": "user@example.com",
  "password": "password123",
  "nickname": "사용자"
}
```

### 로그인 요청

```json
{
  "username": "user@example.com",
  "email": "user@example.com",
  "password": "password123"
}
```

### 로그인 응답

```json
{
  "access": "JWT_ACCESS_TOKEN",
  "refresh": "JWT_REFRESH_TOKEN"
}
```

### 내 정보 응답

```json
{
  "id": 1,
  "email": "user@example.com",
  "nickname": "사용자"
}
```

### 채팅 세션 응답

```json
[
  {
    "id": 1,
    "title": "콜라겐 질문",
    "created_at": "2026-04-27T12:00:00+09:00"
  }
]
```

### 질문 요청

```json
{
  "question": "콜라겐이 피부 건강에 도움이 돼?",
  "session_id": 1
}
```

### 질문 응답

```json
{
  "answer": "답변 본문",
  "has_paper_evidence": true,
  "weak_evidence": false,
  "paper_score": 0.82,
  "paper_sources": [
    {
      "title": "논문 제목",
      "journal": "저널명",
      "year": "2024",
      "pmid": "12345678",
      "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    }
  ]
}
```

## 백엔드 팀에 확인/요청할 데이터

프론트가 정상 작동하려면 아래가 준비되어야 한다.

### 1. 인증 API

- 회원가입 API가 `email`, `password`, `nickname`을 받는지
- 로그인 API가 `username/password`인지 `email/password`인지
- 로그인 응답 필드명이 `access`, `refresh`인지
- `/api/auth/me/` 응답에 `id`, `email`, `nickname`이 있는지

### 2. 채팅 세션 API

- 세션 목록이 로그인 유저 기준으로 필터링되는지
- 새 세션 생성 시 `title`을 받을 수 있는지
- 세션 삭제 후 메시지도 함께 삭제되는지
- 메시지 목록 응답에 `role`, `content`, `created_at`이 있는지

### 3. RAG 질문 API

- `/api/chat/ask/`가 `question`, `session_id`를 받는지
- 응답에 `answer`가 항상 포함되는지
- 근거 표시용 필드가 아래 이름으로 유지되는지
  - `has_paper_evidence`
  - `weak_evidence`
  - `paper_score`
  - `paper_sources`
- 에러 시 응답 형태가 `{ "error": "..." }` 또는 `{ "detail": "..." }`인지

### 4. DB 준비

repo에는 `db.sqlite3`가 없다. `.gitignore`에 의해 DB 파일이 빠지는 것은 정상이다.

백엔드 실행 전에는 migration이 필요하다.

```bash
cd backend
python manage.py migrate
```

프론트 관점에서 필요한 DB 테이블:

- User
- ChatSession
- Message

### 5. RAG 데이터 준비

repo에는 RAG용 벡터 DB 데이터도 없다.

프론트는 `/api/chat/health/`를 호출해서 RAG 데이터 상태를 표시한다. 백엔드는 health 응답에 collection count를 내려주면 된다.

프론트가 기대하는 health 응답 예시:

```json
{
  "status": "ok",
  "collections": {
    "papers": 120,
    "aux": 30
  }
}
```

백엔드 팀에 확인할 것:

- ChromaDB 데이터 경로
- 논문 collection 이름
- 보조문서 collection 이름
- 데이터 수집/빌드 명령어
- OpenAI/NCBI/Tavily 등 필요한 API key
- health API가 데이터 없음 상태에서도 500 대신 읽을 수 있는 응답을 주는지

## 로컬 실행

프론트:

```bash
cd frontend
npm install
npm run dev
```

백엔드:

```bash
cd backend
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

프론트 접속:

```text
http://localhost:5173
```

## 테스트 관점

프론트에서 확인할 항목:

- 회원가입 성공/실패
- 로그인 성공/실패
- 로그인 후 내 정보 조회
- 새 채팅 생성
- 세션 목록 조회
- 질문 전송
- 답변 표시
- 논문 근거/점수/출처 표시
- 세션 삭제
- 백엔드 연결 실패 시 안내 메시지 표시

현재 확인한 것:

```bash
cd frontend
npm run build
```

TypeScript 빌드는 성공했다.
