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
  const skipNextFetch = useRef(false)
  const [authForm, setAuthForm] = useState({
    email: '',
    password: '',
    nickname: '',
  })

  const isAuthed = Boolean(user && tokenStore.access)

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
      await logout()
    } finally {
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

    const title = initialQuestion ? initialQuestion.slice(0, 28) : '새 채팅'
    const session = await createSession(title)
    setSessions((current) => [session, ...current])
    setActiveSession(session)
    return session
  }

  async function handleDeleteSession(session: ChatSession) {
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
      if (!activeSession) skipNextFetch.current = true
      const session = activeSession ?? (await handleNewSession(content))
      const result = await ask(content, session?.id)
      const assistantMessage: Message = {
        role: 'assistant',
        content: result.answer,
        has_paper_evidence: result.has_paper_evidence,
        weak_evidence: result.weak_evidence,
        paper_score: result.paper_score,
        needs_web: result.needs_web,
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
            <h1>BioRAG</h1>
            <p className="brand-lead">PubMed 논문 근거로 건강 궁금증을 쉽게 풀어드립니다.</p>
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
            <p>논문 기반의 건강 지식 서비스로, 의학적 진단은 전문가 상담을 요합니다.</p>
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
                  {message.role === 'assistant' ? (
                    <div className="report">
                      <header className="report-header">
                        <h3>BioRAG 분석 리포트</h3>
                      </header>
                      {message.has_paper_evidence !== undefined && (
                        <EvidenceMeta message={message} />
                      )}
                      <ReportBody message={message} />
                      {message.paper_sources && message.paper_sources.length > 0 && !hasCitationBlocks(message.content) && (
                        <SourceLinks sources={message.paper_sources} />
                      )}
                    </div>
                  ) : (
                    <p>{message.content}</p>
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
  const isWeak = message.has_paper_evidence && message.weak_evidence
  const isStrong = message.has_paper_evidence && !message.weak_evidence
  const label = isStrong ? '논문 근거 있음' : isWeak ? '간접 근거' : '직접 근거 없음'
  const badgeIcon = isStrong ? '◎' : isWeak ? '△' : '✕'
  const badgeClass = isStrong ? 'badge-strong' : isWeak ? 'badge-weak' : 'badge-none'

  return (
    <div className="evidence-meta">
      <div className={`evidence-badge ${badgeClass}`}>
        <span aria-hidden="true">{badgeIcon}</span>
        {label}
      </div>

      {message.paper_score !== undefined && (
        <div className="evidence-score">
          <span className="evidence-score-label">논문 관련도</span>
          <div
            className="evidence-score-bar"
            role="progressbar"
            aria-valuenow={score}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className="evidence-score-fill"
              style={{
                width: `${score}%`,
                background: isStrong ? '#2bb360' : isWeak ? '#d4a000' : '#c0392b',
              }}
            />
          </div>
          <span className="evidence-score-value">{score}%</span>
        </div>
      )}

      {message.needs_web && <span className="web-search-badge">웹검색 보조 사용</span>}
    </div>
  )
}

function ReportBody({ message }: { message: Message }) {
  const sources = message.paper_sources ?? []
  const usedSourceIndexes = new Set<number>()
  let citationIndex = 0

  return (
    <div className="report-body">
      {message.content.split(/\n{2,}/).map((paragraph, paragraphIndex) => (
        <div className="report-paragraph" key={`paragraph-${paragraphIndex}`}>
          {paragraph.split('\n').map((line, lineIndex) => {
            const parts = splitCitationBlocks(line)
            return (
              <span className="report-line" key={`line-${lineIndex}`}>
                {parts.map((part, partIndex) => {
                  if (typeof part === 'string') return <span key={`text-${partIndex}`}>{part}</span>
                  const source = findCitationSource(part.citation, sources, usedSourceIndexes) ?? sources[citationIndex]
                  citationIndex += 1
                  if (!source) return null
                  return <SourcePill key={`cite-${partIndex}`} source={source} inline />
                })}
              </span>
            )
          })}
        </div>
      ))}
    </div>
  )
}

function findCitationSource(
  citation: string,
  sources: NonNullable<Message['paper_sources']>,
  usedSourceIndexes: Set<number>,
) {
  const normalizedCitation = normalizeCitation(citation)
  if (!normalizedCitation) return undefined

  const unusedIndex = sources.findIndex((source, index) => {
    if (usedSourceIndexes.has(index)) return false
    const normalizedTitle = normalizeCitation(source.title || '')
    if (!normalizedTitle) return false
    return normalizedTitle.includes(normalizedCitation) || normalizedCitation.includes(normalizedTitle)
  })

  const index = unusedIndex >= 0
    ? unusedIndex
    : sources.findIndex((source) => {
      const normalizedTitle = normalizeCitation(source.title || '')
      return Boolean(normalizedTitle) && normalizedTitle.includes(normalizedCitation)
    })

  if (index >= 0) {
    usedSourceIndexes.add(index)
    return sources[index]
  }

  return undefined
}

function normalizeCitation(value: string) {
  return value
    .replace(/^[([ ]?출처:\s*/, '')
    .replace(/[)\]]$/, '')
    .replace(/,\s*\d{4}\s*$/, '')
    .replace(/[^\p{Letter}\p{Number}]+/gu, ' ')
    .trim()
    .toLowerCase()
}

function hasCitationBlocks(content: string) {
  return content.includes('(출처:') || content.includes('[출처:')
}

function splitCitationBlocks(line: string): Array<string | { citation: string }> {
  const parts: Array<string | { citation: string }> = []
  let cursor = 0

  while (cursor < line.length) {
    const parenStart = line.indexOf('(출처:', cursor)
    const bracketStart = line.indexOf('[출처:', cursor)
    const starts = [parenStart, bracketStart].filter((index) => index >= 0)
    if (starts.length === 0) {
      parts.push(line.slice(cursor))
      break
    }

    const start = Math.min(...starts)
    const opener = line[start]
    const closer = opener === '(' ? ')' : ']'
    if (start > cursor) parts.push(line.slice(cursor, start))

    let end = start
    let depth = 0
    while (end < line.length) {
      const char = line[end]
      if (char === opener) depth += 1
      if (char === closer) {
        depth -= 1
        if (depth === 0) break
      }
      end += 1
    }

    if (end >= line.length) {
      parts.push(line.slice(start))
      break
    }

    parts.push({ citation: line.slice(start, end + 1) })
    cursor = end + 1
  }

  return parts.filter((part) => typeof part !== 'string' || part.length > 0)
}

function SourcePill({
  source,
  fallback,
  inline = false,
}: {
  source?: NonNullable<Message['paper_sources']>[number]
  fallback?: string
  inline?: boolean
}) {
  const text = source ? formatSourceLabel(source) : fallback || '출처'
  const href = source?.url || (source?.pmid ? `https://pubmed.ncbi.nlm.nih.gov/${source.pmid}/` : '')
  const title = source?.title ? `${source.title}${source.year ? `, ${source.year}` : ''}` : text
  const className = inline ? 'source-pill inline-source' : 'source-pill'

  return href ? (
    <a href={href} target="_blank" rel="noreferrer" className={className} title={title}>
      {text}
    </a>
  ) : (
    <span className={className} title={title}>{text}</span>
  )
}

function formatSourceLabel(source: NonNullable<Message['paper_sources']>[number]) {
  return [source.journal || source.source_type || '논문', source.year].filter(Boolean).join(' ')
}

function SourceLinks({ sources }: { sources: NonNullable<Message['paper_sources']> }) {
  return (
    <div className="source-links">
      {sources.slice(0, 5).map((source, index) => {
        const key = source.url || source.pmid || source.title || `${source.journal}-${index}`
        return <SourcePill key={`${key}-${index}`} source={source} />
      })}
    </div>
  )
}

export default App
