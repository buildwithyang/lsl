import { requestJson } from '@/lib/api/client'
import type { CreateSessionRequest, SessionItem, SessionListResponse, UpdateSessionRequest } from '@/types/api'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

interface ListSessionsParams {
  limit?: number
  offset?: number
  query?: string
  status?: number
}

export async function createSession(payload: CreateSessionRequest): Promise<SessionItem> {
  const response = await requestJson<ApiResponse<SessionItem>>('/sessions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      title: payload.title,
      description: payload.description,
      target_language: payload.targetLanguage,
      f_type: payload.fType,
      asset_object_key: payload.assetObjectKey,
      current_transcript_id: payload.currentTranscriptId,
    }),
  })

  return response.data
}

export async function getSession(sessionId: string): Promise<SessionItem> {
  const response = await requestJson<ApiResponse<SessionItem>>(`/sessions/${sessionId}`, {
    method: 'GET',
  })

  return response.data
}

export async function updateSession(sessionId: string, payload: UpdateSessionRequest): Promise<SessionItem> {
  const response = await requestJson<ApiResponse<SessionItem>>(`/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      title: payload.title,
      description: payload.description,
      target_language: payload.targetLanguage,
      f_type: payload.fType,
      asset_object_key: payload.assetObjectKey,
      current_transcript_id: payload.currentTranscriptId,
    }),
  })

  return response.data
}

export async function deleteSession(sessionId: string): Promise<void> {
  await requestJson<ApiResponse<{ session_id: string; deleted: boolean }>>(`/sessions/${sessionId}`, {
    method: 'DELETE',
  })
}

export async function listSessions({
  limit = 20,
  offset = 0,
  query,
  status,
}: ListSessionsParams = {}): Promise<SessionItem[]> {
  const safeLimit = Math.min(Math.max(1, limit), 100)
  const safeOffset = Math.max(0, offset)

  const queryParams: Record<string, string> = {
    limit: String(safeLimit),
    offset: String(safeOffset),
  }

  if (query && query.trim()) {
    queryParams.query = query.trim()
  }

  if (typeof status === 'number') {
    queryParams.status = String(status)
  }

  const response = await requestJson<ApiResponse<SessionListResponse>>('/sessions', {
    method: 'GET',
    query: queryParams,
  })

  return response.data.items
}
