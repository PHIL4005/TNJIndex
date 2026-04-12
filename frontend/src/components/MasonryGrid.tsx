import Masonry from "react-masonry-css"

import type { ItemSummary } from "@/lib/api"
import { ImageCard } from "@/components/ImageCard"
import { cn } from "@/lib/utils"

const BREAKPOINT_COLS = {
  default: 4,
  1024: 3,
  640: 2,
  480: 1,
} as const

type MasonryGridProps = {
  items: ItemSummary[]
  loading: boolean
  loadingMore: boolean
  className?: string
}

export function MasonryGrid({ items, loading, loadingMore, className }: MasonryGridProps) {
  const initialSkeleton = loading && items.length === 0
  const itemNodes = initialSkeleton
    ? Array.from({ length: 12 }, (_, i) => <ImageCard key={`sk-${i}`} />)
    : items.map((item) => <ImageCard key={item.id} item={item} />)

  const tailSkeleton =
    loadingMore && !initialSkeleton
      ? Array.from({ length: 4 }, (_, i) => <ImageCard key={`sk-more-${i}`} />)
      : []

  return (
    <Masonry
      breakpointCols={BREAKPOINT_COLS}
      className={cn(
        "masonry-root flex w-auto",
        className,
      )}
      columnClassName="masonry-col pl-4 bg-clip-padding"
    >
      {[...itemNodes, ...tailSkeleton]}
    </Masonry>
  )
}
