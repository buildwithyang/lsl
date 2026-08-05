import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { Play, Pause, SkipBack, SkipForward, ListRestart, Repeat, Repeat1, Volume2 } from 'lucide-react';
import { formatTime } from '@/utils/formatTime';
import { useApp } from '@/context/AppContext';
import type { RevisionItem, SpeakerMapping } from '@/types';
import type { TtsSpeakerItem } from '@/types/api';
import { SessionFlowNav } from '@/components/SessionFlowNav';
import { VoiceAvatar } from '@/components/VoiceAvatar';
import { NotFound } from './NotFound';
import { parseCueText } from '@/utils/cueParser';
import { cn } from '@/lib/utils';
import { getSession } from '@/lib/api/sessions';
import { getRevision } from '@/lib/api/revisions';
import { getTtsSettings, getTtsSpeakers, getTtsSynthesis } from '@/lib/api/tts';
import {
  applyTtsSynthesis,
  applyTtsTimelineToRevision,
  fitRevisionTimelineToAudioDuration,
  mapRevision,
  mapSessionItem,
} from '@/lib/domain';
import { getVoiceForSpeaker } from '@/lib/voice';
import { useTranslation } from '@/hooks/useTranslation';
import { InlineTranslate } from '@/components/translation/InlineTranslate';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useI18n } from '@/i18n';

type PlaybackMode = 'once' | 'repeat-all' | 'repeat-one';
type ListeningTextMode = 'hint' | 'original' | 'bilingual';

const PLAYBACK_MODES = [
  { value: 'once', labelKey: 'listening.playOnce', icon: ListRestart },
  { value: 'repeat-all', labelKey: 'listening.repeatAll', icon: Repeat },
  { value: 'repeat-one', labelKey: 'listening.repeatSentence', icon: Repeat1 },
] as const satisfies Array<{ value: PlaybackMode; labelKey: 'listening.playOnce' | 'listening.repeatAll' | 'listening.repeatSentence'; icon: typeof ListRestart }>;

const HINT_WORD_COUNT = 5;

function getSentenceHint(content: string) {
  const trimmed = content.trim();
  if (!trimmed) return '';

  const words = trimmed.split(/\s+/);
  if (words.length > 1) {
    return words.length <= HINT_WORD_COUNT
      ? trimmed
      : `${words.slice(0, HINT_WORD_COUNT).join(' ')}...`;
  }

  return trimmed.length <= 16 ? trimmed : `${trimmed.slice(0, 16)}...`;
}

function MobileSubtitleCard({
  item, index, isActive, voice, onClick, translationText, translating, translationFailed, onTranslate, mode,
}: {
  item: RevisionItem;
  index: number;
  isActive: boolean;
  voice?: TtsSpeakerItem;
  onClick: (time: number) => void;
  translationText?: string | null;
  translating?: boolean;
  translationFailed?: boolean;
  onTranslate?: () => void;
  mode: ListeningTextMode;
}) {
  const parsed = parseCueText(item.fullText);
  const cardRef = useRef<HTMLDivElement>(null);
  const isBilingual = mode === 'bilingual';
  const isHint = mode === 'hint';
  const isExpanded = isBilingual || isActive;
  const displayContent = isHint ? getSentenceHint(parsed.content) : parsed.content;

  useEffect(() => {
    if (isActive && cardRef.current) {
      cardRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [isActive]);

  return (
    <div
      ref={cardRef}
      onClick={() => onClick(item.startTime)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onClick(item.startTime);
        }
      }}
      role="button"
      tabIndex={0}
      className={cn(
        'group bg-white rounded-xl border p-3.5 cursor-pointer select-none outline-none transition-all duration-300',
        isActive
          ? 'border-indigo-300 ring-1 ring-indigo-200 shadow-md shadow-indigo-100'
          : 'border-slate-200 hover:border-slate-300 hover:shadow-sm'
      )}
    >
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-bold text-slate-500">{index + 1}</span>
        <VoiceAvatar voice={voice} fallbackLabel={item.speaker} className="h-6 w-6 text-[9px]" />
        <span className="text-[10px] text-slate-400 font-mono ml-auto">
          {formatTime(item.startTime)}
        </span>
      </div>

      <div
        className={cn(
          'grid transition-[grid-template-rows,opacity,margin-top] duration-200',
          isExpanded
            ? 'mt-2 grid-rows-[1fr] opacity-100'
            : 'grid-rows-[0fr] opacity-0 sm:group-hover:mt-2 sm:group-hover:grid-rows-[1fr] sm:group-hover:opacity-100 group-focus-visible:mt-2 group-focus-visible:grid-rows-[1fr] group-focus-visible:opacity-100'
        )}
      >
        <div className="min-h-0 overflow-hidden">
          <div className="border-t border-slate-100 pt-2">
            {!isHint && parsed.cue && (
              <span className="inline-block font-mono text-[11px] bg-amber-50 text-amber-700 border border-amber-200 rounded-md px-1.5 py-0.5 font-medium mb-1">
                [{parsed.cue}]
              </span>
            )}
            <p className={cn(
              'text-[14px] leading-relaxed',
              isHint ? 'font-medium text-slate-600' : 'text-slate-700'
            )}>
              {displayContent}
            </p>
            {isBilingual && (
              <InlineTranslate
                text={translationText}
                translating={translating}
                failed={translationFailed}
                onTranslate={() => onTranslate?.()}
                lineClassName="text-[12px]"
              />
            )}
          </div>
        </div>
      </div>

    </div>
  );
}

