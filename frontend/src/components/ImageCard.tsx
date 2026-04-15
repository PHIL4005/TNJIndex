import type { ItemSummary } from "@/lib/api"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

type ImageCardProps = {
  item?: ItemSummary
  className?: string
  onSelect?: (id: number) => void
}

export function ImageCard({ item, className, onSelect }: ImageCardProps) {
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

  const cardInner = (
    <>
      <div className="relative overflow-hidden bg-muted">
        {item.thumbnail_url ? (
          <img
            src={item.thumbnail_url}
            alt={item.title}
            loading="lazy"
            className="block h-auto w-full"
          />
        ) : (
          <Skeleton className="aspect-[4/3] w-full rounded-none" />
        )}
        {item.score != null ? (
          <div className="pointer-events-none absolute right-2 top-2 rounded-md bg-background/80 px-1.5 py-0.5 text-xs font-medium tabular-nums text-foreground backdrop-blur-sm">
            {item.score.toFixed(2)}
          </div>
        ) : null}
      </div>
    </>
  )

  if (onSelect) {
    return (
      <button
        type="button"
        onClick={() => onSelect(item.id)}
        className={cn(
          "group mb-4 block w-full cursor-pointer overflow-hidden rounded-xl border border-border bg-surface text-left transition duration-150 will-change-transform hover:scale-[1.02] hover:ring-1 hover:ring-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
          className,
        )}
      >
        {cardInner}
      </button>
    )
  }

  return (
    <article
      className={cn(
        "group mb-4 overflow-hidden rounded-xl border border-border bg-surface transition duration-150 will-change-transform hover:scale-[1.02] hover:ring-1 hover:ring-accent",
        className,
      )}
    >
      {cardInner}
    </article>
  )
}
