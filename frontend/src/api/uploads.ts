import { apiClient, apiFormData } from './client'
import { ApiError } from './errors'
import type { ApiErrorBody } from './types'
import type {
  ReassignUploadResponse,
  UploadBatchResponse,
  UploadFileResult,
  UploadListResponse,
  UploadSummary,
} from './types'

async function readJson(response: Response): Promise<ApiErrorBody | null> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text) as ApiErrorBody
  } catch {
    return { detail: text }
  }
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function asSummary(value: unknown): UploadSummary | undefined {
  if (!value || typeof value !== 'object') return undefined
  const s = value as Record<string, unknown>
  const rows = asNumber(s.rows)
  const merchants = asNumber(s.merchants)
  const created = asNumber(s.created)
  const updated = asNumber(s.updated)
  const needs_review = asNumber(s.needs_review)
  const coverage_pct = asNumber(s.coverage_pct)
  if (
    rows === undefined ||
    merchants === undefined ||
    created === undefined ||
    updated === undefined ||
    needs_review === undefined ||
    coverage_pct === undefined
  ) {
    return undefined
  }
  return { rows, merchants, created, updated, needs_review, coverage_pct }
}

function parseFileResult(raw: Record<string, unknown>): UploadFileResult {
  const ok = Boolean(raw.ok)
  return {
    ok,
    filename: asString(raw.filename) ?? 'upload.csv',
    detail: asString(raw.detail),
    upload_id: asNumber(raw.upload_id),
    status: asString(raw.status),
    user_card_id: asNumber(raw.user_card_id),
    summary: asSummary(raw.summary),
    http_status: asNumber(raw.http_status),
    current_user_card_ids: Array.isArray(raw.current_user_card_ids)
      ? raw.current_user_card_ids.filter((n): n is number => typeof n === 'number')
      : undefined,
    requested_user_card_id: asNumber(raw.requested_user_card_id),
  }
}

/**
 * Backend single-file responses omit the batch wrapper and strip `ok`.
 * Multi-file returns {count, succeeded, failed, results} — including on HTTP 400
 * when every file failed. Normalize both into one shape for the UI.
 */
export function normalizeUploadResponse(
  body: ApiErrorBody | null,
  httpStatus: number,
  fallbackFilename: string,
): UploadBatchResponse {
  if (body && Array.isArray(body.results)) {
    const results = (body.results as unknown[]).map((item) =>
      parseFileResult(
        item && typeof item === 'object'
          ? (item as Record<string, unknown>)
          : {},
      ),
    )
    return {
      count: asNumber(body.count) ?? results.length,
      succeeded: asNumber(body.succeeded) ?? results.filter((r) => r.ok).length,
      failed: asNumber(body.failed) ?? results.filter((r) => !r.ok).length,
      results,
    }
  }

  // Single-file path (success or failure) — no results array.
  if (httpStatus >= 200 && httpStatus < 300 && body) {
    const result: UploadFileResult = {
      ok: true,
      filename: asString(body.filename) ?? fallbackFilename,
      upload_id: asNumber(body.upload_id),
      status: asString(body.status),
      user_card_id: asNumber(body.user_card_id),
      summary: asSummary(body.summary),
      http_status: httpStatus,
    }
    return { count: 1, succeeded: 1, failed: 0, results: [result] }
  }

  const detail =
    typeof body?.detail === 'string'
      ? body.detail
      : Array.isArray(body?.detail)
        ? body.detail.join(' ')
        : `Upload failed (${httpStatus})`

  // Top-level errors (missing card, no files) have detail but no per-file row.
  if (!body?.filename && httpStatus >= 400) {
    throw new ApiError(httpStatus, body, detail)
  }

  const result: UploadFileResult = {
    ok: false,
    filename: asString(body?.filename) ?? fallbackFilename,
    detail,
    upload_id: asNumber(body?.upload_id),
    http_status: httpStatus,
    current_user_card_ids: Array.isArray(body?.current_user_card_ids)
      ? body.current_user_card_ids.filter((n): n is number => typeof n === 'number')
      : undefined,
    requested_user_card_id: asNumber(body?.requested_user_card_id),
  }
  return { count: 1, succeeded: 0, failed: 1, results: [result] }
}

/** POST /api/upload/ — repeated `file` parts + user_card_id. */
export async function uploadStatements(
  userCardId: number,
  files: File[],
): Promise<UploadBatchResponse> {
  if (files.length === 0) {
    throw new ApiError(400, { detail: 'No file provided under the \'file\' (or \'files\') field.' })
  }

  const formData = new FormData()
  formData.append('user_card_id', String(userCardId))
  for (const file of files) {
    formData.append('file', file)
  }

  const response = await apiFormData('/api/upload/', formData)
  const body = await readJson(response)
  return normalizeUploadResponse(
    body,
    response.status,
    files[0]?.name ?? 'upload.csv',
  )
}

export function fetchUploads(): Promise<UploadListResponse> {
  return apiClient<UploadListResponse>('/api/uploads/')
}

export function reassignUpload(
  uploadId: number,
  userCardId: number,
): Promise<ReassignUploadResponse> {
  return apiClient<ReassignUploadResponse>(`/api/uploads/${uploadId}/reassign/`, {
    method: 'POST',
    body: { user_card_id: userCardId },
  })
}

export function deleteUpload(uploadId: number): Promise<void> {
  return apiClient<void>(`/api/uploads/${uploadId}/`, { method: 'DELETE' })
}
