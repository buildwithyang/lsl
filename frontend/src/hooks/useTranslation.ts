import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  createTranslation,
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
  /** Return the current source sentences to push when creating or retrying translation. */
  getSourceItems?: () => TranslationSourceItemInput[]
}

export function useTranslation({
  sourceType,
  sourceEntityId,
  sessionId,
  sourceLanguage,
  targetLanguage,
  enabled = true,
  getSourceItems,
}: UseTranslationParams) {
  const [translation, setTranslation] = useState<TranslationResponse | null>(null)
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
      if (isMissingTranslationError(err)) {
        const items = getSourceItems?.()
        if (!items || items.length === 0) {
          if (requestSeqRef.current === seq) {
            setError(err instanceof Error ? err.message : 'Failed to load translation')
          }
          return null
        }
        const created = await createTranslation({
          sourceType,
          sourceEntityId,
          sessionId: sessionId ?? undefined,
          sourceLanguage,
          targetLanguage,
          items,
        })
        if (requestSeqRef.current === seq) {
          setTranslation(created)
        }
        return created
      }
      if (requestSeqRef.current === seq) {
        setError(err instanceof Error ? err.message : 'Failed to load translation')
      }
      return null
    }
  }, [canLoad, sourceType, sourceEntityId, sessionId, sourceLanguage, targetLanguage, getSourceItems])

  const retry = useCallback(async () => {
    if (!canLoad || !sourceType || !sourceEntityId) return null
    const seq = requestSeqRef.current + 1
    requestSeqRef.current = seq
    setError(null)
    try {
      const items = getSourceItems?.()
      if (!items || items.length === 0) {
        throw new Error('No source items available for translation')
      }
      const data = await createTranslation({
        sourceType,
        sourceEntityId,
        sessionId: sessionId ?? undefined,
        sourceLanguage,
        targetLanguage,
        items,
        force: true,
      })
      if (requestSeqRef.current === seq) {
        setTranslation(data)
      }
      return data
    } catch (err) {
      if (requestSeqRef.current === seq) {
        setError(err instanceof Error ? err.message : 'Failed to start translation')
      }
      return null
    }
  }, [canLoad, sourceType, sourceEntityId, sessionId, sourceLanguage, targetLanguage, getSourceItems])

  const translateItem = useCallback(async (item: TranslationSourceItemInput) => {
    if (!canLoad || !sourceType || !sourceEntityId) return null
    const seq = requestSeqRef.current + 1
    requestSeqRef.current = seq
    setError(null)
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
        setTranslation(data)
      }
      return data
    } catch (err) {
      if (requestSeqRef.current === seq) {
        setError(err instanceof Error ? err.message : 'Failed to translate item')
      }
      return null
    }
  }, [canLoad, sourceType, sourceEntityId, sessionId, sourceLanguage, targetLanguage])

  useEffect(() => {
    if (!canLoad) {
      requestSeqRef.current += 1
      setTranslation(null)
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
    isTranslating,
    hasStuckItems,
    error,
    reload: load,
    retry,
    translateItem,
  }
}
