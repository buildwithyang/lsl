import { requestJson } from '@/lib/api/client'
import type {
  GenerateMaterialSessionRequest,
  GenerateMaterialSessionResponse,
  MaterialGeneration,
} from '@/types/api'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function generateMaterialSession(payload: GenerateMaterialSessionRequest): Promise<GenerateMaterialSessionResponse> {
  const response = await requestJson<ApiResponse<GenerateMaterialSessionResponse>>('/materials/generate-session', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      source: payload.source,
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

export async function getMaterialGeneration(generationId: string): Promise<MaterialGeneration> {
  const response = await requestJson<ApiResponse<MaterialGeneration>>(`/materials/generations/${generationId}`)
  return response.data
}

export async function confirmMaterialGeneration(generationId: string): Promise<MaterialGeneration> {
  const response = await requestJson<ApiResponse<MaterialGeneration>>(`/materials/generations/${generationId}/confirm`, {
    method: 'POST',
  })
  return response.data
}

export async function cancelMaterialGeneration(generationId: string): Promise<MaterialGeneration> {
  const response = await requestJson<ApiResponse<MaterialGeneration>>(`/materials/generations/${generationId}/cancel`, {
    method: 'POST',
  })
  return response.data
}
