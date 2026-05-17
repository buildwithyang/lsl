export interface UploadUrlRequest {
  category: string
  entityId: string
  filename: string
  contentType: string
}

export interface UploadUrlResponse {
  object_key: string
  upload_url: string
  asset_url: string
}

export interface CompleteUploadRequest {
  objectKey: string
  category?: string
  entityId?: string
  filename?: string
  contentType?: string
  fileSize?: number
  etag?: string
}

export interface CompleteUploadResponse {
  object_key: string
  asset_url: string
  status: string
}

export interface AssetListItem {
  object_key: string
  category: string
  entity_id: string
  filename?: string | null
  content_type?: string | null
  file_size?: number | null
  etag?: string | null
  upload_status: number
  created_at: string
  asset_url: string
}

export interface AssetListResponse {
  items: AssetListItem[]
}

export interface JobItem {
  job_id: string
  job_type: string
  status: number
  status_name: string
  entity_type?: string | null
  entity_id?: string | null
  progress: number
  attempts: number
  error_code?: string | null
  error_message?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface TranscriptItemResponse {
  transcript_id: string
  source_type: string
  source_entity_id?: string | null
  duration_ms?: number | null
  duration_sec?: number | null
  status: number
  status_name: string
  language?: string | null
  error_code?: string | null
  error_message?: string | null
  created_at: string
  updated_at: string
}

export interface CreateAsrRecognitionRequest {
  objectKey: string
  audioUrl: string
  targetLanguage?: string
}

export interface AsrRecognitionResponse {
  recognition_id: string
  transcript_id: string
  job_id?: string | null
  object_key: string
  audio_url?: string | null
  target_language?: string | null
  provider?: string | null
  status: number
  status_name: string
  error_code?: string | null
  error_message?: string | null
  created_at: string
  updated_at: string
}

export interface CreateAsrRecognitionResponse {
  recognition: AsrRecognitionResponse
  transcript: TranscriptItemResponse
  job: JobItem
}

export interface SessionEntity {
  session_id: string
  title: string
  description?: string | null
  target_language?: string | null
  f_type: number
  asset_object_key?: string | null
  current_transcript_id?: string | null
  created_at: string
  updated_at: string
}

export interface SessionItem {
  session: SessionEntity
  asset?: AssetListItem | null
  transcript?: TranscriptItemResponse | null
}

export interface SessionListResponse {
  items: SessionItem[]
}

export interface CreateSessionRequest {
  title: string
  description?: string
  targetLanguage?: string
  fType?: 1 | 2
  assetObjectKey?: string
  currentTranscriptId?: string
}

export interface UpdateSessionRequest {
  title?: string
  description?: string | null
  targetLanguage?: string | null
  fType?: 1 | 2
  assetObjectKey?: string | null
  currentTranscriptId?: string | null
}

export interface GenerateScriptSessionRequest {
  title: string
  description?: string
  targetLanguage?: string
  cueLanguage?: string
  prompt: string
  turnCount?: number
  speakerCount?: number
  difficulty?: string
  cueStyle?: string
  mustInclude?: string[]
}

export interface GenerateScriptSessionResponse {
  session: SessionItem
  generation: ScriptGenerationResponse
  job: JobItem
  revision?: RevisionResponse | null
}

export interface ScriptGenerationResponse {
  generation_id: string
  session_id: string
  transcript_id?: string | null
  job_id?: string | null
  provider: string
  title: string
  description?: string | null
  target_language?: string | null
  cue_language?: string | null
  prompt: string
  turn_count: number
  speaker_count: number
  difficulty?: string | null
  cue_style?: string | null
  must_include: string[]
  plan_sections: ScriptGenerationPlanSectionResponse[]
  raw_result?: ScriptGenerationRawResult | null
  status: number
  status_name: string
  error_code?: string | null
  error_message?: string | null
  created_at: string
  updated_at: string
}

export interface ScriptGenerationPlanSectionResponse {
  section_index: number
  title: string
  summary: string
  target_turn_count: number
}

export interface ScriptGenerationRawResult {
  stage?: string
  [key: string]: unknown
}

export interface ScriptGenerationPreviewItemResponse {
  seq: number
  speaker: string
  cue: string
  text: string
}

export interface ScriptGenerationPreviewResponse {
  generation: ScriptGenerationResponse
  items: ScriptGenerationPreviewItemResponse[]
}

export interface CreateRevisionRequest {
  sessionId: string
  userPrompt?: string
  force?: boolean
  cueLanguage?: string
}

export interface UpdateRevisionItemRequest {
  draftText?: string | null
}

export interface RevisionItemResponse {
  item_id: string
  revision_id: string
  transcript_id: string
  source_seq_start: number
  source_seq_end: number
  source_seq_count: number
  source_seqs: number[]
  speaker?: string | null
  start_time: number
  end_time: number
  original_text: string
  suggested_text: string
  draft_text?: string | null
  score: number
  issue_tags: string
  explanations: string
  created_at: string
  updated_at: string
}

export interface RevisionPlanSectionResponse {
  section_index: number
  title: string
  summary: string
  start_seq: number
  end_seq: number
  target_utterance_count: number
}

export interface RevisionResponse {
  revision_id: string
  session_id: string
  transcript_id: string
  job_id?: string | null
  user_prompt?: string | null
  cue_language?: string | null
  status: number
  status_name: string
  error_code?: string | null
  error_message?: string | null
  item_count: number
  plan_sections: RevisionPlanSectionResponse[]
  created_at: string
  updated_at: string
  items: RevisionItemResponse[]
}

export interface RevisionPreviewResponse {
  revision: RevisionResponse
  items: RevisionItemResponse[]
}

export interface TranscriptUtteranceResponse {
  seq: number
  text: string
  speaker?: string | null
  start_time: number
  end_time: number
  additions: Record<string, unknown>
}

export interface TranscriptData {
  transcript_id: string
  source_type: string
  source_entity_id?: string | null
  status: number
  status_name: string
  duration_ms?: number | null
  duration_sec?: number | null
  full_text?: string | null
  utterances: TranscriptUtteranceResponse[]
  raw_result?: Record<string, unknown> | null
}

export interface TtsSpeakerMapping {
  conversation_speaker: string
  provider_speaker_id: string
}

export interface TtsSpeakerItem {
  speaker_id: string
  name: string
  provider_name?: string | null
  display_name?: string | null
  language?: string | null
  gender?: string | null
  style?: string | null
  description?: string | null
  i18n?: Record<string, {
    name?: string
    language?: string
    style?: string
    description?: string
  }>
  avatar?: {
    type?: string
    key?: string
    color?: string
    initials?: string
    url?: string | null
  }
  traits?: Record<string, unknown>
}

export interface TtsSpeakerListResponse {
  items: TtsSpeakerItem[]
}

export interface TtsSettingsResponse {
  session_id: string
  format: string
  emotion_scale: number
  speech_rate: number
  loudness_rate: number
  speaker_mappings: TtsSpeakerMapping[]
}

export interface UpdateTtsSettingsRequest {
  sessionId: string
  format: string
  emotionScale: number
  speechRate: number
  loudnessRate: number
  speakerMappings: TtsSpeakerMapping[]
}

export interface CreateTtsSynthesisRequest {
  sessionId: string
  force?: boolean
}

export interface TtsSynthesisItemResponse {
  item_id: string
  conversation_speaker?: string | null
  provider_speaker_id: string
  content: string
  plain_text: string
  cue_texts: string[]
  content_hash: string
  start_time_ms?: number | null
  end_time_ms?: number | null
  duration_ms?: number | null
  status: number
  status_name: string
}

export interface TtsSynthesisResponse {
  synthesis_id: string
  session_id: string
  provider: string
  full_asset_url?: string | null
  full_duration_ms?: number | null
  item_count: number
  completed_item_count: number
  failed_item_count: number
  status: number
  status_name: string
  error_code?: string | null
  error_message?: string | null
  created_at: string
  updated_at: string
  items: TtsSynthesisItemResponse[]
}

export interface CreateTtsSynthesisResponse {
  synthesis: TtsSynthesisResponse
  job?: JobItem | null
}

export interface TranslationItemResponse {
  item_id: string
  translation_id: string
  source_item_key: string
  source_seq?: number | null
  speaker?: string | null
  start_time?: number | null
  end_time?: number | null
  source_text: string
  source_text_hash: string
  translated_text?: string | null
  status: number
  status_name: string
  error_code?: string | null
  error_message?: string | null
  created_at: string
  updated_at: string
}

export interface GenerateMaterialSessionRequest {
  source: { type: 'webpage'; url: string };
  title?: string | null;
  description?: string | null;
  targetLanguage: string;
  cueLanguage?: string | null;
  prompt?: string | null;
  turnCount?: number;
  speakerCount?: number;
  difficulty?: string | null;
  cueStyle?: string | null;
  mustInclude?: string[];
}

export interface MaterialGeneration {
  generation_id: string;
  session_id: string;
  source_type: string;
  source_payload: Record<string, unknown>;
  request_payload: Record<string, unknown>;
  extracted_title: string | null;
  extracted_text: string | null;
  extracted_meta: Record<string, unknown>;
  script_generation_id: string | null;
  job_id: string | null;
  status: number;
  status_name: string;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface GenerateMaterialSessionResponse {
  session: SessionItem;
  material_generation: MaterialGeneration;
  job: JobItem;
}

export interface TranslationResponse {
  translation_id: string
  session_id?: string | null
  source_type: string
  source_entity_id: string
  source_language?: string | null
  target_language: string
  job_id?: string | null
  provider: string
  model?: string | null
  status: number
  status_name: string
  item_count: number
  completed_count: number
  stale_count: number
  error_code?: string | null
  error_message?: string | null
  created_at: string
  updated_at: string
  items: TranslationItemResponse[]
}
