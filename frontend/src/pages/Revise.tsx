import { useState, useCallback, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Sparkles, Loader2, Volume2, Wand2 } from 'lucide-react';
import { RevisionCard } from '@/components/RevisionCard';
import { SectionGenerationProgress } from '@/components/SectionGenerationProgress';
import type { SectionGenerationProgressItem } from '@/components/SectionGenerationProgress';
import { SessionFlowNav } from '@/components/SessionFlowNav';
import { SpeakerSelect } from '@/components/SpeakerSelect';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useApp } from '@/context/AppContext';
import { ttsVoices } from '@/data/mockData';
import type { RevisionItem, SpeakerMapping } from '@/types';
import type { TtsSpeakerItem } from '@/types/api';
import { NotFound } from './NotFound';
import { getSession } from '@/lib/api/sessions';
import { ApiRequestError } from '@/lib/api/client';
import { getJob } from '@/lib/api/jobs';
import { getScriptGenerationPreview } from '@/lib/api/scripts';
import { getTranscript } from '@/lib/api/transcripts';
import { createRevision, getRevisionPreview, updateRevisionItem } from '@/lib/api/revisions';
import { createTtsSynthesis, generateTtsItemAudio, getTtsSettings, getTtsSpeakers, getTtsSynthesis, updateTtsSettings } from '@/lib/api/tts';
import { applyTtsSettings, applyTtsSynthesis, mapRevision, mapSessionItem, mapTranscript } from '@/lib/domain';
import { getVoiceForSpeaker } from '@/lib/voice';
import type { RevisionPlanSectionResponse, ScriptGenerationPlanSectionResponse, ScriptGenerationPreviewItemResponse, TtsSynthesisResponse } from '@/types/api';
import { useTranslation } from '@/hooks/useTranslation';
import { TranslationButton } from '@/components/translation/TranslationButton';
import { useI18n } from '@/i18n';

const TTS_PARAM_RANGES = {
  emotionScale: { min: 1, max: 5, step: 0.1, defaultValue: 4 },
  speechRate: { min: -50, max: 100, step: 1, defaultValue: 0 },
  loudnessRate: { min: -50, max: 100, step: 1, defaultValue: 0 },
};

function clampTtsParam(value: number, range: { min: number; max: number; step: number; defaultValue: number }): number {
  if (!Number.isFinite(value)) return range.defaultValue;
  const clamped = Math.min(range.max, Math.max(range.min, value));
  return Math.round(clamped / range.step) * range.step;
}

