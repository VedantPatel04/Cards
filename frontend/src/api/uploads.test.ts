import { describe, expect, it } from 'vitest'

import { ApiError } from './errors'
import { normalizeUploadResponse } from './uploads'

describe('normalizeUploadResponse', () => {
  it('wraps a successful single-file body into a batch of one', () => {
    const batch = normalizeUploadResponse(
      {
        upload_id: 7,
        filename: 'stmt.csv',
        status: 'processed',
        user_card_id: 3,
        summary: {
          rows: 2,
          merchants: 2,
          created: 2,
          updated: 0,
          needs_review: 0,
          coverage_pct: 100,
        },
      },
      201,
      'stmt.csv',
    )

    expect(batch).toEqual({
      count: 1,
      succeeded: 1,
      failed: 0,
      results: [
        {
          ok: true,
          filename: 'stmt.csv',
          upload_id: 7,
          status: 'processed',
          user_card_id: 3,
          summary: {
            rows: 2,
            merchants: 2,
            created: 2,
            updated: 0,
            needs_review: 0,
            coverage_pct: 100,
          },
          http_status: 201,
        },
      ],
    })
  })

  it('keeps multi-file results when overall status is 400 (all failed)', () => {
    const batch = normalizeUploadResponse(
      {
        count: 2,
        succeeded: 0,
        failed: 2,
        results: [
          { ok: false, filename: 'a.csv', detail: 'bad', http_status: 400 },
          { ok: false, filename: 'b.csv', detail: 'also bad', http_status: 400 },
        ],
      },
      400,
      'a.csv',
    )

    expect(batch.count).toBe(2)
    expect(batch.succeeded).toBe(0)
    expect(batch.failed).toBe(2)
    expect(batch.results.map((r) => r.filename)).toEqual(['a.csv', 'b.csv'])
  })

  it('throws on top-level errors with no per-file filename', () => {
    expect(() =>
      normalizeUploadResponse(
        { detail: 'user_card_id is required.' },
        400,
        'stmt.csv',
      ),
    ).toThrow(ApiError)
  })
})
