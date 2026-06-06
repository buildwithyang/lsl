import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Headphones } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import type { Difficulty } from '@/types';
import { extractMaterial } from '@/lib/api/materials';
import type { PodcastPreviewLocationState } from '@/pages/PodcastPreview';
import { useI18n } from '@/i18n';

type PodcastSessionFormProps = {
  active: boolean;
};

const URL_PATTERN = /^https?:\/\/.+/i;

export function PodcastSessionForm({ active }: PodcastSessionFormProps) {
  const navigate = useNavigate();
  const { t, language: uiLanguage } = useI18n();

  const [url, setUrl] = useState('');
  const [sessionName, setSessionName] = useState('');
  const sessionDescription = '';
  const [targetLanguage, setTargetLanguage] = useState('en-US');
  const [steeringPrompt, setSteeringPrompt] = useState('');
  const [turnCount, setTurnCount] = useState('16');
  const speakerCount = '2';
  const difficulty: Difficulty = 'Beginner';
  const cueStyle = t('create.defaultCueStyle');
  const mustInclude = '';
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const steeringRef = useRef<HTMLTextAreaElement | null>(null);

  const clearErrors = useCallback(() => setErrors({}), []);
  const adjustHeight = useCallback((el?: HTMLTextAreaElement | null) => {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, []);

  useEffect(() => {
    if (!active) clearErrors();
  }, [active, clearErrors]);

  useEffect(() => {
    adjustHeight(steeringRef.current);
  }, [steeringPrompt, adjustHeight]);

  const handleSubmit = useCallback(async () => {
    clearErrors();
    const next: Record<string, string> = {};
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      next.url = t('validation.urlRequired');
    } else if (!URL_PATTERN.test(trimmedUrl)) {
      next.url = t('validation.urlInvalid');
    }
    if (Object.keys(next).length > 0) {
      setErrors(next);
      return;
    }
    setIsSubmitting(true);
    try {
      const extracted = await extractMaterial({
        source: { type: 'webpage', url: trimmedUrl },
      });
      const state: PodcastPreviewLocationState = {
        source: { type: 'webpage', url: trimmedUrl },
        extracted,
        formValues: {
          title: sessionName || null,
          description: sessionDescription || null,
          targetLanguage,
          cueLanguage: uiLanguage,
          prompt: steeringPrompt || null,
          turnCount: Number(turnCount),
          speakerCount: Number(speakerCount),
          difficulty,
          cueStyle,
          mustInclude: mustInclude.split(',').map((s) => s.trim()).filter(Boolean),
        },
      };
      navigate('/podcast-preview', { state });
    } catch (err) {
      console.error('Failed to extract material', err);
      setErrors({ submit: err instanceof Error ? err.message : String(err) });
    } finally {
      setIsSubmitting(false);
    }
  }, [
    clearErrors,
    cueStyle,
    difficulty,
    mustInclude,
    navigate,
    sessionDescription,
    sessionName,
    speakerCount,
    steeringPrompt,
    targetLanguage,
    t,
    turnCount,
    uiLanguage,
    url,
  ]);

  if (!active) return null;

  return (
    <div className="space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div>
        <Label className="text-[12px] font-semibold text-slate-700">
          {t('create.podcastUrl')} <span className="text-red-400">*</span>
        </Label>
        <Input
          id="podcast-url"
          value={url}
          onChange={(e) => { setUrl(e.target.value); clearErrors(); }}
          placeholder={t('create.podcastUrlPlaceholder')}
          className={`mt-1.5 h-10 border-slate-200 text-[13px] focus:border-indigo-300 ${errors.url ? 'border-red-300' : ''}`}
        />
        {errors.url && <p className="mt-1 text-[11px] text-red-500">{errors.url}</p>}
      </div>

      <div>
        <Label className="text-[12px] font-semibold text-slate-700">{t('create.targetLanguage')}</Label>
        <Select value={targetLanguage} onValueChange={setTargetLanguage}>
          <SelectTrigger id="podcast-target-lang" className="mt-1.5 h-10 border-slate-200 text-[13px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="en-US">{t('create.targetLanguage.english')}</SelectItem>
            <SelectItem value="zh-CN">{t('create.targetLanguage.chinese')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div>
        <Label className="text-[12px] font-semibold text-slate-700">{t('create.podcastLength')}</Label>
        <Select value={turnCount} onValueChange={setTurnCount}>
          <SelectTrigger id="podcast-length" className="mt-1.5 h-10 border-slate-200 text-[13px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="8">{t('create.podcastLength.short')}</SelectItem>
            <SelectItem value="16">{t('create.podcastLength.medium')}</SelectItem>
            <SelectItem value="24">{t('create.podcastLength.long')}</SelectItem>
            <SelectItem value="36">{t('create.podcastLength.extra')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div>
        <Label className="text-[12px] font-semibold text-slate-700">
          {t('create.podcastSteeringPrompt')} <span className="font-normal text-slate-400">({t('common.optional')})</span>
        </Label>
        <Textarea
          id="podcast-steering"
          ref={steeringRef}
          value={steeringPrompt}
          onChange={(e) => {
            setSteeringPrompt(e.target.value);
            adjustHeight(e.target);
          }}
          placeholder={t('create.podcastSteeringPromptPlaceholder')}
          className="mt-1.5 resize-none overflow-hidden border-slate-200 text-[13px] focus:border-indigo-300"
          rows={2}
        />
      </div>

      <div>
        <Label className="text-[12px] font-semibold text-slate-700">
          {t('create.sessionName')} <span className="font-normal text-slate-400">({t('common.optional')})</span>
        </Label>
        <Input
          id="podcast-session-name"
          value={sessionName}
          onChange={(e) => setSessionName(e.target.value)}
          placeholder={t('create.sessionNamePlaceholder')}
          className="mt-1.5 h-10 border-slate-200 text-[13px] focus:border-indigo-300"
        />
      </div>

      {errors.submit && <p className="text-[12px] text-red-500">{errors.submit}</p>}

      <Button
        onClick={handleSubmit}
        disabled={isSubmitting}
        className="h-11 w-full bg-indigo-500 text-[13px] font-semibold text-white hover:bg-indigo-600 disabled:opacity-60"
      >
        {isSubmitting ? (
          <span className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('create.extracting')}
          </span>
        ) : (
          <span className="flex items-center gap-2">
            <Headphones className="h-4 w-4" />
            {t('create.extractAndPreview')}
          </span>
        )}
      </Button>
    </div>
  );
}
