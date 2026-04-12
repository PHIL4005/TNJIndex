import { useCallback, useEffect, useMemo, useState } from "react"
import { ExternalLinkIcon } from "lucide-react"
import { toast } from "sonner"

import { DetailModal } from "@/components/DetailModal"
import { MasonryGrid } from "@/components/MasonryGrid"
import { SearchBar } from "@/components/SearchBar"
import { Badge } from "@/components/ui/badge"
import { useInfiniteScroll } from "@/hooks/useInfiniteScroll"
import { useSearch } from "@/hooks/useSearch"
import { fetchTags, type TagCount } from "@/lib/api"

function sortTagsByCount(tags: TagCount[]): TagCount[] {
  return [...tags].sort((a, b) => b.count - a.count)
}

function resultsHeading(
  query: string,
  activeTags: string[],
  total: number,
): string {
  const q = query.trim()
  if (activeTags.length > 0 && !q) {
    const t = activeTags[0]!
    const suffix = activeTags.length > 1 ? ` 等 ${activeTags.length} 个标签` : ""
    return `「${t}」${suffix} · ${total} 条`
  }
  if (q) {
    return `「${q}」的搜索结果 · ${total} 条`
  }
  return `全部素材 · ${total} 条`
}

export default function App() {
  const { items, total, loading, loadingMore, error, query, activeTags, search, loadMore } =
    useSearch()

  const [searchInput, setSearchInput] = useState("")
  const [topTags, setTopTags] = useState<TagCount[]>([])
  const [detailOpen, setDetailOpen] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  useEffect(() => {
    void fetchTags()
      .then((raw) => setTopTags(sortTagsByCount(raw).slice(0, 8)))
      .catch(() => {
        /* 标签区静默失败 */
      })
  }, [])

  useEffect(() => {
    if (!error) return
    toast.error("搜索出错，请稍后重试")
  }, [error])

  const hasMore = items.length < total

  const sentinelRef = useInfiniteScroll({
    onLoadMore: loadMore,
    hasMore,
    loading,
    loadingMore,
  })

  const onSubmitSearch = useCallback(() => {
    const q = searchInput.trim()
    search(q, [])
  }, [search, searchInput])

  const onTagClick = useCallback(
    (name: string) => {
      setSearchInput("")
      search("", [name])
    },
    [search],
  )

  const onSelectItem = useCallback((id: number) => {
    setSelectedId(id)
    setDetailOpen(true)
  }, [])

  const onDetailOpenChange = useCallback((open: boolean) => {
    setDetailOpen(open)
    if (!open) setSelectedId(null)
  }, [])

  const heading = useMemo(
    () => resultsHeading(query, activeTags, total),
    [query, activeTags, total],
  )

  const showEmpty =
    !loading && items.length === 0 && (query.trim().length > 0 || activeTags.length > 0)

  return (
    <div className="min-h-screen bg-background text-foreground">
      <DetailModal open={detailOpen} onOpenChange={onDetailOpenChange} itemId={selectedId} />
      <header className="sticky top-0 z-40 flex h-12 items-center border-b border-border bg-surface px-4">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4">
          <span className="text-sm font-semibold tracking-tight">TNJIndex</span>
          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground transition hover:text-foreground"
          >
            GitHub
            <ExternalLinkIcon className="size-3.5" aria-hidden />
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 pb-16 pt-10">
        <section className="mx-auto max-w-xl text-center">
          <h2 className="text-balance text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            搜一张对的梗图
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            描述场景或情绪，从索引里捞出最贴切的一张。
          </p>
          <div className="mt-6">
            <SearchBar
              value={searchInput}
              onValueChange={setSearchInput}
              onSubmitSearch={onSubmitSearch}
              loading={loading}
            />
          </div>
        </section>

        <section className="mt-10">
          <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            热门标签
          </p>
          <div className="flex flex-wrap gap-2">
            {topTags.map((t) => (
              <Badge
                key={t.name}
                asChild
                variant="secondary"
                className="cursor-pointer border-border bg-surface px-3 py-1 text-xs font-normal text-foreground hover:bg-surface/80"
              >
                <button type="button" onClick={() => onTagClick(t.name)}>
                  {t.name}
                  <span className="ml-1 tabular-nums text-muted-foreground">{t.count}</span>
                </button>
              </Badge>
            ))}
          </div>
        </section>

        <section className="mt-12">
          <div className="mb-6 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
            <h3 className="text-sm font-medium text-foreground">{heading}</h3>
            {!hasMore && items.length > 0 && !loading ? (
              <p className="text-xs text-muted-foreground">已加载全部</p>
            ) : null}
          </div>

          {showEmpty ? (
            <div className="rounded-xl border border-border bg-surface/40 px-6 py-16 text-center">
              <p className="text-sm text-foreground">没找到相关梗图，换个描述试试？</p>
              <p className="mt-2 text-xs text-muted-foreground">或从热门标签里点一个：</p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {topTags.map((t) => (
                  <Badge
                    key={`empty-${t.name}`}
                    asChild
                    variant="secondary"
                    className="cursor-pointer border-border bg-background px-3 py-1 text-xs font-normal hover:bg-background/80"
                  >
                    <button type="button" onClick={() => onTagClick(t.name)}>
                      {t.name}
                    </button>
                  </Badge>
                ))}
              </div>
            </div>
          ) : (
            <>
              <MasonryGrid
                items={items}
                loading={loading}
                loadingMore={loadingMore}
                onSelectItem={onSelectItem}
              />
              <div ref={sentinelRef} className="h-8 w-full" aria-hidden />
            </>
          )}
        </section>
      </main>
    </div>
  )
}