function TranslationModeControls({
  mode,
  onModeChange,
}: {
  mode: ListeningTextMode;
  onModeChange: (mode: ListeningTextMode) => void;
}) {
  const { t } = useI18n();

  return (
    <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1">
      {[
        { value: 'hint', label: t('listening.mode.hint'), tip: t('listening.mode.hintTip') },
        { value: 'original', label: t('listening.mode.original'), tip: t('listening.mode.originalTip') },
        { value: 'bilingual', label: t('listening.mode.bilingual'), tip: t('listening.mode.bilingualTip') },
      ].map((item) => (
        <Tooltip key={item.value}>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={() => onModeChange(item.value as ListeningTextMode)}
              aria-label={`${item.label}: ${item.tip}`}
              className={cn(
                'h-7 rounded-md px-2.5 text-[11px] font-semibold transition-colors',
                mode === item.value ? 'bg-indigo-50 text-indigo-700' : 'text-slate-500 hover:text-slate-700'
              )}
            >
              {item.label}
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" sideOffset={6}>
            {item.tip}
          </TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}

export function Listening() {
  const { id } = useParams<{ id: string }>();
  const { getSessionById, dispatch } = useApp();
  const { t, language } = useI18n();
  const [loadedSession, setLoadedSession] = useState<ReturnType<typeof getSessionById> | null>(null);
  const [notFound, setNotFound] = useState(false);

  const session = useMemo(() => loadedSession || (id ? getSessionById(id) : undefined), [id, getSessionById, loadedSession]);

  const [revision, setRevision] = useState<RevisionItem[]>([]);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [volume, setVolume] = useState(1);
  const [playbackMode, setPlaybackMode] = useState<PlaybackMode>('once');
  const [activeIndex, setActiveIndex] = useState(-1);
  const [speakerMappings, setSpeakerMappings] = useState<SpeakerMapping[]>([]);
  const [voiceList, setVoiceList] = useState<TtsSpeakerItem[]>([]);
  const [revisionId, setRevisionId] = useState<string | null>(null);
  const [translationMode, setTranslationMode] = useState<ListeningTextMode>('hint');

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const activeIndexRef = useRef(-1);

  const audioUrl = session?.synthesizedAudioUrl || session?.audioUrl;
  const shouldFitTimelineToAudioDuration = !session?.synthesizedAudioUrl;
  const revisionTranslation = useTranslation({
    sourceType: 'revision',
    sourceEntityId: revisionId,
    sessionId: id,
    targetLanguage: language,
    enabled: !!revisionId && revision.length > 0,
  });

  useEffect(() => {
    activeIndexRef.current = activeIndex;
  }, [activeIndex]);

  useEffect(() => {
    setDuration(revision.length > 0 ? revision[revision.length - 1].endTime : 0);
    setActiveIndex((current) => {
      if (revision.length === 0) {
        activeIndexRef.current = -1;
        return -1;
      }
      if (current >= 0 && current < revision.length) return current;
      activeIndexRef.current = 0;
      return 0;
    });
  }, [revision]);

  useEffect(() => {
    if (session) {
      dispatch({ type: 'SET_CURRENT_SESSION', payload: session });
      setRevision(session.revision || []);
    }
  }, [session, dispatch]);

  useEffect(() => {
    if (!id) return;
    const sessionId = id;
    let cancelled = false;

    async function loadListeningData() {
      setNotFound(false);
      try {
        const item = await getSession(sessionId);
        let nextSession = mapSessionItem(item);
        let nextRevision: RevisionItem[] = [];
        let nextSpeakerMappings: SpeakerMapping[] = [];
        let nextVoiceList: TtsSpeakerItem[] = [];
        try {
          const revisionData = await getRevision(sessionId);
          setRevisionId(revisionData.revision_id);
          nextRevision = mapRevision(revisionData);
          nextSession = { ...nextSession, revision: nextRevision, userPrompt: revisionData.user_prompt ?? undefined };
        } catch {
          // Revision must exist before listening practice has subtitles.
        }
        try {
          const synthesis = await getTtsSynthesis(sessionId);
          nextRevision = applyTtsTimelineToRevision(nextRevision, synthesis);
          nextSession = applyTtsSynthesis(nextSession, synthesis);
          nextSession = { ...nextSession, revision: nextRevision };
        } catch {
          // Audio synthesis is optional; the page can still show timed subtitles.
        }
        try {
          const settings = await getTtsSettings(sessionId);
          nextSpeakerMappings = settings.speaker_mappings.map((mapping) => ({
            speaker: mapping.conversation_speaker,
            voice: mapping.provider_speaker_id,
          }));
        } catch {
          // Speaker mapping is optional for sessions without TTS settings.
        }
        try {
          const speakers = await getTtsSpeakers();
          nextVoiceList = speakers.items;
        } catch {
          // Keep subtitles usable even if provider metadata is unavailable.
        }
        if (!cancelled) {
          setLoadedSession(nextSession);
          setSpeakerMappings(nextSpeakerMappings);
          setVoiceList(nextVoiceList);
          dispatch({ type: 'UPDATE_SESSION', payload: nextSession });
        }
      } catch {
        if (!cancelled) setNotFound(true);
      }
    }

    void loadListeningData();
    return () => {
      cancelled = true;
    };
  }, [id, dispatch]);

  // Sync audio source when URL changes
  useEffect(() => {
    const audio = audioRef.current;
    if (audio && audioUrl) {
      audio.src = audioUrl;
      audio.load();
      setCurrentTime(0);
      setDuration(revision.length > 0 ? revision[revision.length - 1].endTime : 0);
      setIsPlaying(false);
    }
  }, [audioUrl, revision]);

  // Sync playback rate
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.playbackRate = playbackRate;
    }
  }, [playbackRate]);

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = volume;
    }
  }, [volume]);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;

    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
    } else {
      if (audio.ended || audio.currentTime >= audio.duration) {
        audio.currentTime = 0;
      }
      void audio.play().catch(() => {
        // Ignore autoplay restrictions
      });
      setIsPlaying(true);
    }
  }, [isPlaying]);

  const handleSeek = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const time = Number(e.target.value);
    if (audioRef.current) {
      audioRef.current.currentTime = time;
    }
    setCurrentTime(time);
    const idx = revision.findIndex(item => time >= item.startTime && time < item.endTime);
    activeIndexRef.current = idx;
    setActiveIndex(idx);
  }, [revision]);

  const skip = useCallback((delta: number) => {
    if (audioRef.current) {
      const next = Math.min(Math.max(audioRef.current.currentTime + delta, 0), audioRef.current.duration || duration);
      audioRef.current.currentTime = next;
      setCurrentTime(next);
      const idx = revision.findIndex(item => next >= item.startTime && next < item.endTime);
      activeIndexRef.current = idx;
      setActiveIndex(idx);
    }
  }, [duration, revision]);

  const handleSentenceClick = useCallback((time: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = time;
      setCurrentTime(time);
      const idx = revision.findIndex(item => time >= item.startTime && time < item.endTime);
      activeIndexRef.current = idx;
      setActiveIndex(idx);
      void audioRef.current.play().catch(() => {
        // Ignore autoplay restrictions
      });
      setIsPlaying(true);
    }
  }, [revision]);

  const handleVolumeChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const nextVolume = Number(e.target.value);
    setVolume(nextVolume);
    if (audioRef.current) {
      audioRef.current.volume = nextVolume;
    }
  }, []);

  // Keep UI currentTime and active index in sync with audio
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTimeUpdate = () => {
      if (playbackMode === 'repeat-one') {
        const loopIndex = activeIndexRef.current;
        const loopItem = loopIndex >= 0 ? revision[loopIndex] : undefined;
        if (loopItem && audio.currentTime >= loopItem.endTime) {
          audio.currentTime = loopItem.startTime;
          setCurrentTime(loopItem.startTime);
          return;
        }
      }

      setCurrentTime(audio.currentTime);
      const idx = revision.findIndex(item => audio.currentTime >= item.startTime && audio.currentTime < item.endTime);
      setActiveIndex(idx);
    };

    const onEnded = () => {
      if (playbackMode === 'repeat-all') {
        audio.currentTime = 0;
        setCurrentTime(0);
        void audio.play().catch(() => {
          setIsPlaying(false);
        });
        return;
      }
      setIsPlaying(false);
    };

    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onLoadedMetadata = () => {
      const nextDuration = Number.isFinite(audio.duration)
        ? audio.duration
        : revision.length > 0 ? revision[revision.length - 1].endTime : 0;
      setDuration(nextDuration);
      if (shouldFitTimelineToAudioDuration && Number.isFinite(audio.duration)) {
        setRevision((current) => fitRevisionTimelineToAudioDuration(current, audio.duration));
      }
    };

    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('ended', onEnded);
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);
    audio.addEventListener('loadedmetadata', onLoadedMetadata);
    if (audio.readyState >= HTMLMediaElement.HAVE_METADATA) {
      onLoadedMetadata();
    }

    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('ended', onEnded);
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
      audio.removeEventListener('loadedmetadata', onLoadedMetadata);
    };
  }, [revision, playbackMode, shouldFitTimelineToAudioDuration]);

  if (!session && !notFound) {
    return <div className="text-[13px] text-slate-500">{t('listening.loading')}</div>;
  }

  if (!session) return <NotFound />;

  return (
    <div className="sm:space-y-6 space-y-4 pb-36 sm:pb-32">
      {/* Hidden audio element */}
      <audio ref={audioRef} preload="metadata" />

      <SessionFlowNav
        sessionId={session.id}
        currentStep="listen"
        canRevise={true}
        canListen={true}
      />

      {/* Header - hidden on mobile to save space */}
      <div className="hidden sm:block">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">{t('listening.title')}</h1>
            <p className="text-[13px] text-slate-500 mt-0.5">{t('listening.subtitle')}</p>
          </div>
          <TranslationModeControls
            mode={translationMode}
            onModeChange={setTranslationMode}
          />
        </div>
      </div>

      {/* Mobile mini header */}
      <div className="sm:hidden flex items-center justify-between">
        <h1 className="text-[16px] font-bold text-slate-800">{t('listening.mobileTitle')}</h1>
        <TranslationModeControls
          mode={translationMode}
          onModeChange={setTranslationMode}
        />
      </div>

      {/* Subtitle Cards */}
      <div className="space-y-2">
        {revision.map((item, index) => (
          <MobileSubtitleCard
            key={item.id}
            item={item}
            index={index}
            isActive={activeIndex === index}
            voice={getVoiceForSpeaker(item.speaker, speakerMappings, voiceList)}
            onClick={handleSentenceClick}
            translationText={revisionTranslation.itemsByKey.get(item.id)?.translated_text}
            translating={revisionTranslation.translatingKeys.has(item.id)}
            translationFailed={revisionTranslation.itemsByKey.get(item.id)?.status_name === 'failed'}
            onTranslate={() => void revisionTranslation.translateItem({
              source_item_key: item.id,
              source_seq: index,
              speaker: item.speaker,
              source_text: item.fullText,
            })}
            mode={translationMode}
          />
        ))}
      </div>

      {/* Fixed Player */}
      <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-slate-200 bg-white/95 backdrop-blur-lg shadow-[0_-8px_24px_rgba(15,23,42,0.08)]">
        <div className="max-w-[900px] mx-auto px-4 sm:px-6 lg:px-8 py-3 sm:py-4">
          <div className="hidden sm:block">
            <DesktopPlayer
              currentTime={currentTime}
              duration={duration}
              isPlaying={isPlaying}
              playbackRate={playbackRate}
              volume={volume}
              playbackMode={playbackMode}
              onTogglePlay={togglePlay}
              onSeek={handleSeek}
              onSkip={skip}
              onRateChange={setPlaybackRate}
              onVolumeChange={handleVolumeChange}
              onPlaybackModeChange={setPlaybackMode}
            />
          </div>
          <div className="sm:hidden">
            <MobilePlayer
              currentTime={currentTime}
              duration={duration}
              isPlaying={isPlaying}
              playbackRate={playbackRate}
              volume={volume}
              playbackMode={playbackMode}
              onTogglePlay={togglePlay}
              onSeek={handleSeek}
              onSkip={skip}
              onRateChange={setPlaybackRate}
              onVolumeChange={handleVolumeChange}
              onPlaybackModeChange={setPlaybackMode}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------- Desktop Player ---------- */
function DesktopPlayer({
  currentTime, duration, isPlaying, playbackRate, volume, playbackMode,
  onTogglePlay, onSeek, onSkip, onRateChange, onVolumeChange, onPlaybackModeChange,
}: {
  currentTime: number; duration: number; isPlaying: boolean; playbackRate: number; volume: number; playbackMode: PlaybackMode;
  onTogglePlay: () => void; onSeek: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onSkip: (d: number) => void; onRateChange: (r: number) => void;
  onVolumeChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onPlaybackModeChange: (mode: PlaybackMode) => void;
}) {
  const { t } = useI18n();

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 shadow-sm">
      <div className="flex items-center gap-4">
        <button onClick={() => onSkip(-5)} className="p-2 hover:bg-white rounded-full transition-colors" aria-label={t('common.skipBack5')}>
          <SkipBack className="w-5 h-5 text-slate-600" />
        </button>

        <button
          onClick={onTogglePlay}
          className="w-12 h-12 bg-indigo-500 hover:bg-indigo-600 rounded-full flex items-center justify-center transition-colors shadow-lg shadow-indigo-200"
          aria-label={isPlaying ? t('common.pause') : t('common.play')}
        >
          {isPlaying ? <Pause className="w-5 h-5 text-white" /> : <Play className="w-5 h-5 text-white ml-0.5" />}
        </button>

        <button onClick={() => onSkip(5)} className="p-2 hover:bg-white rounded-full transition-colors" aria-label={t('common.skipForward5')}>
          <SkipForward className="w-5 h-5 text-slate-600" />
        </button>

        <PlaybackModeMenu playbackMode={playbackMode} onPlaybackModeChange={onPlaybackModeChange} />

        <div className="flex items-center gap-2 w-36">
          <Volume2 className="w-4 h-4 text-slate-500" />
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={volume}
            onChange={onVolumeChange}
            className="w-full accent-indigo-500"
            aria-label={t('common.volume')}
          />
        </div>

        <span className="text-[11px] text-slate-500 font-mono tabular-nums w-24 text-center">
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>

        <div className="flex-1 min-w-0">
          <input
            type="range"
            min={0}
            max={duration || 0}
            value={currentTime}
            onChange={onSeek}
            className="w-full accent-indigo-500"
            aria-label={t('common.playbackPosition')}
          />
        </div>

        <select
          value={playbackRate}
          onChange={(e) => onRateChange(Number(e.target.value))}
          className="text-[11px] text-slate-600 bg-white border border-slate-200 rounded-lg px-2 py-1.5 cursor-pointer font-medium"
          aria-label={t('common.playbackSpeed')}
        >
          {[0.7, 0.8, 0.9, 1, 1.1, 1.2, 1.3, 1.4, 1.5].map(r => <option key={r} value={r}>{r}x</option>)}
        </select>
      </div>
    </div>
  );
}

