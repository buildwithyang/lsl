import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  getTranslation,
  isMissingTranslationError,
  translateTranslationItem,
  type TranslationSourceItemInput,
} from '@/lib/api/translations'
import type { TranslationItemResponse, TranslationResponse } from '@/types/api'

type SourceType = 'transcript' | 'revision'

interface UseTranslationParams {
  sourceType?: SourceType
  sourceEntityId?: string | null
  sessionId?: string | null
  sourceLanguage?: string
  targetLanguage?: string
  enabled?: boolean
}

export function useTranslation({
  sourceType,
  sourceEntityId,
  sessionId,
  sourceLanguage,
  targetLanguage,
  enabled = true,
}: UseTranslationParams) {
  const [translation, setTranslation] = useState<TranslationResponse | null>(null)
  const [translatingKeys, setTranslatingKeys] = useState<Set<string>>(() => new Set())
  const [error, setError] = useState<string | null>(null)
  const requestSeqRef = useRef(0)

  const canLoad = enabled && !!sourceType && !!sourceEntityId

  const load = useCallback(async () => {
    if (!canLoad || !sourceType || !sourceEntityId) return null
    const seq = requestSeqRef.current + 1
    requestSeqRef.current = seq
    setError(null)
    try {
      const data = await getTranslation({ sourceType, sourceEntityId, targetLanguage })
      if (requestSeqRef.current === seq) {
        setTranslation(data)
      }
      return data
    } catch (err) {
      // Not translated yet is a normal empty state, not an error. Sentences are translated
      // on demand one at a time via translateItem — we never batch-translate on load.
      if (isMissingTranslationError(err)) {
        if (requestSeqRef.current === seq) {
          setTranslation(null)
        }
        return null
      }
      if (requestSeqRef.current === seq) {
        setError(err instanceof Error ? err.message : 'Failed to load translation')
      }
      return null
    }
  }, [canLoad, sourceType, sourceEntityId, targetLanguage])

  const translateItem = useCallback(async (item: TranslationSourceItemInput) => {
    if (!canLoad || !sourceType || !sourceEntityId) return null
    const key = item.source_item_key
    const seq = requestSeqRef.current + 1
    requestSeqRef.current = seq
    setError(null)
    setTranslatingKeys((prev) => {
      const next = new Set(prev)
      next.add(key)
      return next
    })
    try {
      const data = await translateTranslationItem({
        sourceType,
        sourceEntityId,
        sessionId: sessionId ?? undefined,
        sourceLanguage,
        targetLanguage,
        item,
      })
      if (requestSeqRef.current === seq) {
        // Merge the returned item(s) into current state so concurrent single-sentence
        // translations don't clobber each other.
        setTranslation((prev) => {
          if (!prev) return data
          const byKey = new Map(prev.items.map((existing) => [existing.source_item_key, existing]))
          for (const next of data.items) {
            byKey.set(next.source_item_key, next)
          }
          return { ...data, items: Array.from(byKey.values()) }
        })
      }
      return data
    } catch (err) {
      if (requestSeqRef.current === seq) {
        setError(err instanceof Error ? err.message : 'Failed to translate item')
      }
      return null
    } finally {
      setTranslatingKeys((prev) => {
        if (!prev.has(key)) return prev
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    }
  }, [canLoad, sourceType, sourceEntityId, sessionId, sourceLanguage, targetLanguage])

  useEffect(() => {
    if (!canLoad) {
      requestSeqRef.current += 1
      setTranslation(null)
      setTranslatingKeys(new Set())
      setError(null)
      return
    }

    void load()
  }, [canLoad, load])

  useEffect(() => {
    if (!canLoad) return
    const status = translation?.status_name
    if (status !== 'pending' && status !== 'generating') return

    const timer = window.setTimeout(() => {
      void load()
    }, 2000)

    return () => window.clearTimeout(timer)
  }, [canLoad, load, translation])

  const itemsByKey = useMemo(() => {
    const map = new Map<string, TranslationItemResponse>()
    for (const item of translation?.items ?? []) {
      map.set(item.source_item_key, item)
    }
    return map
  }, [translation])

  const isTranslating = translation?.status_name === 'pending' || translation?.status_name === 'generating'
  const hasStuckItems = !!translation
    && !isTranslating
    && translation.items.some((item) => item.status_name === 'pending' || item.status_name === 'generating')

  return {
    translation,
    itemsByKey,
    translatingKeys,
    isTranslating,
    hasStuckItems,
    error,
    reload: load,
    translateItem,
  }
}
