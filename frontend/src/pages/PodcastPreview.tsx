import { useCallback, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeft, Headphones, Loader2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useApp } from '@/context/AppContext';
import { createPodcastSession } from '@/lib/api/materials';
import { mapSessionItem } from '@/lib/domain';
import type { Difficulty } from '@/types';
import type { ExtractedMaterialContent, MaterialSourceInput } from '@/types/api';
import { useI18n } from '@/i18n';

export interface PodcastPreviewFormValues {
  title: string | null;
  description: string | null;
  targetLanguage: string;
  cueLanguage: string | null;
  prompt: string | null;
  turnCount: number;
  speakerCount: number;
  difficulty: Difficulty;
  cueStyle: string;
  mustInclude: string[];
}

export interface PodcastPreviewLocationState {
  source: MaterialSourceInput;
  extracted: ExtractedMaterialContent;
  formValues: PodcastPreviewFormValues;
}

export function PodcastPreview() {
  const location = useLocation();
  const navigate = useNavigate();
  const { dispatch } = useApp();
  const { t } = useI18n();

  const state = (location.state ?? null) as PodcastPreviewLocationState | null;
  const [generating, setGenerating] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const handleGenerate = useCallback(async () => {
    if (!state) return;
    setGenerating(true);
    setActionError(null);
    try {
      const result = await createPodcastSession({
        source: state.source,
        extractedTitle: state.extracted.title,
        extractedText: state.extracted.main_text,
        title: state.formValues.title,
        description: state.formValues.description,
        targetLanguage: state.formValues.targetLanguage,
        cueLanguage: state.formValues.cueLanguage,
        prompt: state.formValues.prompt,
        turnCount: state.formValues.turnCount,
        speakerCount: state.formValues.speakerCount,
        difficulty: state.formValues.difficulty,
        cueStyle: state.formValues.cueStyle,
        mustInclude: state.formValues.mustInclude,
      });
      const session = mapSessionItem(result.session);
      dispatch({ type: 'ADD_SESSION', payload: session });
      const params = new URLSearchParams({ generation_id: result.generation.generation_id });
      if (result.job?.job_id) params.set('job_id', result.job.job_id);
      navigate(`/session/${session.id}/revise?${params.toString()}`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
      setGenerating(false);
    }
  }, [dispatch, navigate, state]);

  const handleCancel = useCallback(() => {
    navigate('/dashboard');
  }, [navigate]);

  if (!state) {
    return (
      <div className="max-w-2xl py-8">
        <p className="text-[13px] text-red-500">{t('podcastPreview.missingState')}</p>
        <Link to="/create" className="text-[12px] text-indigo-600 hover:underline">
          {t('podcastPreview.backToCreate')}
        </Link>
      </div>
    );
  }

  const { extracted } = state;

  return (
    <div className="max-w-2xl space-y-6 py-2">
      <div>
        <Link
          to="/create"
          className="mb-3 inline-flex items-center gap-1.5 text-[12px] text-slate-500 transition-colors hover:text-indigo-600"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {t('podcastPreview.backToCreate')}
        </Link>
        <h1 className="text-[22px] font-bold tracking-tight text-slate-900">{t('podcastPreview.title')}</h1>
        <p className="mt-1 text-[13px] text-slate-500">{t('podcastPreview.subtitle')}</p>
      </div>

      <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {t('podcastPreview.extractedTitle')}
          </label>
          <p className="mt-1 text-[14px] font-medium text-slate-900">
            {extracted.title || '—'}
          </p>
        </div>
        <div>
          <div className="flex items-baseline justify-between">
            <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              {t('podcastPreview.extractedText')}
            </label>
            <span className="text-[11px] text-slate-400">
              {t('podcastPreview.charCount').replace('{count}', String(extracted.char_count))}
            </span>
          </div>
          <div className="mt-1 max-h-96 overflow-y-auto whitespace-pre-wrap rounded-md border border-slate-100 bg-slate-50 p-3 text-[12px] leading-relaxed text-slate-700">
            {extracted.main_text || '—'}
          </div>
        </div>

        {actionError && <p className="text-[12px] text-red-500">{actionError}</p>}

        <div className="flex gap-2 pt-2">
          <Button
            onClick={handleGenerate}
            disabled={generating}
            className="h-10 flex-1 bg-indigo-500 text-[13px] font-semibold text-white hover:bg-indigo-600 disabled:opacity-60"
          >
            {generating ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" /> {t('podcastPreview.confirming')}
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <Headphones className="h-4 w-4" /> {t('podcastPreview.generate')}
              </span>
            )}
          </Button>
          <Button
            variant="outline"
            onClick={handleCancel}
            disabled={generating}
            className="h-10 border-slate-200 px-4 text-[13px] text-slate-600 hover:bg-slate-100 disabled:opacity-60"
          >
            <span className="flex items-center gap-2">
              <X className="h-4 w-4" /> {t('podcastPreview.cancel')}
            </span>
          </Button>
        </div>
      </div>
    </div>
  );
}
