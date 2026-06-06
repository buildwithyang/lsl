import { requestJson } from '@/lib/api/client'
import type {
  CreatePodcastSessionRequest,
  ExtractMaterialRequest,
  ExtractedMaterialContent,
  GenerateScriptSessionResponse,
} from '@/types/api'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function extractMaterial(payload: ExtractMaterialRequest): Promise<ExtractedMaterialContent> {
  const response = await requestJson<ApiResponse<ExtractedMaterialContent>>('/materials/extract', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ source: payload.source }),
  })
  return response.data
}

export async function createPodcastSession(payload: CreatePodcastSessionRequest): Promise<GenerateScriptSessionResponse> {
  const response = await requestJson<ApiResponse<GenerateScriptSessionResponse>>('/materials/create-session', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      source: payload.source,
      extracted_title: payload.extractedTitle ?? null,
      extracted_text: payload.extractedText,
      title: payload.title ?? null,
      description: payload.description ?? null,
      target_language: payload.targetLanguage,
      cue_language: payload.cueLanguage ?? null,
      prompt: payload.prompt ?? null,
      turn_count: payload.turnCount,
      speaker_count: payload.speakerCount,
      difficulty: payload.difficulty,
      cue_style: payload.cueStyle,
      must_include: payload.mustInclude,
    }),
  })
  return response.data
}
