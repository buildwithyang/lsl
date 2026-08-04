import { Languages, Loader2, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useI18n } from '@/i18n'

interface TranslationButtonProps {
  active?: boolean
  isTranslating?: boolean
  failed?: boolean
  disabled?: boolean
  onClick: () => void
  className?: string
}

export function TranslationButton({
  active = false,
  isTranslating = false,
  failed = false,
  disabled = false,
  onClick,
  className,
}: TranslationButtonProps) {
  const { t } = useI18n()
  const icon = isTranslating
    ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
    : failed
      ? <RefreshCw className="h-3.5 w-3.5" />
      : <Languages className="h-3.5 w-3.5" />
  const label = isTranslating
    ? t('translation.translating')
    : failed
      ? t('translation.retry')
      : t('translation.short')

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || isTranslating}
      className={cn(
        'inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-[11px] font-semibold transition-colors disabled:pointer-events-none disabled:opacity-60',
        active
          ? 'border-indigo-200 bg-indigo-50 text-indigo-700'
          : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50 hover:text-slate-700',
        className
      )}
    >
      {icon}
      {label}
    </button>
  )
}
