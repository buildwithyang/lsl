import { useState } from 'react'
import { cn } from '@/lib/utils'
import { TranslationButton } from '@/components/translation/TranslationButton'
import { TranslationLine } from '@/components/translation/TranslationLine'

interface InlineTranslationToggleProps {
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
 * A "译文" button placed at the end of a sentence that shows/hides its translation.
 * Matches the per-item translate button used on the revise page: when the sentence
 * has not been translated yet, clicking it translates just this one sentence on demand
 * and reveals the result; once translated the same button collapses or expands the line.
 * Translation is never done in bulk.
 */
export function InlineTranslationToggle({
  text,
  translating = false,
  failed = false,
  onTranslate,
  className,
  lineClassName,
}: InlineTranslationToggleProps) {
  const [visible, setVisible] = useState(false)
  const hasText = !!text
  const showLine = visible && hasText

  const handleClick = () => {
    if (failed || !hasText) {
      // Not translated yet (or the last attempt failed): translate on demand and reveal.
      onTranslate()
      setVisible(true)
      return
    }
    setVisible((current) => !current)
  }

  return (
    <div
      className={cn('mt-1.5', className)}
      onClick={(event) => event.stopPropagation()}
    >
      <TranslationButton
        active={showLine}
        isTranslating={translating}
        failed={failed}
        onClick={handleClick}
      />
      {showLine && <TranslationLine text={text} className={lineClassName} />}
    </div>
  )
}
