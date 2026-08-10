import type { ApiErrorBody } from '../api/types'

export class ApiError extends Error {
  readonly status: number
  readonly body: ApiErrorBody | null

  constructor(status: number, body: ApiErrorBody | null, message?: string) {
    super(message ?? formatApiError(body) ?? `Request failed (${status})`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

export function formatApiError(body: ApiErrorBody | null): string | null {
  if (!body) return null

  if (typeof body.detail === 'string') return body.detail
  if (Array.isArray(body.detail)) return body.detail.join(' ')

  const parts: string[] = []
  for (const [key, value] of Object.entries(body)) {
    if (key === 'detail') continue
    if (Array.isArray(value)) {
      parts.push(`${key}: ${value.join(' ')}`)
    } else if (typeof value === 'string') {
      parts.push(`${key}: ${value}`)
    }
  }
  return parts.length > 0 ? parts.join(' · ') : null
}

export function getApiBaseUrl(): string {
  const base = import.meta.env.VITE_API_BASE_URL
  if (typeof base !== 'string' || base.trim() === '') {
    throw new Error(
      'VITE_API_BASE_URL is not set. Copy frontend/.env.example to frontend/.env.',
    )
  }
  return base.replace(/\/$/, '')
}