/* ---------- Mobile Player ---------- */
function MobilePlayer({
  currentTime, duration, isPlaying, playbackRate, volume, playbackMode,
  onTogglePlay, onSeek, onSkip, onRateChange, onVolumeChange, onPlaybackModeChange,
}: {
  currentTime: number; duration: number; isPlaying: boolean; playbackRate: number; volume: number; playbackMode: PlaybackMode;
  onTogglePlay: () => void; onSeek: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onSkip: (d: number) => void; onRateChange: (r: number) => void;
  onVolumeChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onPlaybackModeChange: (mode: PlaybackMode) => void;
}) {
  const { t } = useI18n();

  return (
    <div className="space-y-2">
      {/* Progress */}
      <div className="flex items-center gap-2.5">
        <span className="text-[10px] text-slate-500 font-mono w-8 text-right">{formatTime(currentTime)}</span>
        <input
          type="range"
          min={0}
          max={duration || 0}
          value={currentTime}
          onChange={onSeek}
          className="flex-1 accent-indigo-500"
          aria-label={t('common.playbackPosition')}
        />
        <span className="text-[10px] text-slate-500 font-mono w-8">{formatTime(duration)}</span>
      </div>

      {/* Controls */}
      <div className="flex items-center justify-center gap-4">
        <button onClick={() => onSkip(-5)} className="p-2 active:bg-slate-100 rounded-full transition-colors" aria-label={t('common.skipBack5')}>
          <SkipBack className="w-5 h-5 text-slate-600" />
        </button>

        <button
          onClick={onTogglePlay}
          className="w-11 h-11 bg-indigo-500 active:bg-indigo-600 rounded-full flex items-center justify-center transition-colors shadow-md shadow-indigo-200"
          aria-label={isPlaying ? t('common.pause') : t('common.play')}
        >
          {isPlaying
            ? <Pause className="w-5 h-5 text-white" />
            : <Play className="w-5 h-5 text-white ml-0.5" />}
        </button>

        <button onClick={() => onSkip(5)} className="p-2 active:bg-slate-100 rounded-full transition-colors" aria-label={t('common.skipForward5')}>
          <SkipForward className="w-5 h-5 text-slate-600" />
        </button>

        <PlaybackModeMenu playbackMode={playbackMode} onPlaybackModeChange={onPlaybackModeChange} compact />

        <select
          value={playbackRate}
          onChange={(e) => onRateChange(Number(e.target.value))}
          className="text-[10px] text-slate-600 bg-slate-100 border border-slate-200 rounded-md px-1.5 py-1 cursor-pointer font-semibold"
        >
          {[0.7, 0.8, 0.9, 1, 1.1, 1.2, 1.3, 1.4, 1.5].map(r => <option key={r} value={r}>{r}x</option>)}
        </select>
      </div>

      <div className="flex items-center gap-2">
        <Volume2 className="w-4 h-4 text-slate-500" />
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={volume}
          onChange={onVolumeChange}
          className="flex-1 accent-indigo-500"
          aria-label={t('common.volume')}
        />
      </div>
    </div>
  );
}

