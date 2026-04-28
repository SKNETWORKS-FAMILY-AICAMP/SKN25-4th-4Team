export type User = {
  id: number
  email: string
  nickname: string
}

export type AuthTokens = {
  access: string
  refresh: string
}

export type ChatSession = {
  id: number
  title: string
  created_at: string
}

export type SourceInfo = {
  title?: string
  journal?: string
  year?: string
  pmid?: string
  url?: string
  source_type?: string
}

export type Message = {
  id?: number
  role: 'user' | 'assistant'
  content: string
  has_paper_evidence?: boolean
  weak_evidence?: boolean
  paper_score?: number
  needs_web?: boolean
  paper_sources?: SourceInfo[]
  created_at?: string
}

export type AskResponse = {
  answer: string
  has_paper_evidence?: boolean
  weak_evidence?: boolean
  paper_score?: number
  needs_web?: boolean
  paper_sources?: SourceInfo[]
}

export type HealthResponse = {
  status: 'ok' | 'error'
  collections?: {
    papers?: number
    aux?: number
  }
  message?: string
}
