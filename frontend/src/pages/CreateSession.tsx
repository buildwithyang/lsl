import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Mic, Sparkles, Headphones } from 'lucide-react';
import { AudioSessionForm } from '@/components/create-session/AudioSessionForm';
import { AiScriptSessionForm } from '@/components/create-session/AiScriptSessionForm';
import { PodcastSessionForm } from '@/components/create-session/PodcastSessionForm';
import { cn } from '@/lib/utils';
import { useI18n } from '@/i18n';

export function CreateSession() {
  const { t } = useI18n();
  const [mode, setMode] = useState<'audio' | 'ai_script' | 'podcast'>('ai_script');

  const handleModeChange = useCallback((nextMode: 'audio' | 'ai_script' | 'podcast') => {
    setMode(nextMode);
  }, []);

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <Link to="/dashboard" className="mb-4 inline-flex items-center gap-1.5 text-[12px] text-slate-500 transition-colors hover:text-indigo-600">
          <ArrowLeft className="h-3.5 w-3.5" />
          {t('create.back')}
        </Link>
        <h1 className="text-[22px] font-bold tracking-tight text-slate-900">{t('create.title')}</h1>
        <p className="mt-0.5 text-[13px] text-slate-500">{t('create.subtitle')}</p>
      </div>

      <div className="flex gap-1 rounded-xl bg-slate-100 p-1">
        <button
          onClick={() => handleModeChange('ai_script')}
          className={cn(
            'flex flex-1 items-center justify-center gap-2 rounded-lg py-2.5 text-[13px] font-medium transition-all duration-200',
            mode === 'ai_script'
              ? 'bg-white text-slate-800 shadow-sm'
              : 'text-slate-500 hover:text-slate-700'
          )}
        >
          <Sparkles className="h-4 w-4" /> {t('create.aiScript')}
        </button>
        <button
          onClick={() => handleModeChange('podcast')}
          className={cn(
            'flex flex-1 items-center justify-center gap-2 rounded-lg py-2.5 text-[13px] font-medium transition-all duration-200',
            mode === 'podcast'
              ? 'bg-white text-slate-800 shadow-sm'
              : 'text-slate-500 hover:text-slate-700'
          )}
        >
          <Headphones className="h-4 w-4" /> {t('create.podcast')}
        </button>
        <button
          onClick={() => handleModeChange('audio')}
          className={cn(
            'flex flex-1 items-center justify-center gap-2 rounded-lg py-2.5 text-[13px] font-medium transition-all duration-200',
            mode === 'audio'
              ? 'bg-white text-slate-800 shadow-sm'
              : 'text-slate-500 hover:text-slate-700'
          )}
        >
          <Mic className="h-4 w-4" /> {t('create.audioUpload')}
        </button>
      </div>

      <AiScriptSessionForm active={mode === 'ai_script'} />
      <PodcastSessionForm active={mode === 'podcast'} />
      <AudioSessionForm active={mode === 'audio'} />
    </div>
  );
}
