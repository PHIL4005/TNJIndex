import type { ItemSummary } from "@/lib/api"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

type ImageCardProps = {
  item?: ItemSummary
  className?: string
}

export function ImageCard({ item, className }: ImageCardProps) {
  if (!item) {
    return (
      <div
        className={cn(
          "mb-4 overflow-hidden rounded-xl border border-border bg-surface/60",
          className,
        )}
      >
        <Skeleton className="aspect-[4/3] w-full rounded-none" />
      </div>
    )
  }

  return (
    <article
      className={cn(
        "group mb-4 overflow-hidden rounded-xl border border-border bg-surface transition duration-150 will-change-transform hover:scale-[1.02] hover:ring-1 hover:ring-accent",
        className,
      )}
    >
      <div className="relative aspect-[4/3] overflow-hidden bg-muted">
        {item.thumbnail_url ? (
          <img
            src={item.thumbnail_url}
            alt={item.title}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <Skeleton className="h-full w-full rounded-none" />
        )}
        {item.score != null ? (
          <div className="absolute right-2 top-2 rounded-md bg-background/80 px-1.5 py-0.5 text-xs font-medium tabular-nums text-foreground backdrop-blur-sm">
            {item.score.toFixed(2)}
          </div>
        ) : null}
      </div>
    </article>
  )
}
