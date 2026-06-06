-- LSL database bootstrap schema.
-- Naming rules:
-- - Tables and indexes use the owning module as prefix, for example job_jobs.
-- - Columns that may collide with SQL or programming-language keywords use x_ prefix.
-- - JSON payload columns are stored as TEXT for SQLite/PostgreSQL portability.

-- Create the default PostgreSQL schema used by the application.
CREATE SCHEMA IF NOT EXISTS public;

-- Shared trigger function for tables that maintain updated_at.
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Auth module
-- Stores users created from Casdoor OAuth/OIDC login.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.auth_users (
    user_id          VARCHAR(32) PRIMARY KEY,                     -- Internal user id, uuid hex.
    provider         VARCHAR(32) NOT NULL,                         -- OAuth provider key, currently casdoor.
    provider_subject VARCHAR(255) NOT NULL,                        -- Stable subject from provider claims.
    username         VARCHAR(128),                                 -- Provider username.
    display_name     VARCHAR(255),                                 -- Display name.
    email            VARCHAR(255),                                 -- Email address if provided.
    avatar_url       VARCHAR(1024),                                -- Avatar URL if provided.
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_users_provider_subject
    ON public.auth_users (provider, provider_subject);

CREATE INDEX IF NOT EXISTS idx_auth_users_email
    ON public.auth_users (email);

-- ---------------------------------------------------------------------------
-- Asset module
-- Stores object-storage metadata for uploaded or generated files.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.asset_assets (
    id                BIGSERIAL PRIMARY KEY,                      -- Internal auto-increment row id.
    object_key        TEXT NOT NULL UNIQUE,                       -- Stable object-storage key.
    category          VARCHAR(64) NOT NULL,                       -- Business category, for example audio or tts.
    entity_id         VARCHAR(128) NOT NULL,                      -- Owning business entity id.
    filename          VARCHAR(255),                               -- Original or generated filename.
    content_type      VARCHAR(128),                               -- MIME type.
    file_size         BIGINT,                                     -- File size in bytes.
    etag              VARCHAR(128),                               -- Storage-provider ETag when available.
    storage_provider  VARCHAR(32) NOT NULL,                       -- Storage backend, for example fake or oss.
    upload_status     SMALLINT NOT NULL DEFAULT 0,                -- Upload lifecycle status.
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

-- Query recent assets by business owner.
CREATE INDEX IF NOT EXISTS idx_asset_assets_category_entity_created_at
    ON public.asset_assets (category, entity_id, created_at DESC);

-- Asset list pagination.
CREATE INDEX IF NOT EXISTS idx_asset_assets_created_at
    ON public.asset_assets (created_at DESC);

-- ---------------------------------------------------------------------------
-- Job module
-- Generic asynchronous lifecycle table. Business results stay in owning modules.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.job_jobs (
    job_id        VARCHAR(32) PRIMARY KEY,                         -- Job id, uuid hex.
    job_type      VARCHAR(64) NOT NULL,                            -- Handler key, for example asr_recognition.
    x_status      SMALLINT NOT NULL DEFAULT 0,                     -- 0 queued, 1 running, 2 completed, 3 failed, 4 canceled.
    entity_type   VARCHAR(64),                                     -- Owning domain entity type.
    entity_id     VARCHAR(128),                                    -- Owning domain entity id.
    priority      INTEGER NOT NULL DEFAULT 0,                      -- Higher priority jobs are claimed first.
    progress      INTEGER NOT NULL DEFAULT 0,                      -- Approximate progress from 0 to 100.
    attempts      INTEGER NOT NULL DEFAULT 0,                      -- Number of claim/run attempts.
    max_attempts  INTEGER NOT NULL DEFAULT 3,                      -- Maximum allowed attempts.
    payload_json  TEXT NOT NULL DEFAULT '{}',                      -- Handler input payload JSON.
    result_json   TEXT,                                           -- Lightweight handler result JSON.
    error_code    VARCHAR(64),                                    -- Stable error code when failed/canceled.
    error_message TEXT,                                           -- Human-readable error detail.
    locked_by     VARCHAR(128),                                   -- Worker id that claimed the job.
    locked_until  TIMESTAMPTZ,                                    -- Lock expiration timestamp.
    next_run_at   TIMESTAMPTZ,                                    -- Next scheduled run time; NULL means runnable now.
    started_at    TIMESTAMPTZ,                                    -- First started timestamp.
    finished_at   TIMESTAMPTZ,                                    -- Terminal timestamp.
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

-- Claim queued/running jobs by due time.
CREATE INDEX IF NOT EXISTS idx_job_jobs_status_next_run_at
    ON public.job_jobs (x_status, next_run_at);

-- Filter due jobs by handler type.
CREATE INDEX IF NOT EXISTS idx_job_jobs_type_status_next_run_at
    ON public.job_jobs (job_type, x_status, next_run_at);

-- Lookup jobs by owning business entity.
CREATE INDEX IF NOT EXISTS idx_job_jobs_entity
    ON public.job_jobs (entity_type, entity_id);

-- Job list pagination.
CREATE INDEX IF NOT EXISTS idx_job_jobs_created_at
    ON public.job_jobs (created_at);

-- ---------------------------------------------------------------------------
-- Transcript module
-- Unified utterance stream produced by ASR, AI script generation, manual input,
-- or imports.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.transcript_transcripts (
    transcript_id    VARCHAR(32) PRIMARY KEY,                     -- Transcript id, uuid hex.
    source_type      VARCHAR(32) NOT NULL,                        -- asr, ai_script, manual, or import.
    source_entity_id VARCHAR(128),                                -- Source module entity id.
    x_language       VARCHAR(16),                                 -- Language tag, for example en-US.
    duration_ms      INTEGER,                                     -- Total duration in milliseconds.
    full_text        TEXT,                                        -- Joined text for quick display/search.
    raw_result_json  TEXT,                                        -- Provider/raw generation result JSON.
    x_status         SMALLINT NOT NULL DEFAULT 0,                 -- 0 pending, 1 completed, 2 failed.
    error_code       VARCHAR(64),                                 -- Stable failure code.
    error_message    TEXT,                                        -- Failure detail.
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

-- Find transcript by source module entity.
CREATE INDEX IF NOT EXISTS idx_transcript_transcripts_source
    ON public.transcript_transcripts (source_type, source_entity_id);

-- Transcript list and pending/failed scans.
CREATE INDEX IF NOT EXISTS idx_transcript_transcripts_status_created_at
    ON public.transcript_transcripts (x_status, created_at);

CREATE TABLE IF NOT EXISTS public.transcript_utterances (
    id               BIGSERIAL PRIMARY KEY,                       -- Internal auto-increment row id.
    transcript_id    VARCHAR(32) NOT NULL,                        -- Owning transcript id.
    seq              INTEGER NOT NULL,                            -- Ordered utterance sequence.
    x_text           TEXT NOT NULL,                               -- Utterance text.
    speaker          VARCHAR(64),                                 -- Speaker label from ASR/script/manual source.
    start_time       INTEGER NOT NULL,                            -- Start time in milliseconds.
    end_time         INTEGER NOT NULL,                            -- End time in milliseconds.
    additions_json   TEXT NOT NULL DEFAULT '{}',                  -- Extra source-specific metadata JSON.
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP -- Creation timestamp.
);

-- Load utterances in transcript order.
CREATE INDEX IF NOT EXISTS idx_transcript_utterances_transcript_id
    ON public.transcript_utterances (transcript_id, seq);

-- One utterance per transcript sequence number.
CREATE UNIQUE INDEX IF NOT EXISTS uq_transcript_utterance_transcript_seq
    ON public.transcript_utterances (transcript_id, seq);

-- ---------------------------------------------------------------------------
-- ASR module
-- Tracks provider recognition process. Standard output is written to transcript.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.asr_recognitions (
    recognition_id            VARCHAR(32) PRIMARY KEY,             -- Recognition id, uuid hex.
    transcript_id             VARCHAR(32) NOT NULL,                -- Target transcript id.
    job_id                    VARCHAR(32),                         -- Async job id.
    object_key                TEXT NOT NULL,                       -- Uploaded audio object key.
    audio_url                 TEXT NOT NULL,                       -- Provider-readable audio URL.
    target_language           VARCHAR(16),                         -- ASR target language tag.
    x_provider                VARCHAR(32) NOT NULL,                -- ASR provider name.
    x_status                  SMALLINT NOT NULL DEFAULT 0,         -- 0 pending, 1 submitted, 2 processing, 3 completed, 4 failed.
    x_provider_request_id     VARCHAR(128),                        -- Provider request id.
    x_provider_resource_id    VARCHAR(128),                        -- Provider resource id if returned.
    x_tt_logid                VARCHAR(255),                        -- Volc/ByteDance request log id.
    x_provider_status_code    VARCHAR(32),                         -- Provider status code.
    x_provider_message        TEXT,                                -- Provider status message.
    error_code                VARCHAR(64),                         -- Stable failure code.
    error_message             TEXT,                                -- Failure detail.
    poll_count                INTEGER NOT NULL DEFAULT 0,          -- Number of provider query polls.
    last_polled_at            TIMESTAMPTZ,                         -- Last provider query timestamp.
    next_poll_at              TIMESTAMPTZ,                         -- Next provider query timestamp.
    created_at                TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

-- Find recognition process by transcript.
CREATE INDEX IF NOT EXISTS idx_asr_recognitions_transcript_id
    ON public.asr_recognitions (transcript_id);

-- List recognitions by state.
CREATE INDEX IF NOT EXISTS idx_asr_recognitions_status_created_at
    ON public.asr_recognitions (x_status, created_at);

-- Lookup recognition by uploaded object.
CREATE INDEX IF NOT EXISTS idx_asr_recognitions_object_key
    ON public.asr_recognitions (object_key);

-- ---------------------------------------------------------------------------
-- Session module
-- User-facing learning session. It references current transcript and asset.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.session_sessions (
    session_id             VARCHAR(32) PRIMARY KEY,                -- Session id, uuid hex.
    title                  VARCHAR(200) NOT NULL,                  -- Display title.
    x_description          TEXT,                                   -- Optional description.
    target_language        VARCHAR(16),                            -- Learning target language tag.
    x_type                 SMALLINT NOT NULL DEFAULT 1,            -- 1 recording session, 2 text/script session.
    asset_object_key       TEXT UNIQUE,                            -- Uploaded audio object key.
    current_transcript_id  VARCHAR(32) UNIQUE,                     -- Current transcript id.
    created_at             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

-- Session list pagination.
CREATE INDEX IF NOT EXISTS idx_session_sessions_created_at
    ON public.session_sessions (created_at DESC);

-- Case-insensitive title search.
CREATE INDEX IF NOT EXISTS idx_session_sessions_title_lower
    ON public.session_sessions (lower(title));

-- ---------------------------------------------------------------------------
-- Revision module
-- Stores editable revised utterances generated from a transcript.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.revision_revisions (
    revision_id     VARCHAR(32) PRIMARY KEY,                       -- Revision id, uuid hex.
    session_id      VARCHAR(32) NOT NULL UNIQUE,                   -- One current revision per session.
    transcript_id   VARCHAR(32) NOT NULL,                          -- Source transcript id.
    job_id          VARCHAR(32),                                   -- Current revision_generation job id.
    user_prompt     TEXT,                                          -- User revision prompt.
    cue_language    VARCHAR(16),                                   -- Delivery CUE language tag.
    plan_sections_json TEXT NOT NULL DEFAULT '[]',                 -- Planned revision sections JSON array.
    x_status        SMALLINT NOT NULL DEFAULT 0,                   -- 0 pending, 1 generating, 2 completed, 3 failed.
    error_code      VARCHAR(64),                                   -- Stable failure code.
    error_message   TEXT,                                          -- Failure detail.
    item_count      INTEGER NOT NULL DEFAULT 0,                    -- Number of revision items.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

-- Load current revision by session.
CREATE INDEX IF NOT EXISTS idx_revision_revisions_session_id
    ON public.revision_revisions (session_id);

CREATE TABLE IF NOT EXISTS public.revision_items (
    item_id             VARCHAR(32) PRIMARY KEY,                   -- Revision item id, uuid hex.
    revision_id         VARCHAR(32) NOT NULL,                      -- Owning revision id.
    transcript_id       VARCHAR(32) NOT NULL,                      -- Source transcript id.
    source_seq_start    INTEGER NOT NULL,                          -- First source utterance seq.
    source_seq_end      INTEGER NOT NULL,                          -- Last source utterance seq.
    source_seq_count    INTEGER NOT NULL,                          -- Number of source utterances covered.
    source_seqs         TEXT NOT NULL DEFAULT '[]',                -- Source utterance seq list JSON.
    speaker             VARCHAR(64),                               -- Speaker label.
    start_time          INTEGER NOT NULL,                          -- Start time in milliseconds.
    end_time            INTEGER NOT NULL,                          -- End time in milliseconds.
    original_text       TEXT NOT NULL,                             -- Original transcript text.
    suggested_text      TEXT NOT NULL,                             -- AI-generated or initial suggested text.
    draft_text          TEXT,                                      -- User-edited draft text.
    score               SMALLINT NOT NULL,                         -- Quality/confidence score.
    issue_tags          TEXT NOT NULL DEFAULT '',                  -- Comma-separated issue tags.
    explanations        TEXT NOT NULL DEFAULT '',                  -- Explanation text.
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

-- Load revision items in source order.
CREATE INDEX IF NOT EXISTS idx_revision_items_revision_seq_span
    ON public.revision_items (revision_id, source_seq_start, source_seq_end);

-- Find revision items by transcript span.
CREATE INDEX IF NOT EXISTS idx_revision_items_transcript_seq_span
    ON public.revision_items (transcript_id, source_seq_start, source_seq_end);

-- ---------------------------------------------------------------------------
-- Script module
-- Tracks AI script generation process. Output is written to transcript/revision.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.script_generations (
    generation_id      VARCHAR(32) PRIMARY KEY,                    -- Script generation id, uuid hex.
    session_id         VARCHAR(32) NOT NULL,                       -- Created text session id.
    transcript_id      VARCHAR(32),                                -- Completed transcript id.
    job_id             VARCHAR(32),                                -- Async job id.
    x_provider         VARCHAR(32) NOT NULL,                       -- Script generator provider.
    title              VARCHAR(200) NOT NULL,                      -- Requested session title.
    x_description      TEXT,                                       -- Requested session description.
    target_language    VARCHAR(16),                                -- Requested spoken target language tag.
    cue_language       VARCHAR(16),                                -- Requested delivery CUE language tag.
    prompt             TEXT NOT NULL,                              -- User scenario prompt.
    turn_count         INTEGER NOT NULL,                           -- Target conversation turn count.
    speaker_count      INTEGER NOT NULL,                           -- Target speaker count.
    difficulty         VARCHAR(32),                                -- Requested difficulty.
    cue_style          VARCHAR(200),                               -- Requested cue style.
    must_include_json  TEXT NOT NULL DEFAULT '[]',                 -- Required expressions JSON array.
    preview_items_json TEXT NOT NULL DEFAULT '[]',                 -- Incremental generated utterance preview JSON array.
    plan_sections_json TEXT NOT NULL DEFAULT '[]',                 -- Planned script sections JSON array.
    raw_result_json    TEXT,                                       -- Raw LLM/generator result JSON.
    x_status           SMALLINT NOT NULL DEFAULT 0,                -- 0 pending, 1 generating, 2 completed, 3 failed.
    error_code         VARCHAR(64),                                -- Stable failure code.
    error_message      TEXT,                                       -- Failure detail.
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

-- List script generations by session.
CREATE INDEX IF NOT EXISTS idx_script_generations_session_id
    ON public.script_generations (session_id);

-- Lookup generation by produced transcript.
CREATE INDEX IF NOT EXISTS idx_script_generations_transcript_id
    ON public.script_generations (transcript_id);

-- List script generations by lifecycle state.
CREATE INDEX IF NOT EXISTS idx_script_generations_status_created_at
    ON public.script_generations (x_status, created_at);

-- ---------------------------------------------------------------------------
-- Translation module
-- Stores learner-facing translations for transcript and revision text.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.translation_translations (
    translation_id    VARCHAR(32) PRIMARY KEY,                    -- Translation id, uuid hex.
    session_id        VARCHAR(32),                                -- Optional owning session id.
    source_type       VARCHAR(32) NOT NULL,                       -- transcript or revision.
    source_entity_id  VARCHAR(128) NOT NULL,                      -- Source transcript_id or revision_id.
    source_language   VARCHAR(16),                                -- Source language tag.
    target_language   VARCHAR(16) NOT NULL,                       -- Target language tag, for example zh-CN.
    job_id            VARCHAR(32),                                -- Current translation_generation job id.
    x_provider        VARCHAR(32) NOT NULL,                       -- Translation provider name.
    x_model           VARCHAR(128),                               -- Provider model when applicable.
    x_status          SMALLINT NOT NULL DEFAULT 0,                -- 0 pending, 1 generating, 2 completed, 3 failed, 4 partial.
    item_count        INTEGER NOT NULL DEFAULT 0,                 -- Total translation item count.
    completed_count   INTEGER NOT NULL DEFAULT 0,                 -- Completed item count.
    stale_count       INTEGER NOT NULL DEFAULT 0,                 -- Items whose source text changed.
    error_code        VARCHAR(64),                                -- Stable failure code.
    error_message     TEXT,                                       -- Failure detail.
    raw_result_json   TEXT,                                       -- Lightweight provider result JSON.
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_translation_source_target
    ON public.translation_translations (source_type, source_entity_id, target_language);

CREATE INDEX IF NOT EXISTS idx_translation_translations_session
    ON public.translation_translations (session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_translation_translations_status_created_at
    ON public.translation_translations (x_status, created_at);

CREATE TABLE IF NOT EXISTS public.translation_items (
    item_id           VARCHAR(32) PRIMARY KEY,                    -- Translation item id, uuid hex.
    translation_id    VARCHAR(32) NOT NULL,                       -- Owning translation id.
    source_item_key   VARCHAR(128) NOT NULL,                      -- Source item id or transcript seq.
    source_seq        INTEGER,                                    -- Sort key within the source.
    speaker           VARCHAR(64),                                -- Speaker label.
    start_time        INTEGER,                                    -- Source start time in milliseconds.
    end_time          INTEGER,                                    -- Source end time in milliseconds.
    source_text       TEXT NOT NULL,                              -- Source text used for this translation.
    source_text_hash  VARCHAR(64) NOT NULL,                       -- Hash for stale detection.
    translated_text   TEXT,                                       -- Translated text.
    x_status          SMALLINT NOT NULL DEFAULT 0,                -- 0 pending, 1 generating, 2 completed, 3 failed, 4 stale.
    error_code        VARCHAR(64),                                -- Stable failure code.
    error_message     TEXT,                                       -- Failure detail.
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

CREATE INDEX IF NOT EXISTS idx_translation_items_translation_seq
    ON public.translation_items (translation_id, source_seq);

CREATE INDEX IF NOT EXISTS idx_translation_items_status
    ON public.translation_items (translation_id, x_status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_translation_items_source_item
    ON public.translation_items (translation_id, source_item_key);

-- ---------------------------------------------------------------------------
-- TTS module
-- Stores session-level TTS settings and full synthesis outputs.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.tts_session_settings (
    session_id              VARCHAR(32) PRIMARY KEY,               -- Session id.
    x_format                VARCHAR(16) NOT NULL DEFAULT 'mp3',    -- Output audio format.
    emotion_scale           NUMERIC NOT NULL DEFAULT 4.0,          -- Provider emotion scale.
    speech_rate             NUMERIC NOT NULL DEFAULT 0.0,          -- Provider speech rate.
    loudness_rate           NUMERIC NOT NULL DEFAULT 0.0,          -- Provider loudness rate.
    speaker_mappings_json   TEXT NOT NULL DEFAULT '[]',            -- Conversation speaker to provider voice JSON.
    created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

CREATE TABLE IF NOT EXISTS public.tts_syntheses (
    synthesis_id           VARCHAR(32) PRIMARY KEY,                -- Synthesis id, uuid hex.
    session_id             VARCHAR(32) NOT NULL UNIQUE,            -- One current synthesis per session.
    x_provider             VARCHAR(32) NOT NULL,                   -- TTS provider name.
    full_content_hash      VARCHAR(64) NOT NULL,                   -- Hash of full synthesis inputs/settings.
    full_asset_object_key  TEXT,                                   -- Generated full audio object key.
    full_duration_ms       INTEGER,                                -- Full audio duration in milliseconds.
    item_count             INTEGER NOT NULL DEFAULT 0,             -- Total item count.
    completed_item_count   INTEGER NOT NULL DEFAULT 0,             -- Completed item count.
    failed_item_count      INTEGER NOT NULL DEFAULT 0,             -- Failed item count.
    x_status               SMALLINT NOT NULL DEFAULT 0,            -- 0 pending, 1 generating, 2 completed, 3 partial, 4 failed.
    error_code             VARCHAR(64),                            -- Stable failure code.
    error_message          TEXT,                                   -- Failure detail.
    created_at             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

-- Load current synthesis by session.
CREATE INDEX IF NOT EXISTS idx_tts_syntheses_session_created_at
    ON public.tts_syntheses (session_id, created_at);

CREATE TABLE IF NOT EXISTS public.tts_synthesis_items (
    tts_item_id           VARCHAR(32) PRIMARY KEY,                 -- TTS item id, uuid hex.
    synthesis_id          VARCHAR(32) NOT NULL,                    -- Owning synthesis id.
    source_item_id        VARCHAR(32) NOT NULL,                    -- Source revision item id.
    source_seq_start      INTEGER NOT NULL,                        -- First source utterance seq.
    source_seq_end        INTEGER NOT NULL,                        -- Last source utterance seq.
    source_seqs           TEXT NOT NULL DEFAULT '[]',              -- Source seq list JSON.
    conversation_speaker  VARCHAR(64),                             -- Original conversation speaker.
    provider_speaker_id   VARCHAR(128) NOT NULL,                   -- Provider voice/speaker id.
    content               TEXT NOT NULL,                           -- Full TTS input including cue.
    plain_text            TEXT NOT NULL,                           -- Speech text after cue removal.
    cue_texts             TEXT NOT NULL DEFAULT '[]',              -- Removed cue texts JSON.
    content_hash          VARCHAR(64) NOT NULL,                    -- Hash of item synthesis input/settings.
    duration_ms           INTEGER,                                 -- Item audio duration in milliseconds.
    x_status              SMALLINT NOT NULL DEFAULT 0,             -- 0 pending, 1 generating, 2 completed, 3 partial, 4 failed.
    error_code            VARCHAR(64),                             -- Stable failure code.
    error_message         TEXT,                                    -- Failure detail.
    created_at            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp.
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp.
);

-- Load synthesis items in source order.
CREATE INDEX IF NOT EXISTS idx_tts_synthesis_items_seq_span
    ON public.tts_synthesis_items (synthesis_id, source_seq_start, source_seq_end);

-- One synthesis item per source revision item.
CREATE UNIQUE INDEX IF NOT EXISTS uq_tts_synthesis_items_source_item
    ON public.tts_synthesis_items (synthesis_id, source_item_id);

-- ---------------------------------------------------------------------------
-- updated_at triggers
-- Recreate triggers idempotently so rerunning this file keeps definitions fresh.
-- ---------------------------------------------------------------------------

DROP TRIGGER IF EXISTS trg_asset_assets_set_updated_at ON public.asset_assets;
DROP TRIGGER IF EXISTS trg_job_jobs_set_updated_at ON public.job_jobs;
DROP TRIGGER IF EXISTS trg_transcript_transcripts_set_updated_at ON public.transcript_transcripts;
DROP TRIGGER IF EXISTS trg_asr_recognitions_set_updated_at ON public.asr_recognitions;
DROP TRIGGER IF EXISTS trg_session_sessions_set_updated_at ON public.session_sessions;
DROP TRIGGER IF EXISTS trg_revision_revisions_set_updated_at ON public.revision_revisions;
DROP TRIGGER IF EXISTS trg_revision_items_set_updated_at ON public.revision_items;
DROP TRIGGER IF EXISTS trg_script_generations_set_updated_at ON public.script_generations;
DROP TRIGGER IF EXISTS trg_translation_translations_set_updated_at ON public.translation_translations;
DROP TRIGGER IF EXISTS trg_translation_items_set_updated_at ON public.translation_items;
DROP TRIGGER IF EXISTS trg_tts_session_settings_set_updated_at ON public.tts_session_settings;
DROP TRIGGER IF EXISTS trg_tts_syntheses_set_updated_at ON public.tts_syntheses;
DROP TRIGGER IF EXISTS trg_tts_synthesis_items_set_updated_at ON public.tts_synthesis_items;

-- Keep asset metadata update timestamps current.
CREATE TRIGGER trg_asset_assets_set_updated_at
BEFORE UPDATE ON public.asset_assets
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- Keep job lifecycle update timestamps current.
CREATE TRIGGER trg_job_jobs_set_updated_at
BEFORE UPDATE ON public.job_jobs
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- Keep transcript header update timestamps current.
CREATE TRIGGER trg_transcript_transcripts_set_updated_at
BEFORE UPDATE ON public.transcript_transcripts
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- Keep ASR recognition update timestamps current.
CREATE TRIGGER trg_asr_recognitions_set_updated_at
BEFORE UPDATE ON public.asr_recognitions
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- Keep session update timestamps current.
CREATE TRIGGER trg_session_sessions_set_updated_at
BEFORE UPDATE ON public.session_sessions
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- Keep revision header update timestamps current.
CREATE TRIGGER trg_revision_revisions_set_updated_at
BEFORE UPDATE ON public.revision_revisions
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- Keep revision item update timestamps current.
CREATE TRIGGER trg_revision_items_set_updated_at
BEFORE UPDATE ON public.revision_items
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- Keep script generation update timestamps current.
CREATE TRIGGER trg_script_generations_set_updated_at
BEFORE UPDATE ON public.script_generations
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- Keep translation header update timestamps current.
CREATE TRIGGER trg_translation_translations_set_updated_at
BEFORE UPDATE ON public.translation_translations
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- Keep translation item update timestamps current.
CREATE TRIGGER trg_translation_items_set_updated_at
BEFORE UPDATE ON public.translation_items
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- Keep TTS settings update timestamps current.
CREATE TRIGGER trg_tts_session_settings_set_updated_at
BEFORE UPDATE ON public.tts_session_settings
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- Keep TTS synthesis header update timestamps current.
CREATE TRIGGER trg_tts_syntheses_set_updated_at
BEFORE UPDATE ON public.tts_syntheses
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- Keep TTS synthesis item update timestamps current.
CREATE TRIGGER trg_tts_synthesis_items_set_updated_at
BEFORE UPDATE ON public.tts_synthesis_items
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();
