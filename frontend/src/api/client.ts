import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
} from '../auth/tokenStorage'
import type { AccessTokenResponse, ApiErrorBody } from './types'
import { ApiError, getApiBaseUrl } from './errors'

const AUTH_FAILURE_EVENT = 'cards:auth-failure'

export function onAuthFailure(listener: () => void): () => void {
  const handler = () => listener()
  window.addEventListener(AUTH_FAILURE_EVENT, handler)
  return () => window.removeEventListener(AUTH_FAILURE_EVENT, handler)
}

function emitAuthFailure(): void {
  clearTokens()
  window.dispatchEvent(new Event(AUTH_FAILURE_EVENT))
}

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown
  /** Skip Authorization header (login/register/refresh). */
  skipAuth?: boolean
  /** Internal: do not attempt another refresh after a 401. */
  _retried?: boolean
}

let refreshInFlight: Promise<string | null> | null = null

async function parseBody(response: Response): Promise<ApiErrorBody | null> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text) as ApiErrorBody
  } catch {
    return { detail: text }
  }
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight

  refreshInFlight = (async () => {
    const refresh = getRefreshToken()
    if (!refresh) {
      emitAuthFailure()
      return null
    }

    const response = await fetch(`${getApiBaseUrl()}/api/token/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ refresh }),
    })

    if (!response.ok) {
      emitAuthFailure()
      return null
    }

    const data = (await response.json()) as AccessTokenResponse
    if (!data.access) {
      emitAuthFailure()
      return null
    }

    setAccessToken(data.access)
    return data.access
  })().finally(() => {
    refreshInFlight = null
  })

  return refreshInFlight
}

/**
 * JSON API client for the Django backend.
 * Attaches Bearer access token; on 401 refreshes once and retries the request.
 */
export async function apiClient<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { body, skipAuth, _retried, headers: initHeaders, ...rest } = options
  const headers = new Headers(initHeaders)

  if (body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }

  if (!skipAuth) {
    const access = getAccessToken()
    if (access) headers.set('Authorization', `Bearer ${access}`)
  }

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...rest,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (response.status === 401 && !skipAuth && !_retried) {
    const nextAccess = await refreshAccessToken()
    if (!nextAccess) {
      throw new ApiError(401, { detail: 'Session expired. Please log in again.' })
    }
    return apiClient<T>(path, { ...options, _retried: true })
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseBody(response))
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
