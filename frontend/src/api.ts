import type { AskResponse, AuthTokens, ChatSession, HealthResponse, Message, User } from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const ACCESS_KEY = 'biorag_access_token'
const REFRESH_KEY = 'biorag_refresh_token'

export const tokenStore = {
  get access() {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY)
  },
  save(tokens: AuthTokens) {
    localStorage.setItem(ACCESS_KEY, tokens.access)
    localStorage.setItem(REFRESH_KEY, tokens.refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

async function request<T>(path: string, options: RequestInit = {}, withAuth = true): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')

  if (withAuth && tokenStore.access) {
    headers.set('Authorization', `Bearer ${tokenStore.access}`)
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  const contentType = response.headers.get('content-type') ?? ''
  const data = contentType.includes('application/json') ? await response.json() : null

  if (!response.ok) {
    const detail = data?.detail ?? data?.error ?? data?.message
    if (typeof detail === 'string') throw new Error(detail)
    if (data && typeof data === 'object') {
      const firstKey = Object.keys(data)[0]
      const firstVal = data[firstKey]
      if (Array.isArray(firstVal) && firstVal.length > 0) throw new Error(String(firstVal[0]))
    }
    throw new Error('요청 처리에 실패했습니다.')
  }

  return data as T
}

export async function register(email: string, password: string, nickname: string): Promise<User> {
  return request<User>(
    '/api/auth/register/',
    {
      method: 'POST',
      body: JSON.stringify({ email, password, nickname }),
    },
    false,
  )
}

export async function login(email: string, password: string): Promise<AuthTokens> {
  const tokens = await request<AuthTokens>(
    '/api/auth/login/',
    {
      method: 'POST',
      body: JSON.stringify({ username: email, email, password }),
    },
    false,
  )
  tokenStore.save(tokens)
  return tokens
}

export async function logout(): Promise<void> {
  const refresh = tokenStore.refresh
  if (refresh) {
    await request('/api/auth/logout/', {
      method: 'POST',
      body: JSON.stringify({ refresh }),
    })
  }
  tokenStore.clear()
}

export async function getMe(): Promise<User> {
  return request<User>('/api/auth/me/')
}

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/api/chat/health/', {}, false)
}

export async function getSessions(): Promise<ChatSession[]> {
  return request<ChatSession[]>('/api/chat/sessions/')
}

export async function createSession(title = '새 채팅'): Promise<ChatSession> {
  return request<ChatSession>('/api/chat/sessions/', {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

export async function deleteSession(id: number): Promise<void> {
  await request(`/api/chat/sessions/${id}/`, {
    method: 'DELETE',
  })
}

export async function getMessages(sessionId: number): Promise<Message[]> {
  return request<Message[]>(`/api/chat/sessions/${sessionId}/messages/`)
}

export async function ask(question: string, sessionId?: number): Promise<AskResponse> {
  return request<AskResponse>('/api/chat/ask/', {
    method: 'POST',
    body: JSON.stringify({ question, session_id: sessionId ?? null }),
  })
}
