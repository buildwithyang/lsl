import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Headphones, Loader2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  cancelMaterialGeneration,
  confirmMaterialGeneration,
  getMaterialGeneration,
} from '@/lib/api/materials';
import type { MaterialGeneration } from '@/types/api';
import { useI18n } from '@/i18n';

const POLL_INTERVAL_MS = 1500;
const TERMINAL_STATUSES = new Set(['extracted', 'completed', 'failed', 'cancelled']);

export function PodcastPreview() {
  const { id: sessionId } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { t } = useI18n();

  const generationId = searchParams.get('material_generation_id') ?? '';
  const [generation, setGeneration] = useState<MaterialGeneration | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [actionState, setActionState] = useState<'idle' | 'confirming' | 'cancelling'>('idle');
  const [actionError, setActionError] = useState<string | null>(null);
  const stopPolling = useRef(false);

  useEffect(() => {
    if (!generationId) return;
    stopPolling.current = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const poll = async () => {
      if (stopPolling.current) return;
      try {
        const next = await getMaterialGeneration(generationId);
        setGeneration(next);
        setPollError(null);
        if (TERMINAL_STATUSES.has(next.status_name)) {
          return;
        }
      } catch (err) {
        setPollError(err instanceof Error ? err.message : String(err));
      }
      timer = setTimeout(poll, POLL_INTERVAL_MS);
    };
    void poll();
    return () => {
      stopPolling.current = true;
      if (timer) clearTimeout(timer);
    };
  }, [generationId]);

  const handleConfirm = useCallback(async () => {
    if (!generationId) return;
    setActionState('confirming');
    setActionError(null);
    try {
      const result = await confirmMaterialGeneration(generationId);
      const scriptGenerationId = result.script_generation_id;
      if (!scriptGenerationId || !sessionId) {
        navigate(`/session/${sessionId}`);
        return;
      }
      const params = new URLSearchParams({ generation_id: scriptGenerationId });
      if (result.job_id) params.set('job_id', result.job_id);
      navigate(`/session/${sessionId}/revise?${params.toString()}`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
      setActionState('idle');
    }
  }, [generationId, navigate, sessionId]);

  const handleCancel = useCallback(async () => {
    if (!generationId) return;
    setActionState('cancelling');
    setActionError(null);
    try {
      await cancelMaterialGeneration(generationId);
      navigate('/dashboard');
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
      setActionState('idle');
    }
  }, [generationId, navigate]);

  if (!generationId) {
    return (
      <div className="max-w-2xl py-8">
        <p className="text-[13px] text-red-500">Missing material_generation_id in URL.</p>
        <Link to="/dashboard" className="text-[12px] text-indigo-600 hover:underline">
          {t('podcastPreview.backToDashboard')}
        </Link>
      </div>
    );
  }

  const status = generation?.status_name;

  return (
    <div className="max-w-2xl space-y-6 py-2">
      <div>
        <Link
          to="/dashboard"
          className="mb-3 inline-flex items-center gap-1.5 text-[12px] text-slate-500 transition-colors hover:text-indigo-600"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {t('podcastPreview.backToDashboard')}
        </Link>
        <h1 className="text-[22px] font-bold tracking-tight text-slate-900">{t('podcastPreview.title')}</h1>
        <p className="mt-1 text-[13px] text-slate-500">{t('podcastPreview.subtitle')}</p>
      </div>

      {pollError && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-[12px] text-amber-700">
          {pollError}
        </div>
      )}

      {(status === 'pending' || status === 'extracting' || !generation) && (
        <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-6 text-[13px] text-slate-600 shadow-sm">
          <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
          {t('podcastPreview.extracting')}
        </div>
      )}

      {status === 'failed' && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-[13px] text-red-700 shadow-sm">
          <p className="font-semibold">{t('podcastPreview.failed')}</p>
          {generation?.error_message && <p className="mt-1 text-[12px]">{generation.error_message}</p>}
        </div>
      )}

      {status === 'cancelled' && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-5 text-[13px] text-slate-600 shadow-sm">
          {t('podcastPreview.cancelled')}
        </div>
      )}

      {(status === 'extracted' || status === 'completed') && generation && (
        <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              {t('podcastPreview.extractedTitle')}
            </label>
            <p className="mt-1 text-[14px] font-medium text-slate-900">
              {generation.extracted_title || '—'}
            </p>
          </div>
          <div>
            <div className="flex items-baseline justify-between">
              <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                {t('podcastPreview.extractedText')}
              </label>
              <span className="text-[11px] text-slate-400">
                {t('podcastPreview.charCount').replace('{count}', String((generation.extracted_text || '').length))}
              </span>
            </div>
            <div className="mt-1 max-h-96 overflow-y-auto whitespace-pre-wrap rounded-md border border-slate-100 bg-slate-50 p-3 text-[12px] leading-relaxed text-slate-700">
              {generation.extracted_text || '—'}
            </div>
          </div>

          {actionError && <p className="text-[12px] text-red-500">{actionError}</p>}

          {status === 'extracted' && (
            <div className="flex gap-2 pt-2">
              <Button
                onClick={handleConfirm}
                disabled={actionState !== 'idle'}
                className="h-10 flex-1 bg-indigo-500 text-[13px] font-semibold text-white hover:bg-indigo-600 disabled:opacity-60"
              >
                {actionState === 'confirming' ? (
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
                disabled={actionState !== 'idle'}
                className="h-10 border-slate-200 px-4 text-[13px] text-slate-600 hover:bg-slate-100 disabled:opacity-60"
              >
                {actionState === 'cancelling' ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" /> {t('podcastPreview.cancelling')}
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <X className="h-4 w-4" /> {t('podcastPreview.cancel')}
                  </span>
                )}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
