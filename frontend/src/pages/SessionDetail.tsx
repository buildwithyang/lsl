import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Mic2, FileText, AudioWaveform, Loader2, RefreshCw } from 'lucide-react';
import { AudioPlayer } from '@/components/AudioPlayer';
import { StatusBadge } from '@/components/StatusBadge';
import { SessionFlowNav } from '@/components/SessionFlowNav';
import { Button } from '@/components/ui/button';
import { formatDateTime, formatTime } from '@/utils/formatTime';
import { speakerColors } from '@/data/mockData';
import { useApp } from '@/context/AppContext';
import { NotFound } from './NotFound';
import type { RevisionItem, TranscriptItem } from '@/types';
import { getSession, updateSession } from '@/lib/api/sessions';
import { createAsrRecognition } from '@/lib/api/asr';
import { getTranscript } from '@/lib/api/transcripts';
import { getTtsSynthesis } from '@/lib/api/tts';
import { applyTtsSynthesis, mapSessionItem, mapTranscript } from '@/lib/domain';
import { useTranslation } from '@/hooks/useTranslation';
import { InlineTranslationToggle } from '@/components/translation/InlineTranslationToggle';
import { useI18n } from '@/i18n';

export function SessionDetail() {
  const { id } = useParams<{ id: string }>();
  const { getSessionById, dispatch } = useApp();
  const [loadedSession, setLoadedSession] = useState<ReturnType<typeof getSessionById> | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [activeTranscriptIndex, setActiveTranscriptIndex] = useState<number | null>(null);
  const [seekRequest, setSeekRequest] = useState<{ time: number; requestId: number } | null>(null);
  const [currentTranscriptId, setCurrentTranscriptId] = useState<string | null>(null);
  const [isRetryingTranscription, setIsRetryingTranscription] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const { t, language } = useI18n();

  const session = useMemo(() => loadedSession || (id ? getSessionById(id) : undefined), [id, getSessionById, loadedSession]);
  const transcriptTranslation = useTranslation({
    sourceType: 'transcript',
    sourceEntityId: currentTranscriptId,
    sessionId: session?.id,
    sourceLanguage: session?.targetLanguage,
    targetLanguage: language,
    enabled: !!currentTranscriptId && !!session?.transcript && session.transcript.length > 0,
  });

  useEffect(() => {
    if (session) dispatch({ type: 'SET_CURRENT_SESSION', payload: session });
  }, [session, dispatch]);

  useEffect(() => {
    if (!id) return;
    const sessionId = id;
    let cancelled = false;
    let refreshTimer: ReturnType<typeof window.setTimeout> | null = null;

    async function loadSession(): Promise<boolean> {
      setNotFound(false);
      try {
        const item = await getSession(sessionId);
        let nextSession = mapSessionItem(item);
        if (!cancelled) {
          setCurrentTranscriptId(item.session.current_transcript_id ?? null);
        }

        if (item.session.current_transcript_id) {
          try {
            const transcript = await getTranscript(item.session.current_transcript_id);
            nextSession = { ...nextSession, transcript: mapTranscript(transcript) };
          } catch {
            // Transcript may not be ready while the source job is still processing.
          }
        }

        try {
          const synthesis = await getTtsSynthesis(sessionId);
          nextSession = applyTtsSynthesis(nextSession, synthesis);
        } catch {
          // TTS output is optional until step 3.
        }

        if (!cancelled) {
          setLoadedSession(nextSession);
          dispatch({ type: 'UPDATE_SESSION', payload: nextSession });
        }
        return nextSession.status === 'pending' || nextSession.status === 'processing';
      } catch {
        if (!cancelled) setNotFound(true);
        return false;
      }
    }

    async function loadAndSchedule() {
      const shouldKeepPolling = await loadSession();
      if (!cancelled && shouldKeepPolling) {
        refreshTimer = window.setTimeout(loadAndSchedule, 3000);
      }
    }

    void loadAndSchedule();
    return () => {
      cancelled = true;
      if (refreshTimer) window.clearTimeout(refreshTimer);
    };
  }, [id, dispatch, reloadToken]);

  const handleRetryTranscription = useCallback(async () => {
    if (!session?.assetObjectKey || !session.audioUrl) return;

    setIsRetryingTranscription(true);
    setRetryError(null);
    setActiveTranscriptIndex(null);

    try {
      const recognition = await createAsrRecognition({
        objectKey: session.assetObjectKey,
        audioUrl: session.audioUrl,
        targetLanguage: session.targetLanguage,
      });
      const item = await updateSession(session.id, {
        currentTranscriptId: recognition.transcript.transcript_id,
      });
      const nextSession = mapSessionItem(item);
      setCurrentTranscriptId(item.session.current_transcript_id ?? recognition.transcript.transcript_id);
      setLoadedSession(nextSession);
      dispatch({ type: 'UPDATE_SESSION', payload: nextSession });
      setReloadToken((current) => current + 1);
    } catch (error) {
      setRetryError(error instanceof Error ? error.message : t('error.retryTranscription'));
    } finally {
      setIsRetryingTranscription(false);
    }
  }, [dispatch, session, t]);

  if (!session && !notFound) {
    return <div className="text-[13px] text-slate-500">{t('session.loading')}</div>;
  }

  if (!session) return <NotFound />;

  const transcript = session.transcript || session.revision;
  const totalDuration = transcript && transcript.length > 0 ? transcript[transcript.length - 1].endTime : 0;
  const canOpenRevise = session.status === 'completed' || !!session.revision;
  const shouldShowAudioPlayer = session.type === 'audio';
  const canRetryTranscription = session.type === 'audio'
    && session.status === 'failed'
    && !!session.assetObjectKey
    && !!session.audioUrl;

  const isRevision = (item: RevisionItem | TranscriptItem): item is RevisionItem => 'cue' in item;

  const handleTranscriptSelect = (index: number, item: RevisionItem | TranscriptItem) => {
    setActiveTranscriptIndex(index);
    setSeekRequest((current) => ({
      time: item.startTime,
      requestId: (current?.requestId ?? 0) + 1,
    }));
  };

  return (
    <div className="space-y-6">
      <SessionFlowNav
        sessionId={session.id}
        currentStep="overview"
        canRevise={canOpenRevise}
        canListen={!!session.synthesizedAudioUrl}
      />

      {/* Header Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-3">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 flex-shrink-0 rounded-xl flex items-center justify-center ${
                session.type === 'audio' ? 'bg-violet-100 text-violet-600' : 'bg-sky-100 text-sky-600'
              }`}>
                {session.type === 'audio' ? <Mic2 className="w-5 h-5" /> : <FileText className="w-5 h-5" />}
              </div>
              <div className="min-w-0">
                <h1 className="truncate text-[20px] font-bold text-slate-900 tracking-tight">{session.title}</h1>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <StatusBadge status={session.status} />
              <span className="text-[12px] text-slate-400">{formatDateTime(session.createdAt)}</span>
              {totalDuration > 0 && (
                <span className="flex items-center gap-1 font-mono text-[12px] text-slate-500">
                  <AudioWaveform className="w-3 h-3" />
                  {formatTime(totalDuration)}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {shouldShowAudioPlayer && (
        <AudioPlayer
          audioUrl={session.audioUrl}
          items={transcript}
          seekTo={seekRequest}
          onActiveIndexChange={(index) => setActiveTranscriptIndex(index === -1 ? null : index)}
        />
      )}

      {session.type === 'audio' && session.status === 'failed' && (!transcript || transcript.length === 0) && (
        <div className="rounded-xl border border-red-100 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <h3 className="text-[14px] font-bold text-slate-800">{t('session.transcriptionFailedTitle')}</h3>
              <p className="mt-1 text-[12px] text-slate-500">{t('session.transcriptionFailedHelp')}</p>
              {retryError && <p className="mt-2 text-[12px] text-red-500">{retryError}</p>}
            </div>
            {canRetryTranscription && (
              <Button
                type="button"
                onClick={handleRetryTranscription}
                disabled={isRetryingTranscription}
                className="h-9 shrink-0 bg-indigo-500 px-3 text-[12px] font-semibold text-white hover:bg-indigo-600 disabled:opacity-60"
              >
                {isRetryingTranscription
                  ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  : <RefreshCw className="mr-1.5 h-3.5 w-3.5" />}
                {isRetryingTranscription ? t('session.retryingTranscription') : t('session.retryTranscription')}
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Transcript */}
      {(!transcript || transcript.length === 0) && session.status !== 'failed' && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-8 text-center">
          <p className="text-[13px] text-slate-500">
            {session.type === 'ai_script' ? t('session.generatingScriptTranscript') : t('session.transcriptionProcessing')}
          </p>
        </div>
      )}

      {transcript && transcript.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100">
            <h3 className="text-[14px] font-bold text-slate-800">{t('session.transcript')}</h3>
          </div>
          {transcriptTranslation.error && (
            <div className="px-5 py-2 border-b border-red-100 bg-red-50/60 text-[12px] text-red-600">
              {t('translation.error')}: {transcriptTranslation.error}
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-50 bg-slate-50/50">
                  <th className="text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider py-2.5 px-5 w-[15%]">{t('common.speaker')}</th>
                  <th className="text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider py-2.5 px-3 w-[10%]">{t('common.time')}</th>
                  <th className="text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider py-2.5 px-3">{t('common.content')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {transcript.map((item, index) => {
                  const isActive = activeTranscriptIndex === index;

                  return (
                    <tr
                      key={item.id}
                      role="button"
                      tabIndex={0}
                      aria-current={isActive ? 'true' : undefined}
                      onClick={() => handleTranscriptSelect(index, item)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          handleTranscriptSelect(index, item);
                        }
                      }}
                      className={`cursor-pointer transition-colors ${
                        isActive
                          ? 'bg-indigo-50/80 ring-1 ring-inset ring-indigo-200'
                          : 'hover:bg-slate-50/50'
                      }`}
                    >
                      <td className="py-3 px-5">
                        <div className="flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: speakerColors[item.speaker] || '#94A3B8' }} />
                          <span className={`text-[13px] font-medium ${isActive ? 'text-indigo-700' : 'text-slate-700'}`}>{item.speaker}</span>
                        </div>
                      </td>
                      <td className={`py-3 px-3 text-[12px] font-mono ${isActive ? 'text-indigo-600 font-semibold' : 'text-slate-400'}`}>{formatTime(item.startTime)}</td>
                      <td className={`py-3 px-3 text-[13px] leading-relaxed ${isActive ? 'text-slate-900 font-medium' : 'text-slate-700'}`}>
                        {isRevision(item) && item.cue ? (
                          <div>
                            <span className="font-mono text-[11px] bg-amber-50 text-amber-700 border border-amber-200 rounded-md px-1.5 py-0.5 mr-1.5 font-medium">
                              [{item.cue}]
                            </span>
                            {item.content}
                          </div>
                        ) : (
                          'text' in item ? item.text : item.content
                        )}
                        {'text' in item && (
                          <InlineTranslationToggle
                            text={transcriptTranslation.itemsByKey.get(item.id)?.translated_text}
                            translating={transcriptTranslation.translatingKeys.has(item.id)}
                            failed={transcriptTranslation.itemsByKey.get(item.id)?.status_name === 'failed'}
                            onTranslate={() => void transcriptTranslation.translateItem({
                              source_item_key: item.id,
                              source_seq: index,
                              speaker: item.speaker,
                              source_text: item.text,
                            })}
                          />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
