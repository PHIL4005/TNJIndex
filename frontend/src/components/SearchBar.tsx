import { useRef, useState } from "react"
import { CameraIcon, Loader2Icon, SearchIcon } from "lucide-react"
import { toast } from "sonner"

import { cn } from "@/lib/utils"

const PLACEHOLDERS = [
  "一个人从高处俯视另一个倒在地上的人",
  "两人隔着东西剑拔弩张对视",
  "角色扭头背对镜头",
  "一大一小，大的追着小的跑",
  "角色正在操作一个巨大的机器/设备",
  "特写：嘴巴大张，眼睛瞪圆",
] as const

const MAX_IMAGE_BYTES = 5 * 1024 * 1024
const ALLOWED_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"])

function validateLocalImage(file: File): string | null {
  const t = (file.type || "").toLowerCase()
  if (!ALLOWED_IMAGE_TYPES.has(t)) {
    return "请上传 JPEG、PNG 或 WebP 图片"
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return "图片大小不能超过 5MB"
  }
  return null
}

type SearchBarProps = {
  value: string
  onValueChange: (value: string) => void
  /**
   * 提交搜索。无输入时若传 `fallbackQuery`，则为当前随机示例句（不含「试试：」前缀）。
   */
  onSubmitSearch: (fallbackQuery?: string) => void
  loading?: boolean
  /** 以图搜图请求进行中（控制占位符与相机位图标） */
  imageAnalyzing?: boolean
  imagePreviewUrl?: string | null
  onPickImage?: (file: File) => void
  className?: string
}

export function SearchBar({
  value,
  onValueChange,
  onSubmitSearch,
  loading = false,
  imageAnalyzing = false,
  imagePreviewUrl = null,
  onPickImage,
  className,
}: SearchBarProps) {
  const [placeholder] = useState(
    () => PLACEHOLDERS[Math.floor(Math.random() * PLACEHOLDERS.length)]!,
  )
  const fileInputRef = useRef<HTMLInputElement>(null)

  const hint = `试试：${placeholder}`
  const inputPlaceholder = imageAnalyzing ? "正在分析画面…" : hint

  const submit = () => {
    if (loading) return
    const typed = value.trim()
    if (typed) {
      onSubmitSearch()
      return
    }
    if (!imagePreviewUrl && !imageAnalyzing) {
      onSubmitSearch(placeholder)
      return
    }
    onSubmitSearch()
  }

  const openFilePicker = () => {
    if (loading || !onPickImage) return
    fileInputRef.current?.click()
  }

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.currentTarget
    const file = input.files?.[0]
    input.value = ""
    if (!file || !onPickImage) return
    const err = validateLocalImage(file)
    if (err) {
      toast.error(err)
      return
    }
    onPickImage(file)
  }

  return (
    <div className={cn("flex w-full flex-col gap-2 sm:flex-row sm:items-stretch", className)}>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="sr-only"
        aria-hidden
        tabIndex={-1}
        onChange={onFileChange}
      />

      <div className="flex min-w-0 flex-1 gap-2">
        {imagePreviewUrl ? (
          <div className="relative h-11 w-11 shrink-0 overflow-hidden rounded-xl border border-border bg-surface">
            <img
              src={imagePreviewUrl}
              alt=""
              className="size-full object-cover"
            />
            {imageAnalyzing ? (
              <div className="absolute inset-0 flex items-center justify-center bg-background/50">
                <Loader2Icon className="size-5 animate-spin text-foreground" aria-hidden />
              </div>
            ) : null}
          </div>
        ) : null}

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
            placeholder={inputPlaceholder}
            className="h-11 w-full rounded-xl border border-border bg-surface py-0 pl-4 pr-[4.5rem] text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30"
            autoComplete="off"
            enterKeyHint="search"
          />
          <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-0.5">
            {onPickImage ? (
              <button
                type="button"
                onClick={openFilePicker}
                disabled={loading}
                aria-label="以图搜索"
                className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-surface hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
              >
                {imageAnalyzing ? (
                  <Loader2Icon className="size-4 animate-spin" aria-hidden />
                ) : (
                  <CameraIcon className="size-4" aria-hidden />
                )}
              </button>
            ) : null}
            <SearchIcon className="pointer-events-none size-4 text-muted-foreground" aria-hidden />
          </div>
        </div>
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
