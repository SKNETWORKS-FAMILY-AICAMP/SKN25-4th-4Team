import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  ask,
  createSession,
  deleteSession,
  getHealth,
  getMe,
  getMessages,
  getSessions,
  login,
  logout,
  register,
  tokenStore,
} from './api'
import type { ChatSession, HealthResponse, Message, User } from './types'

type AuthMode = 'login' | 'register'

const examples = [
  '마운자로의 효과를 논문 근거로 알려줘',
  '콜라겐이 피부 건강에 도움이 돼?',
  '오메가3는 매일 먹어도 괜찮아?',
]

// ===== Preview-only block: remove this whole block when backend auth/RAG is ready. =====
const previewUser: User = {
  id: 0,
  email: 'preview@biorag.local',
  nickname: '프론트 미리보기',
}

const previewSession: ChatSession = {
  id: 0,
  title: '화면 미리보기',
  created_at: new Date().toISOString(),
}

const previewMessages: Message[] = [
  {
    role: 'user',
    content: '콜라겐이 피부 건강에 도움이 돼?',
  },
  {
    role: 'assistant',
    content:
      '일부 연구에서는 콜라겐 섭취가 피부 보습과 탄력 지표 개선에 도움을 줄 수 있다고 보고합니다. 다만 제품 성분, 섭취 기간, 개인 건강 상태에 따라 차이가 있으므로 치료 목적보다는 보조적인 건강 정보로 보는 것이 좋습니다.',
    has_paper_evidence: true,
    weak_evidence: false,
    paper_score: 0.82,
    paper_sources: [
      {
        journal: 'Nutrients',
        year: '2024',
        url: 'https://pubmed.ncbi.nlm.nih.gov/',
      },
    ],
  },
]

function createPreviewSession(title = '새 채팅 미리보기'): ChatSession {
  return {
    ...previewSession,
    title,
    created_at: new Date().toISOString(),
  }
}

function createPreviewAnswer(): Message {
  return {
    ...previewMessages[1],
    content:
      '미리보기 모드에서는 실제 RAG API를 호출하지 않습니다. 백엔드가 준비되면 같은 화면에서 질문을 보내고 논문 근거, 관련도, 출처를 실제 응답으로 확인할 수 있습니다.',
  }
}
// ===== End preview-only block. =====

