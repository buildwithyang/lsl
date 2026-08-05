import { ApiRequestError, requestJson } from '@/lib/api/client'
import type { TranslationResponse } from '@/types/api'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface TranslationSourceItemInput {
  source_item_key: string
  source_seq?: number | null
  speaker?: string | null
  source_text: string
}

export interface TranslationSourceParams {
  sourceType: 'transcript' | 'revision'
  sourceEntityId: string
  sessionId?: string
  sourceLanguage?: string
  targetLanguage?: string
}

export async function getTranslation(params: TranslationSourceParams): Promise<TranslationResponse> {
  const query: Record<string, string> = {
    source_type: params.sourceType,
    source_entity_id: params.sourceEntityId,
  }
  if (params.targetLanguage) {
    query.target_language = params.targetLanguage
  }
  const response = await requestJson<ApiResponse<TranslationResponse>>('/translations', {
    method: 'GET',
    query,
  })
  return response.data
}

export async function createTranslation(
  params: TranslationSourceParams & { items: TranslationSourceItemInput[]; force?: boolean }
): Promise<TranslationResponse> {
  const response = await requestJson<ApiResponse<TranslationResponse>>('/translations', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      source_type: params.sourceType,
      source_entity_id: params.sourceEntityId,
      session_id: params.sessionId,
      source_language: params.sourceLanguage,
      target_language: params.targetLanguage,
      items: params.items,
      force: params.force ?? false,
    }),
  })
  return response.data
}

export async function translateTranslationItem(
  params: TranslationSourceParams & { item: TranslationSourceItemInput }
): Promise<TranslationResponse> {
  const response = await requestJson<ApiResponse<TranslationResponse>>('/translations/items/translate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      source_type: params.sourceType,
      source_entity_id: params.sourceEntityId,
      session_id: params.sessionId,
      source_language: params.sourceLanguage,
      target_language: params.targetLanguage,
      item: params.item,
    }),
  })
  return response.data
}

export function isMissingTranslationError(error: unknown): boolean {
  return error instanceof ApiRequestError && error.status === 404
}
