import { useEffect, useRef } from "react"

type UseInfiniteScrollOptions = {
  onLoadMore: () => void
  hasMore: boolean
  loading: boolean
  loadingMore: boolean
  /** Passed to IntersectionObserver */
  rootMargin?: string
}

/**
 * Observes a sentinel element; when it enters the viewport, calls `onLoadMore`
 * unless loading or there is no more data.
 */
export function useInfiniteScroll({
  onLoadMore,
  hasMore,
  loading,
  loadingMore,
  rootMargin = "240px",
}: UseInfiniteScrollOptions) {
  const sentinelRef = useRef<HTMLDivElement>(null)
  const onLoadMoreRef = useRef(onLoadMore)
  onLoadMoreRef.current = onLoadMore

  const gateRef = useRef({ loading, loadingMore, hasMore })
  gateRef.current = { loading, loadingMore, hasMore }

  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.some((e) => e.isIntersecting)
        if (!visible) return
        const { loading: ld, loadingMore: lm, hasMore: hm } = gateRef.current
        if (ld || lm || !hm) return
        onLoadMoreRef.current()
      },
      { root: null, rootMargin, threshold: 0 },
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [hasMore, loading, loadingMore, rootMargin])

  return sentinelRef
}
