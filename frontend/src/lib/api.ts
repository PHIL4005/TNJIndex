/** Types aligned with `backend/schemas.py` */

export type ItemSummary = {
  id: number
  title: string
  thumbnail_url: string | null
  tags: string[]
  score: number | null
}

export type ItemDetail = {
  id: number
  title: string
  image_url: string | null
  thumbnail_url: string | null
  tags: string[]
  description: string | null
  composition: string | null
}

export type TagCount = {
  name: string
  count: number
}

export type SearchResponse = {
  results: ItemSummary[]
  query: string
  total: number
}

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.body = body
  }
}

async function readBody(res: Response): Promise<unknown> {
  const contentType = res.headers.get("content-type") ?? ""
  if (contentType.includes("application/json")) {
    try {
      return await res.json()
    } catch {
      return null
    }
  }
  return res.text()
}

function errorMessage(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail
    if (typeof d === "string") return d
    if (Array.isArray(d)) return JSON.stringify(d)
  }
  return `请求失败 (${status})`
}

/** GET JSON from same-origin `/api/*` (Vite dev proxy → backend). */
async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  })
  const body = await readBody(res)
  if (!res.ok) {
    throw new ApiError(errorMessage(res.status, body), res.status, body)
  }
  return body as T
}

function searchUrl(
  q: string,
  tags: string[],
  limit: number,
  offset: number,
  shuffleSeed?: number,
): string {
  const params = new URLSearchParams()
  params.set("q", q)
  for (const t of tags) {
    const s = t.trim()
    if (s) params.append("tags", s)
  }
  params.set("limit", String(limit))
  params.set("offset", String(offset))
  if (shuffleSeed != null && shuffleSeed > 0) {
    params.set("shuffle_seed", String(shuffleSeed))
  }
  return `/api/search?${params.toString()}`
}

export function fetchSearch(
  q: string,
  tags: string[],
  limit: number,
  offset: number,
  shuffleSeed?: number,
): Promise<SearchResponse> {
  return apiJson<SearchResponse>(searchUrl(q, tags, limit, offset, shuffleSeed))
}

async function apiFormPostJson<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    body: form,
    headers: {
      Accept: "application/json",
    },
  })
  const body = await readBody(res)
  if (!res.ok) {
    throw new ApiError(errorMessage(res.status, body), res.status, body)
  }
  return body as T
}

export function fetchImageSearch(
  file: File,
  limit: number,
  offset: number,
): Promise<SearchResponse> {
  const form = new FormData()
  form.append("file", file)
  const params = new URLSearchParams()
  params.set("limit", String(limit))
  params.set("offset", String(offset))
  return apiFormPostJson<SearchResponse>(`/api/search/image?${params.toString()}`, form)
}

export function fetchTags(): Promise<TagCount[]> {
  return apiJson<TagCount[]>("/api/tags")
}

export function fetchItem(id: number, init?: RequestInit): Promise<ItemDetail> {
  return apiJson<ItemDetail>(`/api/items/${id}`, init)
}
