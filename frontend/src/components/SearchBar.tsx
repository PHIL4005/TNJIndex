import { useState } from "react"
import { Loader2Icon, SearchIcon } from "lucide-react"

import { cn } from "@/lib/utils"

const PLACEHOLDERS = [
  "一脸嫌弃",
  "被催婚时的心情",
  "假装没听见",
  "周末还要加班",
  "我妈叫我全名",
  "同事又甩锅",
] as const

type SearchBarProps = {
  value: string
  onValueChange: (value: string) => void
  /** 提交当前输入框内容（由父组件决定是否 trim / 调用 search） */
  onSubmitSearch: () => void
  loading?: boolean
  className?: string
}

export function SearchBar({
  value,
  onValueChange,
  onSubmitSearch,
  loading = false,
  className,
}: SearchBarProps) {
  const [placeholder] = useState(
    () => PLACEHOLDERS[Math.floor(Math.random() * PLACEHOLDERS.length)]!,
  )

  const hint = `试试：${placeholder}`

  const submit = () => {
    if (loading) return
    onSubmitSearch()
  }

  return (
    <div className={cn("flex w-full gap-2", className)}>
      <div className="relative min-w-0 flex-1">
        <input
          type="search"
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              submit()
            }
          }}
          placeholder={hint}
          className="h-11 w-full rounded-xl border border-border bg-surface px-4 pr-10 text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30"
          autoComplete="off"
          enterKeyHint="search"
        />
        <SearchIcon
          className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
      </div>
      <button
        type="button"
        onClick={submit}
        disabled={loading}
        className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-xl bg-accent px-5 text-sm font-medium text-white transition hover:bg-accent/90 disabled:pointer-events-none disabled:opacity-60"
      >
        {loading ? (
          <Loader2Icon className="size-4 animate-spin" aria-hidden />
        ) : null}
        搜索
      </button>
    </div>
  )
}
