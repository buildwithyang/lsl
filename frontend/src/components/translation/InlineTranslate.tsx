import { Languages, Loader2, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useI18n } from '@/i18n'
import { TranslationLine } from '@/components/translation/TranslationLine'

interface InlineTranslateProps {
  /** Translated text, if this sentence has already been translated. */
  text?: string | null
  /** This sentence is currently being translated. */
  translating?: boolean
  /** The previous translation attempt for this sentence failed. */
  failed?: boolean
  /** Translate just this one sentence on demand. */
  onTranslate: () => void
  className?: string
  lineClassName?: string
}

/**
 * Renders a translated line if present, otherwise a small button that translates
 * just this one sentence on demand. Translation is never done in bulk.
 */
export function InlineTranslate({
  text,
  translating = false,
  failed = false,
  onTranslate,
  className,
  lineClassName,
}: InlineTranslateProps) {
  const { t } = useI18n()

  if (text) {
    return <TranslationLine text={text} className={lineClassName} />
  }

  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation()
        onTranslate()
      }}
      disabled={translating}
      className={cn(
        'mt-1.5 inline-flex items-center gap-1 text-[11px] font-medium text-indigo-600 transition-colors hover:text-indigo-700 disabled:pointer-events-none disabled:opacity-50',
        className,
      )}
    >
      {translating ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : failed ? (
        <RefreshCw className="h-3 w-3" />
      ) : (
        <Languages className="h-3 w-3" />
      )}
      {translating ? t('translation.translating') : failed ? t('translation.retry') : t('translation.translateLine')}
    </button>
  )
}