export function Revise() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { getSessionById, dispatch } = useApp();
  const { t, language } = useI18n();
  const [loadedSession, setLoadedSession] = useState<ReturnType<typeof getSessionById> | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [isPreparingScript, setIsPreparingScript] = useState(false);
  const [scriptPreviewItems, setScriptPreviewItems] = useState<ScriptGenerationPreviewItemResponse[]>([]);
  const [scriptPlanSections, setScriptPlanSections] = useState<ScriptGenerationPlanSectionResponse[]>([]);
  const [scriptTargetTurnCount, setScriptTargetTurnCount] = useState<number | null>(null);

  const session = useMemo(() => loadedSession || (id ? getSessionById(id) : undefined), [id, getSessionById, loadedSession]);

  const [revision, setRevision] = useState<RevisionItem[]>([]);
  const [revisionId, setRevisionId] = useState<string | null>(null);
  const [revisionTranscriptId, setRevisionTranscriptId] = useState<string | null>(null);
  const [revisionTranscript, setRevisionTranscript] = useState<ReturnType<typeof mapTranscript>>([]);
  const [revisionPlanSections, setRevisionPlanSections] = useState<RevisionPlanSectionResponse[]>([]);
  const [userPrompt, setUserPrompt] = useState('');
  const [isRevising, setIsRevising] = useState(false);
  const [isSynthesizing, setIsSynthesizing] = useState(false);
  const [format, setFormat] = useState('mp3');
  const [emotionScale, setEmotionScale] = useState([TTS_PARAM_RANGES.emotionScale.defaultValue]);
  const [speechRate, setSpeechRate] = useState([TTS_PARAM_RANGES.speechRate.defaultValue]);
  const [loudnessRate, setLoudnessRate] = useState([TTS_PARAM_RANGES.loudnessRate.defaultValue]);
  const [speakerMappings, setSpeakerMappings] = useState<SpeakerMapping[]>([]);
  const [voiceList, setVoiceList] = useState<TtsSpeakerItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [synthesizingItemId, setSynthesizingItemId] = useState<string | null>(null);
  const [playingOriginalItemId, setPlayingOriginalItemId] = useState<string | null>(null);
  const [showAllTranslations, setShowAllTranslations] = useState(false);
  const [isStartingTranslation, setIsStartingTranslation] = useState(false);
  const [syncingTranslationItemIds, setSyncingTranslationItemIds] = useState<Set<string>>(() => new Set());
  const userPromptTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const itemAudioRef = useRef<HTMLAudioElement | null>(null);
  const itemAudioUrlRef = useRef<string | null>(null);
  const draftSaveTimersRef = useRef(new Map<string, ReturnType<typeof window.setTimeout>>());
  const pendingDraftTextRef = useRef(new Map<string, string>());
  const draftSavePromisesRef = useRef(new Map<string, Promise<void>>());
  const savingDraftItemIdsRef = useRef(new Set<string>());
  const dirtyTranslationVersionRef = useRef(0);
  const dirtyTranslationItemVersionsRef = useRef(new Map<string, number>());
  const [dirtyTranslationItemIds, setDirtyTranslationItemIds] = useState<Set<string>>(() => new Set());
  const scriptGenerationId = searchParams.get('generation_id');
  const scriptJobId = searchParams.get('job_id');
  const revisionTranslation = useTranslation({
    sourceType: 'revision',
    sourceEntityId: revisionId,
    sessionId: id,
    targetLanguage: language,
    enabled: !!revisionId && revision.length > 0 && !isRevising,
    getSourceItems: useCallback(() => {
      return revision.map((item, index) => ({
        source_item_key: item.id,
        source_seq: index,
        speaker: item.speaker,
        start_time: item.startTime,
        end_time: item.endTime,
        source_text: item.fullText,
      }))
    }, [revision]),
  });
  const revisionProgress = useMemo(
    () => buildRevisionProgress(revisionTranscript, revision, revisionPlanSections),
    [revisionTranscript, revision, revisionPlanSections],
  );
  const scriptProgress = useMemo(
    () => buildScriptGenerationProgress(scriptPlanSections, scriptPreviewItems, scriptTargetTurnCount),
    [scriptPlanSections, scriptPreviewItems, scriptTargetTurnCount],
  );

  const resizeUserPromptTextarea = useCallback(() => {
    const textarea = userPromptTextareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, []);

  useLayoutEffect(() => {
    resizeUserPromptTextarea();
  }, [resizeUserPromptTextarea, userPrompt]);

  useEffect(() => {
    draftSaveTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    draftSaveTimersRef.current.clear();
    pendingDraftTextRef.current.clear();
    dirtyTranslationItemVersionsRef.current.clear();
    setDirtyTranslationItemIds(new Set());
    setSyncingTranslationItemIds(new Set());
  }, [revisionId]);

  useEffect(() => {
    if (!revisionTranscriptId) {
      setRevisionTranscript([]);
      return;
    }

    let cancelled = false;
    getTranscript(revisionTranscriptId)
      .then((data) => {
        if (!cancelled) {
          setRevisionTranscript(mapTranscript(data));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRevisionTranscript([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [revisionTranscriptId]);

  useEffect(() => {
    if (session) {
      dispatch({ type: 'SET_CURRENT_SESSION', payload: session });
      const rev = session.revision || [];
      setRevision(rev);
      setUserPrompt(session.userPrompt || '');
      const speakers = [...new Set(rev.map(r => r.speaker))];
      setSpeakerMappings(prev => {
        const validVoiceIds = voiceList.length > 0 ? new Set(voiceList.map(voice => voice.speaker_id)) : null;
        return speakers.map((speaker, index) => {
          const currentVoice = prev.find(mapping => mapping.speaker === speaker)?.voice;
          if (currentVoice && (!validVoiceIds || validVoiceIds.has(currentVoice))) {
            return { speaker, voice: currentVoice };
          }

          const savedVoice = session.speakerMappings?.find(mapping => mapping.speaker === speaker)?.voice;
          if (savedVoice && (!validVoiceIds || validVoiceIds.has(savedVoice))) {
            return { speaker, voice: savedVoice };
          }

          const fallbackVoice = voiceList.length > 0
            ? voiceList[index % voiceList.length].speaker_id
            : ttsVoices[index % ttsVoices.length];
          return { speaker, voice: fallbackVoice };
        });
      });
    }
  }, [session, dispatch, voiceList]);

  useEffect(() => {
    if (!id) return;
    const sessionId = id;
    let cancelled = false;
    let refreshTimer: ReturnType<typeof window.setTimeout> | null = null;

    async function loadRevision(): Promise<boolean> {
      setNotFound(false);
      setError(null);
      try {
        const item = await getSession(sessionId);
        let nextSession = mapSessionItem(item);
        let hasRevision = false;
        let shouldPoll = false;
        let preparingScript = false;
        let revisionGenerating = false;
        try {
          const preview = await getRevisionPreview(sessionId);
          const revisionData = { ...preview.revision, items: preview.items };
          setRevisionId(revisionData.revision_id);
          setRevisionTranscriptId(revisionData.transcript_id);
          setRevisionPlanSections(normalizeRevisionPlanSections(revisionData.plan_sections));
          nextSession = { ...nextSession, revision: mapRevision(revisionData), userPrompt: revisionData.user_prompt ?? undefined };
          hasRevision = true;
          revisionGenerating = isRevisionGenerating(revisionData.status_name);
          shouldPoll = shouldPoll || revisionGenerating;
        } catch (err) {
          if (!(err instanceof ApiRequestError && err.status === 404)) {
            setError(err instanceof Error ? err.message : t('error.loadRevision'));
          }
        }

        if (!hasRevision && nextSession.type === 'audio' && nextSession.status === 'completed') {
          revisionGenerating = true;
          try {
            const revisionData = await createRevision({ sessionId, userPrompt: '', force: false, cueLanguage: language });
            setRevisionId(revisionData.revision_id);
            setRevisionTranscriptId(revisionData.transcript_id);
            setRevisionPlanSections(normalizeRevisionPlanSections(revisionData.plan_sections));
            nextSession = { ...nextSession, revision: mapRevision(revisionData), userPrompt: revisionData.user_prompt ?? undefined };
            hasRevision = true;
            revisionGenerating = isRevisionGenerating(revisionData.status_name);
            shouldPoll = shouldPoll || revisionGenerating;
            if (revisionData.status_name === 'failed') {
              setError(revisionData.error_message || t('error.reviseSession'));
            }
          } catch (err) {
            revisionGenerating = false;
            setError(err instanceof Error ? err.message : t('error.startRevision'));
          }
        }

        if (hasRevision) {
          try {
            const settings = await getTtsSettings(sessionId);
            nextSession = applyTtsSettings(nextSession, settings);
            setFormat(settings.format);
            setEmotionScale([clampTtsParam(settings.emotion_scale, TTS_PARAM_RANGES.emotionScale)]);
            setSpeechRate([clampTtsParam(settings.speech_rate, TTS_PARAM_RANGES.speechRate)]);
            setLoudnessRate([clampTtsParam(settings.loudness_rate, TTS_PARAM_RANGES.loudnessRate)]);
          } catch {
            // Settings are optional until created.
          }

          try {
            const synthesis = await getTtsSynthesis(sessionId);
            nextSession = applyTtsSynthesis(nextSession, synthesis);
            shouldPoll = shouldPoll || isSynthesisRunning(synthesis);
          } catch {
            // Synthesis is optional until the user generates listening audio.
          }
        }

        if (!hasRevision && nextSession.type === 'ai_script') {
          preparingScript = nextSession.status === 'pending' || nextSession.status === 'processing';

          if (scriptGenerationId) {
            try {
              const preview = await getScriptGenerationPreview(scriptGenerationId);
              if (!cancelled) {
                setScriptPreviewItems(preview.items);
                setScriptTargetTurnCount(preview.generation.turn_count);
                setScriptPlanSections(normalizeScriptPlanSections(preview.generation.plan_sections));
              }
              if (preview.generation.status_name === 'generating' || preview.generation.status_name === 'pending') {
                preparingScript = true;
                shouldPoll = true;
              } else if (preview.generation.status_name === 'failed') {
                preparingScript = false;
                setError(preview.generation.error_message || t('error.scriptGeneration'));
              }
            } catch (err) {
              if (!(err instanceof ApiRequestError && err.status === 404)) {
                setError(err instanceof Error ? err.message : t('error.loadScriptPreview'));
              }
            }
          }

          if (scriptJobId) {
            try {
              const job = await getJob(scriptJobId);
              if (job.status_name === 'failed' || job.status_name === 'canceled') {
                preparingScript = false;
                setError(job.error_message || t('error.scriptGeneration'));
              } else if (job.status_name === 'queued' || job.status_name === 'running' || job.status_name === 'completed') {
                preparingScript = true;
                shouldPoll = true;
              }
            } catch (err) {
              if (!(err instanceof ApiRequestError && err.status === 404)) {
                setError(err instanceof Error ? err.message : t('error.loadScriptJob'));
              }
            }
          } else if (preparingScript) {
            shouldPoll = true;
          }
        }

        if (hasRevision && (scriptJobId || scriptGenerationId)) {
          setSearchParams({}, { replace: true });
        }

        if (!cancelled) {
          if (hasRevision) {
            setScriptPreviewItems([]);
            setScriptPlanSections([]);
            setScriptTargetTurnCount(null);
          } else {
            setRevisionPlanSections([]);
          }
          setIsPreparingScript(!hasRevision && preparingScript);
          setIsRevising(revisionGenerating);
          setLoadedSession(nextSession);
          dispatch({ type: 'UPDATE_SESSION', payload: nextSession });
        }
        return shouldPoll;
      } catch {
        if (!cancelled) {
          setIsPreparingScript(false);
          setNotFound(true);
        }
        return false;
      }
    }

    async function loadVoices() {
      try {
        const data = await getTtsSpeakers();
        if (!cancelled && data.items.length > 0) {
          setVoiceList(data.items);
        }
      } catch {
        // Keep bundled voice list as fallback.
      }
    }

    async function loadAndSchedule() {
      const shouldKeepPolling = await loadRevision();
      if (!cancelled && shouldKeepPolling) {
        refreshTimer = window.setTimeout(loadAndSchedule, 2000);
      }
    }

    void loadAndSchedule();
    void loadVoices();
    return () => {
      cancelled = true;
      if (refreshTimer) window.clearTimeout(refreshTimer);
    };
  }, [id, dispatch, language, scriptGenerationId, scriptJobId, setSearchParams, t]);

  useEffect(() => {
    return () => {
      draftSaveTimersRef.current.forEach((timer) => window.clearTimeout(timer));
      draftSaveTimersRef.current.clear();
      if (itemAudioRef.current) {
        itemAudioRef.current.pause();
      }
      if (itemAudioUrlRef.current) {
        URL.revokeObjectURL(itemAudioUrlRef.current);
      }
    };
  }, []);

  const saveRevisionDraftNow = useCallback((itemId: string): Promise<void> => {
    const existing = draftSavePromisesRef.current.get(itemId);
    if (existing) return existing;

    const promise = (async () => {
      savingDraftItemIdsRef.current.add(itemId);
      try {
        while (pendingDraftTextRef.current.has(itemId)) {
          const textToSave = pendingDraftTextRef.current.get(itemId) ?? '';
          await updateRevisionItem(itemId, { draftText: textToSave });
          if (pendingDraftTextRef.current.get(itemId) === textToSave) {
            pendingDraftTextRef.current.delete(itemId);
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : t('error.saveRevisionItem'));
        throw err;
      } finally {
        savingDraftItemIdsRef.current.delete(itemId);
        draftSavePromisesRef.current.delete(itemId);
      }
    })();

    draftSavePromisesRef.current.set(itemId, promise);
    return promise;
  }, [t]);

  const flushRevisionDraftSaves = useCallback(async () => {
    draftSaveTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    draftSaveTimersRef.current.clear();

    const itemIds = new Set([
      ...pendingDraftTextRef.current.keys(),
      ...savingDraftItemIdsRef.current.values(),
    ]);
    if (itemIds.size === 0) return;

    await Promise.all([...itemIds].map((itemId) => saveRevisionDraftNow(itemId)));
  }, [saveRevisionDraftNow]);

  const handleUpdateRevision = useCallback((itemId: string, fullText: string) => {
    setRevision(prev => prev.map(item => item.id === itemId ? { ...item, fullText } : item));
    pendingDraftTextRef.current.set(itemId, fullText);
    dirtyTranslationVersionRef.current += 1;
    dirtyTranslationItemVersionsRef.current.set(itemId, dirtyTranslationVersionRef.current);
    setDirtyTranslationItemIds(new Set(dirtyTranslationItemVersionsRef.current.keys()));

    const existingTimer = draftSaveTimersRef.current.get(itemId);
    if (existingTimer) {
      window.clearTimeout(existingTimer);
    }
    const timer = window.setTimeout(() => {
      draftSaveTimersRef.current.delete(itemId);
      void saveRevisionDraftNow(itemId).catch(() => undefined);
    }, 600);
    draftSaveTimersRef.current.set(itemId, timer);
  }, [saveRevisionDraftNow]);

  const handleUpdateTranslation = useCallback(async (itemId?: string) => {
    setIsStartingTranslation(true);
    try {
      await flushRevisionDraftSaves();
      if (itemId) {
        const revItem = revision.find((r) => r.id === itemId);
        if (!revItem) {
          throw new Error(t('error.updateTranslation'));
        }
        setSyncingTranslationItemIds((prev) => {
          const next = new Set(prev);
          next.add(itemId);
          return next;
        });
        const data = await revisionTranslation.translateItem({
          source_item_key: revItem.id,
          source_seq: revision.indexOf(revItem),
          speaker: revItem.speaker,
          start_time: revItem.startTime,
          end_time: revItem.endTime,
          source_text: revItem.fullText,
        });
        if (!data) {
          throw new Error(t('error.updateTranslation'));
        }
        dirtyTranslationItemVersionsRef.current.delete(itemId);
        setDirtyTranslationItemIds(new Set(dirtyTranslationItemVersionsRef.current.keys()));
      } else {
        const data = await revisionTranslation.retry();
        if (!data) {
          throw new Error(t('error.updateTranslation'));
        }
        dirtyTranslationItemVersionsRef.current.clear();
        setDirtyTranslationItemIds(new Set());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('error.saveRevisionItem'));
    } finally {
      setIsStartingTranslation(false);
      if (itemId) {
        setSyncingTranslationItemIds((prev) => {
          const next = new Set(prev);
          next.delete(itemId);
          return next;
        });
      }
    }
  }, [flushRevisionDraftSaves, revisionTranslation, revision, t]);

  const handleReviseByAI = useCallback(async () => {
    if (!id) return;
    setIsRevising(true);
    setError(null);
    // UI flow: hide the old revision immediately; polling below fills partial results.
    setRevision([]);
    setRevisionPlanSections([]);
    if (session) {
      dispatch({ type: 'UPDATE_SESSION', payload: { ...session, revision: [], userPrompt } });
    }
    try {
      let data = await createRevision({ sessionId: id, userPrompt, force: true, cueLanguage: language });
      setRevisionId(data.revision_id);
      setRevisionTranscriptId(data.transcript_id);
      setRevisionPlanSections(normalizeRevisionPlanSections(data.plan_sections));
      let nextRevision = mapRevision(data);
      setRevision(nextRevision);
      if (session) {
        dispatch({ type: 'UPDATE_SESSION', payload: { ...session, revision: nextRevision, userPrompt } });
      }

      // The revision job writes items incrementally, so polling GET /revisions behaves like a stream.
      for (let attempt = 0; attempt < 120 && isRevisionGenerating(data.status_name); attempt += 1) {
        await wait(1500);
        const preview = await getRevisionPreview(id);
        data = { ...preview.revision, items: preview.items };
        setRevisionId(data.revision_id);
        setRevisionTranscriptId(data.transcript_id);
        setRevisionPlanSections(normalizeRevisionPlanSections(data.plan_sections));
        nextRevision = mapRevision(data);
        setRevision(nextRevision);
        if (session) {
          dispatch({ type: 'UPDATE_SESSION', payload: { ...session, revision: nextRevision, userPrompt } });
        }
      }

      if (data.status_name === 'failed') {
        throw new Error(data.error_message || t('error.reviseSession'));
      }

      if (isRevisionGenerating(data.status_name)) {
        throw new Error(t('error.revisionStillGenerating'));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('error.reviseSession'));
    } finally {
      setIsRevising(false);
    }
  }, [id, userPrompt, session, dispatch, language, t]);

  // Ensure speaker mappings use valid speaker_ids after voices are loaded
  useEffect(() => {
    if (voiceList.length === 0) return;

    const validIds = new Set(voiceList.map(v => v.speaker_id));
    const nameToId = new Map(voiceList.map(v => [v.name, v.speaker_id]));

    setSpeakerMappings(prev => {
      let changed = false;
      const updated = prev.map(m => {
        if (validIds.has(m.voice)) return m;
        const idFromName = nameToId.get(m.voice);
        if (idFromName) {
          changed = true;
          return { ...m, voice: idFromName };
        }
        changed = true;
        return { ...m, voice: voiceList[0].speaker_id };
      });
      return changed ? updated : prev;
    });
  }, [voiceList]);

  const handleSynthesize = useCallback(async () => {
    if (!id) return;
    setIsSynthesizing(true);
    setError(null);
    try {
      await flushRevisionDraftSaves();
      if (dirtyTranslationItemVersionsRef.current.size > 0) {
        await handleUpdateTranslation();
      }

      await updateTtsSettings({
        sessionId: id,
        format,
        emotionScale: emotionScale[0],
        speechRate: speechRate[0],
        loudnessRate: loudnessRate[0],
        speakerMappings: speakerMappings.map((mapping) => ({
          conversation_speaker: mapping.speaker,
          provider_speaker_id: mapping.voice,
        })),
      });

      let synthesis = await createTtsSynthesis({ sessionId: id });

      for (let attempt = 0; attempt < 40 && isSynthesisRunning(synthesis); attempt += 1) {
        await wait(1500);
        synthesis = await getTtsSynthesis(id);
      }

      if (synthesis.status_name === 'failed') {
        throw new Error(synthesis.error_message || t('error.synthesizeAudio'));
      }

      if (synthesis.full_asset_url && session) {
        const nextSession = applyTtsSynthesis(session, synthesis);
        setLoadedSession(nextSession);
        dispatch({ type: 'UPDATE_SESSION', payload: nextSession });
        navigate(`/session/${session.id}/listening`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('error.synthesizeAudio'));
    } finally {
      setIsSynthesizing(false);
    }
  }, [
    id,
    flushRevisionDraftSaves,
    handleUpdateTranslation,
    format,
    emotionScale,
    speechRate,
    loudnessRate,
    speakerMappings,
    session,
    dispatch,
    navigate,
    t,
  ]);

  const stopItemAudio = useCallback(() => {
    if (itemAudioRef.current) {
      itemAudioRef.current.pause();
      itemAudioRef.current = null;
    }
    if (itemAudioUrlRef.current) {
      URL.revokeObjectURL(itemAudioUrlRef.current);
      itemAudioUrlRef.current = null;
    }
  }, []);

  const playAudio = useCallback((
    audio: HTMLAudioElement,
    options: {
      startTime?: number;
      endTime?: number;
      objectUrl?: string;
      onFinish?: () => void;
    } = {},
  ) => {
    stopItemAudio();

    itemAudioRef.current = audio;
    itemAudioUrlRef.current = options.objectUrl ?? null;

    const finish = () => {
      options.onFinish?.();
    };
    const stopAtEndTime = () => {
      if (options.endTime !== undefined && audio.currentTime >= options.endTime) {
        audio.pause();
        finish();
        audio.removeEventListener('timeupdate', stopAtEndTime);
      }
    };
    const startPlayback = () => {
      audio.currentTime = Math.max(0, options.startTime ?? 0);
      void audio.play().catch((err) => {
        finish();
        setError(err instanceof Error ? err.message : t('error.playAudio'));
      });
    };

    audio.addEventListener('timeupdate', stopAtEndTime);
    audio.addEventListener('ended', finish, { once: true });
    audio.addEventListener('error', finish, { once: true });

    if (audio.readyState >= HTMLMediaElement.HAVE_METADATA) {
      startPlayback();
    } else {
      audio.addEventListener('loadedmetadata', startPlayback, { once: true });
      audio.load();
    }
  }, [stopItemAudio, t]);

  const prepareItemTtsSettings = useCallback(async () => {
    if (!id) return;

    await updateTtsSettings({
      sessionId: id,
      format,
      emotionScale: emotionScale[0],
      speechRate: speechRate[0],
      loudnessRate: loudnessRate[0],
      speakerMappings: speakerMappings.map((mapping) => ({
        conversation_speaker: mapping.speaker,
        provider_speaker_id: mapping.voice,
      })),
    });
  }, [id, format, emotionScale, speechRate, loudnessRate, speakerMappings]);

  const handlePlayOriginal = useCallback(async (item: RevisionItem) => {
    if (!id) return;
    setError(null);
    setPlayingOriginalItemId(item.id);

    if (session?.audioUrl) {
      playAudio(new Audio(session.audioUrl), {
        startTime: item.startTime,
        endTime: item.endTime,
        onFinish: () => setPlayingOriginalItemId((current) => current === item.id ? null : current),
      });
      return;
    }

    try {
      await prepareItemTtsSettings();
      const audioBlob = await generateTtsItemAudio({
        itemId: item.id,
        sessionId: id,
        content: item.originalText,
      });
      const audioUrl = URL.createObjectURL(audioBlob);
      playAudio(new Audio(audioUrl), {
        objectUrl: audioUrl,
        onFinish: () => setPlayingOriginalItemId((current) => current === item.id ? null : current),
      });
    } catch (err) {
      setPlayingOriginalItemId(null);
      setError(err instanceof Error ? err.message : t('error.playOriginalItem'));
    }
  }, [id, session?.audioUrl, playAudio, prepareItemTtsSettings, t]);

  const handleSynthesizeItem = useCallback(async (item: RevisionItem) => {
    if (!id) return;
    setSynthesizingItemId(item.id);
    setPlayingOriginalItemId(null);
    setError(null);
    try {
      await updateTtsSettings({
        sessionId: id,
        format,
        emotionScale: emotionScale[0],
        speechRate: speechRate[0],
        loudnessRate: loudnessRate[0],
        speakerMappings: speakerMappings.map((mapping) => ({
          conversation_speaker: mapping.speaker,
          provider_speaker_id: mapping.voice,
        })),
      });

      const audioBlob = await generateTtsItemAudio({
        itemId: item.id,
        sessionId: id,
        content: item.fullText,
      });

      const audioUrl = URL.createObjectURL(audioBlob);
      playAudio(new Audio(audioUrl), { objectUrl: audioUrl });
    } catch (err) {
      setError(err instanceof Error ? err.message : t('error.synthesizeItemAudio'));
    } finally {
      setSynthesizingItemId(null);
    }
  }, [id, format, emotionScale, speechRate, loudnessRate, speakerMappings, playAudio, t]);

  const handleMappingChange = useCallback((speaker: string, voice: string) => {
    setSpeakerMappings(prev => {
      const exists = prev.some(mapping => mapping.speaker === speaker);
      if (!exists) {
        return [...prev, { speaker, voice }];
      }
      return prev.map(mapping => mapping.speaker === speaker ? { ...mapping, voice } : mapping);
    });
  }, []);

  const speakers = useMemo(() => [...new Set(revision.map(r => r.speaker))], [revision]);
  const isScriptGenerationRoute = revision.length === 0 && session?.type === 'ai_script' && (isPreparingScript || !!scriptJobId || !!scriptGenerationId);
  const isWaitingForScript = isScriptGenerationRoute && !error;
  const shouldShowRevisionControls = !isScriptGenerationRoute;
  const translationNeedsUpdate = dirtyTranslationItemIds.size > 0;
  const isTranslationBusy = isStartingTranslation || revisionTranslation.isTranslating;

  if (!session && !notFound) {
    return <div className="text-[13px] text-slate-500">{t('revise.loading')}</div>;
  }

  if (!session) return <NotFound />;

  return (
    <div className="space-y-6">
      <SessionFlowNav
        sessionId={session.id}
        currentStep="revise"
        canRevise={true}
        canListen={!!session.synthesizedAudioUrl}
      />

      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">{t('revise.title')}</h1>
          <p className="text-[13px] text-slate-500 mt-0.5">
            {isWaitingForScript
              ? t('revise.scriptGenerating')
              : isRevising
                ? revisionProgress
                  ? t('revise.progressSummary', { covered: revisionProgress.coveredUtterances, total: revisionProgress.totalUtterances })
                  : t('revise.analyzingSections')
                : t('revise.utterancesReady', { count: revision.length })}
          </p>
        </div>
        {shouldShowRevisionControls && (
          <TranslationButton
            active={showAllTranslations}
            isTranslating={isTranslationBusy}
            failed={revisionTranslation.translation?.status_name === 'failed' || revisionTranslation.hasStuckItems}
            onClick={() => {
              if (revisionTranslation.translation?.status_name === 'failed' || revisionTranslation.hasStuckItems) {
                void handleUpdateTranslation();
                return;
              }
              setShowAllTranslations((current) => !current);
            }}
            className="shrink-0"
          />
        )}
      </div>

      {isWaitingForScript && (
        <div className="bg-white rounded-xl border border-slate-200 p-8 shadow-sm">
          <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-50 text-indigo-500">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
          <div className="text-center">
            <h3 className="text-[14px] font-bold text-slate-800">
              {scriptProgress.isPlanning
                ? t('revise.scriptPlanning')
                : scriptProgress.activeSection
                  ? t('revise.scriptGeneratingSection', { current: scriptProgress.activeSection.index, total: scriptProgress.sections.length })
                  : t('revise.generatingScript')}
            </h3>
            <p className="mt-1 text-[12px] text-slate-500">
              {scriptProgress.isPlanning
                ? t('revise.scriptPlanningHelp')
                : scriptProgress.sections.length > 0
                  ? t('revise.scriptProgressItems', { generated: scriptPreviewItems.length, total: scriptProgress.totalTurns })
                  : scriptPreviewItems.length > 0 ? t('revise.turnsGenerated', { count: scriptPreviewItems.length }) : t('revise.preparingFirstRevision')}
            </p>
          </div>

          {scriptProgress.sections.length > 0 && (
            <div className="mt-6">
              <SectionGenerationProgress
                title={t('revise.scriptPlanReady')}
                percent={scriptProgress.percent}
                sections={scriptProgress.sections}
                fallbackTitle={t('revise.scriptSectionFallback')}
                statusLabels={buildSectionStatusLabels(t)}
                renderProgress={(section) => t('revise.scriptSectionProgress', { generated: section.generatedCount, total: section.targetCount })}
              />
            </div>
          )}

          {scriptPreviewItems.length > 0 && (
            <div className="mt-6 space-y-3">
              {scriptPreviewItems.map((item) => (
                <div key={item.seq} className="rounded-lg border border-slate-100 bg-slate-50/70 px-4 py-3">
                  <div className="mb-1.5 flex items-center gap-2">
                    <span className="text-[11px] font-bold text-indigo-500">{item.speaker}</span>
                    {item.cue && (
                      <span className="rounded-md border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                        [{item.cue}]
                      </span>
                    )}
                  </div>
                  <p className="text-[13px] leading-relaxed text-slate-700">{item.text}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* AI Revise */}
      {shouldShowRevisionControls && (
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
        <div className="flex items-center gap-2 mb-3">
          <Wand2 className="w-4 h-4 text-indigo-500" />
          <h3 className="text-[13px] font-bold text-slate-800">{t('revise.aiRevise')}</h3>
        </div>
        <p className="text-[12px] text-slate-500 mb-3">{t('revise.aiHelp')}</p>
        <div className="flex items-start gap-3">
          <Textarea
            ref={userPromptTextareaRef}
            value={userPrompt}
            onChange={(e) => setUserPrompt(e.target.value)}
            placeholder={t('revise.aiPlaceholder')}
            className="min-h-[72px] flex-1 resize-none overflow-hidden border-slate-200 text-[13px]"
            rows={2}
          />
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-flex">
                <Button
                  onClick={handleReviseByAI}
                  disabled={isRevising}
                  aria-label={t('revise.aiReviseTooltip')}
                  className="h-[72px] bg-indigo-500 px-5 text-white hover:bg-indigo-600 disabled:opacity-60"
                >
                  {isRevising ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" sideOffset={6}>
              {t('revise.aiReviseTooltip')}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
      )}

      {/* TTS Settings */}
      {shouldShowRevisionControls && (
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Volume2 className="w-4 h-4 text-indigo-500" />
            <h3 className="text-[13px] font-bold text-slate-800">{t('revise.ttsSettings')}</h3>
          </div>
          <span className="text-[10px] text-slate-400">{t('revise.voices', { count: voiceList.length > 0 ? voiceList.length : ttsVoices.length })}</span>
        </div>

        <Button
          onClick={handleSynthesize}
          disabled={isSynthesizing || isRevising}
          className="w-full bg-indigo-500 hover:bg-indigo-600 text-white h-10 text-[12px] font-semibold mb-5 disabled:opacity-60"
        >
          {isSynthesizing ? (
            <span className="flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> {t('revise.synthesizing')}</span>
          ) : (
            <span className="flex items-center gap-2"><Volume2 className="w-4 h-4" /> {t('revise.synthesizeAll')}</span>
          )}
        </Button>

        <div className="grid grid-cols-2 gap-4 mb-5">
          <div>
            <Label className="text-[11px] font-semibold text-slate-600 mb-1.5 block">{t('common.format')}</Label>
            <Select value={format} onValueChange={setFormat}>
              <SelectTrigger className="h-9 text-[12px] border-slate-200"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="mp3">mp3</SelectItem><SelectItem value="wav">wav</SelectItem></SelectContent>
            </Select>
          </div>
          <div>
            <div className="flex justify-between mb-1"><Label className="text-[11px] font-semibold text-slate-600">{t('common.emotion')}</Label><span className="text-[10px] text-slate-400">{emotionScale[0].toFixed(1)}</span></div>
            <Slider value={emotionScale} onValueChange={setEmotionScale} min={TTS_PARAM_RANGES.emotionScale.min} max={TTS_PARAM_RANGES.emotionScale.max} step={TTS_PARAM_RANGES.emotionScale.step} />
          </div>
          <div>
            <div className="flex justify-between mb-1"><Label className="text-[11px] font-semibold text-slate-600">{t('common.speechRate')}</Label><span className="text-[10px] text-slate-400">{speechRate[0]}</span></div>
            <Slider value={speechRate} onValueChange={setSpeechRate} min={TTS_PARAM_RANGES.speechRate.min} max={TTS_PARAM_RANGES.speechRate.max} step={TTS_PARAM_RANGES.speechRate.step} />
          </div>
          <div>
            <div className="flex justify-between mb-1"><Label className="text-[11px] font-semibold text-slate-600">{t('common.loudness')}</Label><span className="text-[10px] text-slate-400">{loudnessRate[0]}</span></div>
            <Slider value={loudnessRate} onValueChange={setLoudnessRate} min={TTS_PARAM_RANGES.loudnessRate.min} max={TTS_PARAM_RANGES.loudnessRate.max} step={TTS_PARAM_RANGES.loudnessRate.step} />
          </div>
        </div>

        <SpeakerSelect speakers={speakers} mappings={speakerMappings} onMappingChange={handleMappingChange} voices={voiceList} />
      </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">
          {error}
        </div>
      )}

      {/* Revision Cards */}
      {shouldShowRevisionControls && (
      <div>
        {revision.length > 0 ? (
          <>
            {isRevising && (
              <RevisionProgressPanel
                progress={revisionProgress}
                itemCount={revision.length}
                t={t}
              />
            )}
            {revision.map(item => {
          const translationItem = revisionTranslation.itemsByKey.get(item.id);
          const translationItemDirty = dirtyTranslationItemIds.has(item.id);
          const translationItemSyncing = syncingTranslationItemIds.has(item.id);
          return (
            <RevisionCard
              key={item.id}
              item={item}
              voice={getVoiceForSpeaker(item.speaker, speakerMappings, voiceList)}
              onUpdate={handleUpdateRevision}
              onPlayOriginal={handlePlayOriginal}
              onSynthesize={handleSynthesizeItem}
              isPlayingOriginal={playingOriginalItemId === item.id}
              isSynthesizing={synthesizingItemId === item.id}
              translationText={translationItem?.translated_text}
              translationStatus={
                translationItemSyncing
                  ? 'generating'
                  : revisionTranslation.hasStuckItems && translationItem?.status_name === 'generating'
                  ? 'failed'
                  : translationItem?.status_name ?? revisionTranslation.translation?.status_name
              }
              translationStale={translationItemDirty}
              showTranslation={showAllTranslations}
              onRetryTranslation={() => void handleUpdateTranslation(item.id)}
              showAssessment={session.type !== 'ai_script'}
            />
          );
            })}
          </>
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
            {isRevising ? (
              <RevisionProgressPanel progress={revisionProgress} itemCount={0} t={t} />
            ) : (
              <p className="text-[13px] text-slate-400">{t('revise.noRevision')}</p>
            )}
          </div>
        )}
      </div>
      )}
    </div>
  );
}

function RevisionProgressPanel({
  progress,
  itemCount,
  t,
}: {
  progress: RevisionProgress | null;
  itemCount: number;
  t: ReturnType<typeof useI18n>['t'];
}) {
  if (!progress) {
    return (
      <div className="rounded-xl border border-indigo-100 bg-indigo-50/70 px-4 py-4 text-center">
        <div className="mx-auto mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-white text-indigo-500">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
        <p className="text-[13px] font-semibold text-slate-800">{t('revise.analyzingSections')}</p>
        <p className="mt-1 text-[12px] text-slate-500">{t('revise.preparingSuggestions')}</p>
      </div>
    );
  }

  return (
    <div className="mb-4">
      <SectionGenerationProgress
        title={
          progress.sections.length > 1 && progress.activeSection
            ? t('revise.progressSection', { current: progress.activeSection.index, total: progress.sections.length })
            : t('revise.revisingTranscript')
        }
        percent={progress.percent}
        sections={progress.sections}
        fallbackTitle={t('revise.scriptSectionFallback')}
        statusLabels={buildSectionStatusLabels(t)}
        renderProgress={(section) => t('revise.revisionSectionProgress', { generated: section.generatedCount, total: section.targetCount, items: itemCount })}
      />
    </div>
  );
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function isRevisionGenerating(statusName: string): boolean {
  return statusName === 'pending' || statusName === 'generating';
}

function isSynthesisRunning(synthesis: TtsSynthesisResponse): boolean {
  return synthesis.status_name === 'pending' || synthesis.status_name === 'generating';
}

type RevisionProgress = {
  totalUtterances: number;
  coveredUtterances: number;
  percent: number;
  sections: SectionGenerationProgressItem[];
  activeSection?: SectionGenerationProgressItem;
};

type ScriptGenerationProgress = {
  totalTurns: number;
  generatedTurns: number;
  percent: number;
  sections: SectionGenerationProgressItem[];
  activeSection?: SectionGenerationProgressItem;
  isPlanning: boolean;
};

function buildRevisionProgress(
  transcript: ReturnType<typeof mapTranscript>,
  revision: RevisionItem[],
  planSections: RevisionPlanSectionResponse[],
): RevisionProgress | null {
  const transcriptSeqs = transcript
    .map((item) => Number(item.id))
    .filter((seq) => Number.isInteger(seq))
    .sort((left, right) => left - right);

  if (transcriptSeqs.length === 0) return null;
  if (planSections.length === 0) return null;

  const coveredSeqs = new Set<number>();
  revision.forEach((item) => {
    const seqs = item.sourceSeqs.length > 0
      ? item.sourceSeqs
      : buildSeqRange(item.sourceSeqStart, item.sourceSeqEnd);
    seqs.forEach((seq) => coveredSeqs.add(Number(seq)));
  });

  const transcriptSeqSet = new Set(transcriptSeqs);
  const sections: SectionGenerationProgressItem[] = planSections.map((section, index) => {
    const sectionSeqs = buildSeqRange(section.start_seq, section.end_seq).filter((seq) => transcriptSeqSet.has(seq));
    const coveredUtterances = sectionSeqs.filter((seq) => coveredSeqs.has(seq)).length;
    const targetCount = sectionSeqs.length || Math.max(1, section.target_utterance_count);
    const status: SectionGenerationProgressItem['status'] =
      coveredUtterances >= targetCount
        ? 'completed'
        : coveredUtterances > 0
          ? 'processing'
          : 'pending';

    return {
      index: index + 1,
      title: section.title,
      summary: section.summary,
      targetCount,
      generatedCount: coveredUtterances,
      status,
    };
  });

  const coveredUtterances = transcriptSeqs.filter((seq) => coveredSeqs.has(seq)).length;
  const activeSection =
    sections.find((section) => section.status === 'processing')
    ?? sections.find((section) => section.status === 'pending')
    ?? sections[sections.length - 1];

  return {
    totalUtterances: transcriptSeqs.length,
    coveredUtterances,
    percent: Math.min(100, Math.round((coveredUtterances / transcriptSeqs.length) * 100)),
    sections,
    activeSection,
  };
}

function buildSeqRange(startSeq: number, endSeq: number): number[] {
  if (!Number.isFinite(startSeq) || !Number.isFinite(endSeq) || startSeq > endSeq) return [];
  return Array.from({ length: endSeq - startSeq + 1 }, (_, index) => startSeq + index);
}

function normalizeScriptPlanSections(
  sections?: ScriptGenerationPlanSectionResponse[] | null,
): ScriptGenerationPlanSectionResponse[] {
  if (!Array.isArray(sections)) return [];
  return sections
    .map((section, index) => ({
      section_index: Number.isFinite(section.section_index) ? section.section_index : index + 1,
      title: String(section.title || '').trim(),
      summary: String(section.summary || '').trim(),
      target_turn_count: Number.isFinite(section.target_turn_count) ? Math.max(1, section.target_turn_count) : 1,
    }))
    .sort((left, right) => left.section_index - right.section_index);
}

function normalizeRevisionPlanSections(
  sections?: RevisionPlanSectionResponse[] | null,
): RevisionPlanSectionResponse[] {
  if (!Array.isArray(sections)) return [];
  return sections
    .map((section, index) => ({
      section_index: Number.isFinite(section.section_index) ? section.section_index : index + 1,
      title: String(section.title || '').trim(),
      summary: String(section.summary || '').trim(),
      start_seq: Number.isFinite(section.start_seq) ? section.start_seq : 0,
      end_seq: Number.isFinite(section.end_seq) ? section.end_seq : 0,
      target_utterance_count: Number.isFinite(section.target_utterance_count) ? Math.max(1, section.target_utterance_count) : 1,
    }))
    .filter((section) => section.start_seq <= section.end_seq)
    .sort((left, right) => left.section_index - right.section_index);
}

function buildScriptGenerationProgress(
  planSections: ScriptGenerationPlanSectionResponse[],
  previewItems: ScriptGenerationPreviewItemResponse[],
  targetTurnCount: number | null,
): ScriptGenerationProgress {
  const generatedTurns = previewItems.length;
  const totalTurnsFromPlan = planSections.reduce((sum, section) => sum + Math.max(0, section.target_turn_count), 0);
  const totalTurns = targetTurnCount || totalTurnsFromPlan || generatedTurns || 0;
  let generatedBeforeSection = 0;
  const sections = planSections.map((section, index) => {
    const targetTurns = Math.max(1, section.target_turn_count);
    const generatedInSection = Math.max(0, Math.min(targetTurns, generatedTurns - generatedBeforeSection));
    const status: SectionGenerationProgressItem['status'] =
      generatedTurns >= generatedBeforeSection + targetTurns
        ? 'completed'
        : generatedTurns >= generatedBeforeSection
          ? 'processing'
          : 'pending';
    generatedBeforeSection += targetTurns;
    return {
      index: index + 1,
      title: section.title,
      summary: section.summary,
      targetCount: targetTurns,
      generatedCount: generatedInSection,
      status,
    };
  });
  const activeSection =
    sections.find((section) => section.status === 'processing')
    ?? (generatedTurns > 0 ? sections.find((section) => section.status === 'pending') : undefined);

  return {
    totalTurns,
    generatedTurns,
    percent: totalTurns > 0 ? Math.min(100, Math.round((generatedTurns / totalTurns) * 100)) : 0,
    sections,
    activeSection,
    isPlanning: (targetTurnCount ?? 0) > 16 && planSections.length === 0 && generatedTurns === 0,
  };
}

function buildSectionStatusLabels(t: ReturnType<typeof useI18n>['t']) {
  return {
    pending: t('status.pending'),
    processing: t('status.processing'),
    completed: t('status.completed'),
    failed: t('status.failed'),
  };
}
