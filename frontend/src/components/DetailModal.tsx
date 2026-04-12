import { useEffect, useId, useState, useCallback } from "react"

import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { ApiError, fetchItem, type ItemDetail } from "@/lib/api"

type DetailModalProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  itemId: number | null
}

function pickImageSrc(detail: ItemDetail): string | null {
  return detail.image_url ?? detail.thumbnail_url
}

export function DetailModal({ open, onOpenChange, itemId }: DetailModalProps) {
  const descId = useId()
  const [detail, setDetail] = useState<ItemDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retryToken, setRetryToken] = useState(0)

  const bumpRetry = useCallback(() => {
    setRetryToken((n) => n + 1)
  }, [])

  useEffect(() => {
    if (!open || itemId == null) {
      setDetail(null)
      setLoading(false)
      setError(null)
      return
    }

    const controller = new AbortController()
    let alive = true

    setDetail(null)
    setError(null)
    setLoading(true)

    void fetchItem(itemId, { signal: controller.signal })
      .then((data) => {
        if (!alive) return
        setDetail(data)
        setLoading(false)
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted || !alive) return
        if (e instanceof ApiError) {
          setError(e.status === 404 ? "该素材不存在或已删除" : e.message)
        } else {
          setError("加载失败，请稍后重试")
        }
        setLoading(false)
      })

    return () => {
      alive = false
      controller.abort()
    }
  }, [open, itemId, retryToken])

  const titleText = detail?.title ?? "素材详情"
  const src = detail ? pickImageSrc(detail) : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        aria-describedby={descId}
        className="max-h-[min(100dvh,100vh)] gap-0 border-border p-0 sm:max-h-[min(92vh,920px)]"
      >
        <DialogTitle className="sr-only">{titleText}</DialogTitle>
        <DialogDescription id={descId} className="sr-only">
          {detail?.description ?? "查看梗图大图、标签与描述"}
        </DialogDescription>

        {error && !loading ? (
          <div className="flex flex-col items-center justify-center gap-4 px-8 py-20 text-center">
            <p className="text-sm text-muted-foreground">{error}</p>
            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                type="button"
                className="text-sm font-medium text-accent underline-offset-2 hover:underline"
                onClick={bumpRetry}
              >
                重试
              </button>
              <button
                type="button"
                className="text-sm text-muted-foreground underline-offset-2 hover:underline"
                onClick={() => onOpenChange(false)}
              >
                关闭
              </button>
            </div>
          </div>
        ) : (
          <div className="flex max-h-[min(100dvh,100vh)] flex-col overflow-hidden sm:max-h-[min(92vh,920px)] sm:flex-row sm:items-stretch">
            <div className="relative flex max-h-[60vh] min-h-[200px] w-full shrink-0 items-center justify-center bg-black sm:max-h-none sm:min-h-0 sm:max-w-[58%] sm:flex-1 sm:basis-[58%]">
              {loading ? (
                <Skeleton className="mx-auto size-full max-h-[55vh] max-w-full rounded-none bg-muted/30 sm:max-h-[min(85vh,880px)]" />
              ) : src ? (
                <img
                  src={src}
                  alt={detail?.title ?? ""}
                  className="max-h-[60vh] w-full object-contain sm:max-h-[min(85vh,880px)]"
                />
              ) : (
                <p className="px-4 text-sm text-muted-foreground">暂无大图</p>
              )}
            </div>

            <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 overflow-y-auto border-t border-border p-4 sm:border-t-0 sm:border-l sm:p-6">
              {!loading && detail ? (
                <>
                  <p className="break-all font-mono text-xs leading-relaxed text-muted-foreground">{detail.title}</p>
                  {detail.tags.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {detail.tags.map((tag) => (
                        <Badge
                          key={tag}
                          variant="secondary"
                          className="border-border bg-surface px-2.5 py-0.5 text-xs font-normal"
                        >
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                  {detail.description ? (
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{detail.description}</p>
                  ) : (
                    <p className="text-sm text-muted-foreground">暂无描述</p>
                  )}
                </>
              ) : loading ? (
                <div className="flex flex-col gap-3">
                  <Skeleton className="h-4 w-48 max-w-full" />
                  <div className="flex flex-wrap gap-2">
                    <Skeleton className="h-5 w-14 rounded-full" />
                    <Skeleton className="h-5 w-20 rounded-full" />
                    <Skeleton className="h-5 w-16 rounded-full" />
                  </div>
                  <Skeleton className="h-20 w-full" />
                </div>
              ) : null}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