function PlaybackModeMenu({
  playbackMode,
  onPlaybackModeChange,
  compact = false,
}: {
  playbackMode: PlaybackMode;
  onPlaybackModeChange: (mode: PlaybackMode) => void;
  compact?: boolean;
}) {
  const currentMode = PLAYBACK_MODES.find((mode) => mode.value === playbackMode) ?? PLAYBACK_MODES[0];
  const Icon = currentMode.icon;
  const { t } = useI18n();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            'inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 transition-colors hover:bg-slate-100',
            compact ? 'h-8 w-8' : 'h-9 w-9'
          )}
          aria-label={t(currentMode.labelKey)}
        >
          <Icon className={compact ? 'w-4 h-4' : 'w-5 h-5'} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="center" side="top" className="min-w-44">
        <DropdownMenuRadioGroup value={playbackMode} onValueChange={(value) => onPlaybackModeChange(value as PlaybackMode)}>
          {PLAYBACK_MODES.map((mode) => {
            const ModeIcon = mode.icon;
            return (
              <DropdownMenuRadioItem key={mode.value} value={mode.value} className="gap-2 text-[12px]">
                <ModeIcon className="w-4 h-4 text-slate-500" />
                {t(mode.labelKey)}
              </DropdownMenuRadioItem>
            );
          })}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
