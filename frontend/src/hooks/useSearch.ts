import { useCallback, useEffect, useRef, useState } from "react"

import { fetchImageSearch, fetchSearch, type ItemSummary } from "@/lib/api"

const PAGE_SIZE = 20

export type ResultMode = "text" | "image"

export function useSearch() {
  const [items, setItems] = useState<ItemSummary[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState("")
  const [activeTags, setActiveTags] = useState<string[]>([])
  const [resultMode, setResultMode] = useState<ResultMode>("text")
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null)

  const requestIdRef = useRef(0)
  const previewRef = useRef<string | null>(null)

  const revokePreview = useCallback(() => {
    if (previewRef.current) {
      URL.revokeObjectURL(previewRef.current)
      previewRef.current = null
    }
    setImagePreviewUrl(null)
  }, [])

  const runSearch = useCallback(
    async (q: string, tags: string[], offset: number, append: boolean) => {
      const requestId = ++requestIdRef.current
      const isPaging = append && offset > 0

      if (isPaging) {
        setLoadingMore(true)
      } else {
        setLoading(true)
        setError(null)
      }

      try {
        const data = await fetchSearch(q, tags, PAGE_SIZE, offset)
        if (requestId !== requestIdRef.current) return

        setTotal(data.total)
        if (append) {
          setItems((prev) => [...prev, ...data.results])
        } else {
          setItems(data.results)
        }
      } catch (e) {
        if (requestId !== requestIdRef.current) return
        const message = e instanceof Error ? e.message : "网络请求失败"
        setError(message)
      } finally {
        if (requestId !== requestIdRef.current) return
        if (isPaging) {
          setLoadingMore(false)
        } else {
          setLoading(false)
        }
      }
    },
    [],
  )

  const runImageSearch = useCallback(
    async (file: File, offset: number, append: boolean) => {
      const requestId = ++requestIdRef.current
      const isPaging = append && offset > 0

      if (isPaging) {
        setLoadingMore(true)
      } else {
        setLoading(true)
        setError(null)
      }

      try {
        const data = await fetchImageSearch(file, PAGE_SIZE, offset)
        if (requestId !== requestIdRef.current) return

        setTotal(data.total)
        if (append) {
          setItems((prev) => [...prev, ...data.results])
        } else {
          setItems(data.results)
        }
      } catch (e) {
        if (requestId !== requestIdRef.current) return
        const message = e instanceof Error ? e.message : "网络请求失败"
        setError(message)
      } finally {
        if (requestId !== requestIdRef.current) return
        if (isPaging) {
          setLoadingMore(false)
        } else {
          setLoading(false)
        }
      }
    },
    [],
  )

  const search = useCallback(
    (q: string, tags: string[] = []) => {
      revokePreview()
      setImageFile(null)
      setResultMode("text")
      setQuery(q)
      setActiveTags(tags)
      void runSearch(q, tags, 0, false)
    },
    [revokePreview, runSearch],
  )

  const searchByImage = useCallback(
    (file: File) => {
      revokePreview()
      const url = URL.createObjectURL(file)
      previewRef.current = url
      setImagePreviewUrl(url)
      setImageFile(file)
      setResultMode("image")
      setQuery("")
      setActiveTags([])
      void runImageSearch(file, 0, false)
    },
    [revokePreview, runImageSearch],
  )

  const clearImageSearch = useCallback(() => {
    revokePreview()
    setImageFile(null)
    setResultMode("text")
    setQuery("")
    setActiveTags([])
    void runSearch("", [], 0, false)
  }, [revokePreview, runSearch])

  const loadMore = useCallback(() => {
    if (loading || loadingMore) return
    if (items.length >= total) return
    if (resultMode === "image") {
      if (!imageFile) return
      void runImageSearch(imageFile, items.length, true)
      return
    }
    void runSearch(query, activeTags, items.length, true)
  }, [
    activeTags,
    imageFile,
    items.length,
    loading,
    loadingMore,
    query,
    resultMode,
    runImageSearch,
    runSearch,
    total,
  ])

  useEffect(() => {
    void runSearch("", [], 0, false)
  }, [runSearch])

  useEffect(
    () => () => {
      if (previewRef.current) {
        URL.revokeObjectURL(previewRef.current)
      }
    },
    [],
  )

  return {
    items,
    total,
    loading,
    loadingMore,
    error,
    query,
    activeTags,
    resultMode,
    imagePreviewUrl,
    search,
    searchByImage,
    clearImageSearch,
    loadMore,
  }
}
