import { useCallback, useRef, useState } from 'react';
import { formatTime } from '@/utils/formatTime';
import type { RevisionItem } from '@/types';
import type { TtsSpeakerItem } from '@/types/api';
import { VoiceAvatar } from '@/components/VoiceAvatar';
import { Loader2, Volume2 } from 'lucide-react';
import { TranslationButton } from '@/components/translation/TranslationButton';
import { TranslationLine } from '@/components/translation/TranslationLine';
import { useI18n } from '@/i18n';

interface RevisionCardProps {
  item: RevisionItem;
  voice?: TtsSpeakerItem;
  onUpdate: (id: string, fullText: string) => void;
  onPlayOriginal: (item: RevisionItem) => void;
  onSynthesize: (item: RevisionItem) => void;
  isPlayingOriginal?: boolean;
  isSynthesizing?: boolean;
  translationText?: string | null;
  translationStatus?: string;
  showTranslation?: boolean;
  translationStale?: boolean;
  onRetryTranslation?: () => void;
  isItemTranslating?: boolean;
  showAssessment?: boolean;
}

/**
 * Split text into segments: normal text and CUE text (wrapped in [])
 */
function parseCueSegments(text: string): Array<{ type: 'cue' | 'text'; content: string }> {
  const segments: Array<{ type: 'cue' | 'text'; content: string }> = [];
  const regex = /(\[[^\]]*\])/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', content: text.slice(lastIndex, match.index) });
    }
    segments.push({ type: 'cue', content: match[1] });
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    segments.push({ type: 'text', content: text.slice(lastIndex) });
  }

  return segments;
}

export function RevisionCard({
  item,
  voice,
  onUpdate,
  onPlayOriginal,
  onSynthesize,
  isPlayingOriginal = false,
  isSynthesizing = false,
  translationText,
  translationStatus,
  showTranslation = false,
  translationStale = false,
  onRetryTranslation,
  isItemTranslating = false,
  showAssessment = true,
}: RevisionCardProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const highlightRef = useRef<HTMLDivElement>(null);
  const [showScoreDetail, setShowScoreDetail] = useState(false);
  const [showItemTranslation, setShowItemTranslation] = useState(false);
  const { t } = useI18n();

  const handleTextChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onUpdate(item.id, e.target.value);
  }, [item.id, onUpdate]);

  // Sync scroll between textarea and highlight layer
  const handleScroll = useCallback(() => {
    if (textareaRef.current && highlightRef.current) {
      highlightRef.current.scrollTop = textareaRef.current.scrollTop;
      highlightRef.current.scrollLeft = textareaRef.current.scrollLeft;
    }
  }, []);

  const segments = parseCueSegments(item.fullText);

  const scoreColor = item.score >= 90 ? 'text-emerald-600' : item.score >= 70 ? 'text-amber-600' : 'text-red-500';
  const scoreBg = item.score >= 90 ? 'bg-emerald-50' : item.score >= 70 ? 'bg-amber-50' : 'bg-red-50';
  const isTranslationGenerating = isItemTranslating || translationStatus === 'pending' || translationStatus === 'generating';
  const isTranslationFailed = translationStatus === 'failed';
  const shouldShowTranslation = showTranslation || showItemTranslation;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 hover:border-slate-300 hover:shadow-sm transition-all duration-200">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <VoiceAvatar voice={voice} fallbackLabel={item.speaker} />
          <span className="text-[11px] text-slate-400 font-mono">
            {formatTime(item.startTime)} - {formatTime(item.endTime)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <TranslationButton
            active={shouldShowTranslation}
            isTranslating={isTranslationGenerating}
            failed={isTranslationFailed}
            onClick={() => {
              if (isTranslationFailed) {
                onRetryTranslation?.();
                return;
              }
              // Not translated yet: translate just this one sentence on demand.
              if (!translationText) {
                onRetryTranslation?.();
                setShowItemTranslation(true);
                return;
              }
              setShowItemTranslation((current) => !current);
            }}
          />
          {showAssessment && (
            <button
              type="button"
              onClick={() => setShowScoreDetail((current) => !current)}
              aria-expanded={showScoreDetail}
              className={`${scoreBg} px-2.5 py-1 rounded-full border transition-colors ${
                showScoreDetail ? 'border-current' : 'border-transparent hover:border-current'
              }`}
            >
              <span className={`text-[11px] font-bold ${scoreColor}`}>{t('common.score')} {item.score}</span>
            </button>
          )}
        </div>
      </div>

      {/* Backdrop-highlight textarea: CUE + text on same line, CUE highlighted */}
      <div className="relative font-mono text-[13px] leading-relaxed rounded-lg border border-slate-200 bg-slate-50 focus-within:border-indigo-300 focus-within:ring-2 focus-within:ring-indigo-100 transition-all">
        {/* Highlight layer (non-interactive) */}
        <div
          ref={highlightRef}
          className="absolute inset-0 px-3 py-2.5 pointer-events-none overflow-hidden whitespace-pre-wrap break-words select-none z-10"
          aria-hidden="true"
        >
          {segments.map((seg, i) =>
            seg.type === 'cue' ? (
              <span key={i} className="text-[#C2410C] bg-[#FFF7ED] rounded px-0.5">
                {seg.content}
              </span>
            ) : (
              <span key={i} className="text-slate-700">{seg.content}</span>
            )
          )}
        </div>

        {/* Actual textarea for editing */}
        <textarea
          ref={textareaRef}
          value={item.fullText}
          onChange={handleTextChange}
          onScroll={handleScroll}
          className="relative z-20 w-full px-3 py-2.5 bg-transparent text-transparent caret-slate-800 resize-none focus:outline-none"
          rows={2}
          spellCheck={false}
        />
      </div>

      {shouldShowTranslation && (
        <TranslationLine text={translationText} stale={translationStale} />
      )}

      {/* Buttons */}
      <div className="flex items-center gap-2 mt-2.5">
        {showAssessment && (
          <button
            type="button"
            onClick={() => onPlayOriginal(item)}
            disabled={isPlayingOriginal}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium text-slate-500 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg transition-colors disabled:pointer-events-none disabled:opacity-60"
          >
            {isPlayingOriginal ? <Loader2 className="w-3 h-3 animate-spin" /> : <Volume2 className="w-3 h-3" />}
            {t('revisionCard.original')}
          </button>
        )}
        <button
          type="button"
          onClick={() => onSynthesize(item)}
          disabled={isSynthesizing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium text-white bg-indigo-500 hover:bg-indigo-600 rounded-lg transition-colors disabled:pointer-events-none disabled:opacity-60"
        >
          {isSynthesizing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Volume2 className="w-3 h-3" />}
          {t('revisionCard.synthesize')}
        </button>
      </div>

      {showAssessment && showScoreDetail && (
        <div className="mt-5 rounded-xl border border-slate-200 bg-white px-4 py-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{t('revisionCard.scoreDetail')}</p>

          <div className="mt-4 space-y-4">
            <div>
              <p className="text-[15px] font-semibold text-slate-900">{t('common.score')} {item.score}</p>
            </div>

            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{t('common.original')}</p>
              <p className="mt-2 text-[13px] leading-relaxed text-slate-700">{item.originalText}</p>
            </div>

            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{t('common.problems')}</p>
              {item.issueTags && item.issueTags.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {item.issueTags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-[12px] text-slate-400">{t('revisionCard.noProblems')}</p>
              )}
            </div>

            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{t('common.notes')}</p>
              <p className="mt-2 text-[13px] leading-relaxed text-slate-700">
                {item.explanations || t('revisionCard.noNotes')}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
