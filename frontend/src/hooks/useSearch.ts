import { useCallback, useEffect, useRef, useState } from "react"

import { fetchSearch, type ItemSummary } from "@/lib/api"

const PAGE_SIZE = 20

export function useSearch() {
  const [items, setItems] = useState<ItemSummary[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState("")
  const [activeTags, setActiveTags] = useState<string[]>([])

  const requestIdRef = useRef(0)

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

  const search = useCallback(
    (q: string, tags: string[] = []) => {
      setQuery(q)
      setActiveTags(tags)
      void runSearch(q, tags, 0, false)
    },
    [runSearch],
  )

  const loadMore = useCallback(() => {
    if (loading || loadingMore) return
    if (items.length >= total) return
    void runSearch(query, activeTags, items.length, true)
  }, [activeTags, items.length, loading, loadingMore, query, runSearch, total])

  useEffect(() => {
    void runSearch("", [], 0, false)
  }, [runSearch])

  return {
    items,
    total,
    loading,
    loadingMore,
    error,
    query,
    activeTags,
    search,
    loadMore,
  }
}