function App() {
  const [authMode, setAuthMode] = useState<AuthMode>('login')
  const [user, setUser] = useState<User | null>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [notice, setNotice] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isPreview, setIsPreview] = useState(false)
  const skipNextFetch = useRef(false)
  const [authForm, setAuthForm] = useState({
    email: '',
    password: '',
    nickname: '',
  })

  const isAuthed = Boolean(user && (tokenStore.access || isPreview))

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((error) => setHealth({ status: 'error', message: error.message }))

    if (tokenStore.access) {
      getMe()
        .then((me) => {
          setUser(me)
          return refreshSessions()
        })
        .catch(() => tokenStore.clear())
    }
  }, [])

  useEffect(() => {
    if (!activeSession) {
      setMessages([])
      return
    }
    if (skipNextFetch.current) {
      skipNextFetch.current = false
      return
    }
    getMessages(activeSession.id)
      .then(setMessages)
      .catch((error) => setNotice(error.message))
  }, [activeSession])

  const evidenceSummary = useMemo(() => {
    const papers = health?.collections?.papers ?? 0
    const aux = health?.collections?.aux ?? 0
    if (health?.status === 'ok') {
      return `논문 ${papers.toLocaleString()}개 · 보조문서 ${aux.toLocaleString()}개`
    }
    return health?.message || '백엔드 연결 대기 중'
  }, [health])

  // Preview-only handler: remove with the preview-only block above.
  function handlePreview() {
    setIsPreview(true)
    setUser(previewUser)
    setHealth({ status: 'ok', collections: { papers: 120, aux: 30 } })
    setSessions([previewSession])
    setActiveSession(previewSession)
    setMessages(previewMessages)
    setNotice('')
  }

  async function refreshSessions() {
    const nextSessions = await getSessions()
    setSessions(nextSessions)
    setActiveSession((current) => current ?? nextSessions[0] ?? null)
  }

  async function handleAuthSubmit(event: FormEvent) {
    event.preventDefault()
    setNotice('')
    setIsSubmitting(true)

    try {
      if (authMode === 'register') {
        await register(authForm.email, authForm.password, authForm.nickname)
        setAuthMode('login')
        setAuthForm({ email: authForm.email, password: '', nickname: '' })
        setNotice('회원가입이 완료됐습니다. 로그인해주세요.')
        return
      }
      await login(authForm.email, authForm.password)
      const me = await getMe()
      setUser(me)
      await refreshSessions()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '인증 요청에 실패했습니다.')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleLogout() {
    try {
      if (!isPreview) {
        await logout()
      }
    } finally {
      setIsPreview(false)
      setUser(null)
      setSessions([])
      setActiveSession(null)
      setMessages([])
    }
  }

  async function handleNewSession(initialQuestion?: string) {
    if (!isAuthed) {
      setNotice('로그인 후 새 채팅을 만들 수 있습니다.')
      return null
    }

    if (isPreview) {
      const session = createPreviewSession(initialQuestion ? initialQuestion.slice(0, 28) : undefined)
      setSessions((current) => [session, ...current])
      setActiveSession(session)
      setMessages([])
      return session
    }

    const title = initialQuestion ? initialQuestion.slice(0, 28) : '새 채팅'
    const session = await createSession(title)
    setSessions((current) => [session, ...current])
    setActiveSession(session)
    return session
  }

  async function handleDeleteSession(session: ChatSession) {
    if (isPreview) {
      setSessions((current) => current.filter((item) => item.id !== session.id))
      setActiveSession(null)
      setMessages([])
      return
    }

    await deleteSession(session.id)
    const nextSessions = sessions.filter((item) => item.id !== session.id)
    setSessions(nextSessions)
    if (activeSession?.id === session.id) {
      setActiveSession(nextSessions[0] ?? null)
    }
  }

  async function handleAsk(event?: FormEvent, preset?: string) {
    event?.preventDefault()
    const content = (preset ?? question).trim()
    if (!content || isSending) return
    if (!isAuthed) {
      setNotice('로그인 후 질문할 수 있습니다.')
      return
    }

    setNotice('')
    setQuestion('')
    setIsSending(true)

    const optimisticUserMessage: Message = { role: 'user', content }
    const loadingMessage: Message = { role: 'assistant', content: '논문과 보조문서를 확인하고 있어요...' }
    setMessages((current) => [...current, optimisticUserMessage, loadingMessage])

    try {
      if (isPreview) {
        const assistantMessage = createPreviewAnswer()
        window.setTimeout(() => {
          setMessages((current) => [...current.slice(0, -1), assistantMessage])
          setIsSending(false)
        }, 450)
        return
      }

      if (!activeSession) skipNextFetch.current = true
      const session = activeSession ?? (await handleNewSession(content))
      const result = await ask(content, session?.id)
      const assistantMessage: Message = {
        role: 'assistant',
        content: result.answer,
        has_paper_evidence: result.has_paper_evidence,
        weak_evidence: result.weak_evidence,
        paper_score: result.paper_score,
        paper_sources: result.paper_sources,
      }
      setMessages((current) => [...current.slice(0, -1), assistantMessage])
      await refreshSessions()
    } catch (error) {
      const message = error instanceof Error ? error.message : '질문 처리에 실패했습니다.'
      setMessages((current) => [...current.slice(0, -1), { role: 'assistant', content: message }])
    } finally {
      setIsSending(false)
    }
  }

  if (!isAuthed) {
    return (
      <main className="auth-screen">
        <section className="auth-panel" aria-label="BioRAG 로그인">
          <div className="brand-lockup">
            <span className="brand-mark">BioRAG</span>
            <h1>논문 기반 건강 팩트체커</h1>
            <p>질문을 보내면 PubMed와 보조 문서를 바탕으로 근거 수준을 정리합니다.</p>
          </div>

          <form className="auth-form" onSubmit={handleAuthSubmit}>
            <div className="segmented-control" role="tablist" aria-label="인증 방식">
              <button
                type="button"
                className={authMode === 'login' ? 'active' : ''}
                onClick={() => setAuthMode('login')}
              >
                로그인
              </button>
              <button
                type="button"
                className={authMode === 'register' ? 'active' : ''}
                onClick={() => setAuthMode('register')}
              >
                회원가입
              </button>
            </div>

            <label>
              이메일
              <input
                type="email"
                value={authForm.email}
                onChange={(event) => setAuthForm({ ...authForm, email: event.target.value })}
                placeholder="name@example.com"
                required
              />
            </label>

            {authMode === 'register' && (
              <label>
                닉네임
                <input
                  type="text"
                  value={authForm.nickname}
                  onChange={(event) => setAuthForm({ ...authForm, nickname: event.target.value })}
                  placeholder="화면에 표시할 이름"
                  required
                />
              </label>
            )}

            <label>
              비밀번호
              <input
                type="password"
                value={authForm.password}
                onChange={(event) => setAuthForm({ ...authForm, password: event.target.value })}
                placeholder="8자 이상"
                minLength={8}
                required
              />
            </label>

            {notice && <p className="notice">{notice}</p>}

            <button className="primary-button" type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? authMode === 'login' ? '로그인 중...' : '회원가입 중...'
                : authMode === 'login' ? '로그인' : '가입하고 시작'}
            </button>

            {/* Preview-only button: remove after backend auth is usable. */}
            {import.meta.env.DEV && (
              <button className="preview-button" type="button" onClick={handlePreview}>
                채팅 화면 미리보기
              </button>
            )}
          </form>
        </section>
      </main>
    )
  }

  const authedUser = user!

  return (
    <main className="chat-shell">
      <aside className="sidebar" aria-label="채팅 세션">
        <div className="sidebar-header">
          <span className="brand-mark">BioRAG</span>
          <button className="ghost-button" type="button" onClick={() => { setActiveSession(null); setMessages([]); setNotice('') }}>
            새 채팅
          </button>
        </div>

        <div className={`health-card ${health?.status === 'ok' ? 'ok' : 'error'}`}>
          <strong>{health?.status === 'ok' ? '서버 연결됨' : '연결 확인 필요'}</strong>
          <span>{evidenceSummary}</span>
        </div>

        <nav className="session-list">
          {sessions.map((session) => (
            <button
              key={session.id}
              className={activeSession?.id === session.id ? 'session-item active' : 'session-item'}
              type="button"
              onClick={() => setActiveSession(session)}
            >
              <span>{session.title}</span>
              <small>{new Date(session.created_at).toLocaleDateString('ko-KR')}</small>
              <span
                className="delete-session"
                role="button"
                tabIndex={0}
                onClick={(event) => {
                  event.stopPropagation()
                  void handleDeleteSession(session)
                }}
              >
                삭제
              </span>
            </button>
          ))}
        </nav>

        <div className="profile-strip">
          <div>
            <strong>{authedUser.nickname || authedUser.email}</strong>
            <span>{authedUser.email}</span>
          </div>
          <button className="text-button" type="button" onClick={() => void handleLogout()}>
            로그아웃
          </button>
        </div>
      </aside>

      <section className="conversation" aria-label="BioRAG 채팅">
        <header className="conversation-header">
          <div>
            <h1>BioRAG</h1>
            <p>의학적 판단은 전문가 상담을 대신하지 않습니다.</p>
          </div>
        </header>

        {messages.length === 0 ? (
          <div className="empty-state">
            <h2>궁금한 건강 정보를 근거와 함께 확인하세요.</h2>
            <div className="example-grid">
              {examples.map((example) => (
                <button key={example} type="button" onClick={() => void handleAsk(undefined, example)}>
                  {example}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="message-list">
            {messages.map((message, index) => (
              <article key={`${message.role}-${index}`} className={`message ${message.role}`}>
                <div className="message-bubble">
                  <p>{message.content}</p>
                  {message.role === 'assistant' && message.has_paper_evidence !== undefined && (
                    <EvidenceMeta message={message} />
                  )}
                </div>
              </article>
            ))}
          </div>
        )}

        {notice && <p className="toast">{notice}</p>}

        <form className="composer" onSubmit={handleAsk}>
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void handleAsk()
              }
            }}
            placeholder="건강 정보나 영양제, 치료제에 대해 질문해보세요."
            rows={1}
          />
          <button className="primary-button" type="submit" disabled={isSending || !question.trim()}>
            {isSending ? '분석 중' : '전송'}
          </button>
        </form>
      </section>
    </main>
  )
}

function EvidenceMeta({ message }: { message: Message }) {
  const score = Math.round((message.paper_score ?? 0) * 100)
  const label = message.has_paper_evidence
    ? message.weak_evidence
      ? '간접 근거'
      : '논문 근거 있음'
    : '직접 근거 없음'

  return (
    <div className="evidence-meta">
      <span>{label}</span>
      {message.paper_score !== undefined && <span>관련도 {score}%</span>}
      {message.paper_sources?.slice(0, 3).map((source, index) => {
        const text = [source.journal || source.source_type || '출처', source.year].filter(Boolean).join(' ')
        const href = source.url || (source.pmid ? `https://pubmed.ncbi.nlm.nih.gov/${source.pmid}/` : '')
        return href ? (
          <a key={`${href}-${index}`} href={href} target="_blank" rel="noreferrer">
            {text}
          </a>
        ) : (
          <span key={`${text}-${index}`}>{text}</span>
        )
      })}
    </div>
  )
}

export default App
