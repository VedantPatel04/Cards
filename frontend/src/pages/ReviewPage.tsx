import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '../api/errors'
import { queryKeys, statementDependentKeys } from '../api/queryKeys'
import { answerReview, fetchReviewQueue } from '../api/review'
import type { ReviewMerchant } from '../api/types'
import { formatMoney } from '../lib/money'

export function ReviewPage() {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  /** merchant_key currently submitting */
  const [submittingKey, setSubmittingKey] = useState<string | null>(null)
  /** selected category per merchant_key before save */
  const [draftCategory, setDraftCategory] = useState<Record<string, string>>({})

  const reviewQuery = useQuery({
    queryKey: queryKeys.review,
    queryFn: fetchReviewQueue,
  })

  const answerMutation = useMutation({
    mutationFn: answerReview,
    onSuccess: async (_data, variables) => {
      setDraftCategory((prev) => {
        const next = { ...prev }
        delete next[variables.merchant_key]
        return next
      })
      await Promise.all(
        statementDependentKeys.map((key) =>
          queryClient.invalidateQueries({ queryKey: key }),
        ),
      )
    },
  })

  async function onAssign(merchant: ReviewMerchant) {
    setError(null)
    const category = (draftCategory[merchant.merchant_key] || '').trim()
    if (!category) {
      setError(`Choose a category for ${merchant.display_name}.`)
      return
    }

    setSubmittingKey(merchant.merchant_key)
    try {
      await answerMutation.mutateAsync({
        merchant_key: merchant.merchant_key,
        category,
      })
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not save category.',
      )
    } finally {
      setSubmittingKey(null)
    }
  }

  const merchants = reviewQuery.data?.merchants ?? []
  const categories = reviewQuery.data?.categories ?? []
  const loading = reviewQuery.isLoading
  const loadError =
    reviewQuery.error instanceof ApiError
      ? reviewQuery.error.message
      : reviewQuery.error
        ? 'Failed to load review queue.'
        : null

  return (
    <section className="flex flex-col gap-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Review</h1>
      </header>

      {loading ? (
        <p className="text-[var(--color-muted)]">Loading review queue…</p>
      ) : null}
      {loadError ? (
        <p className="text-[var(--color-danger)]" role="alert">
          {loadError}
        </p>
      ) : null}
      {error ? (
        <p className="text-[var(--color-danger)]" role="alert">
          {error}
        </p>
      ) : null}

      {reviewQuery.data?.truncated ? (
        <p className="text-sm text-[var(--color-muted)]">
          Showing the top {merchants.length} of {reviewQuery.data.count}{' '}
          merchants by spend. Answer these first — they move the most dollars.
        </p>
      ) : null}

      {!loading && !loadError && merchants.length === 0 ? (
        <p className="text-[var(--color-muted)]">
          Nothing to review. Upload statements from{' '}
          <Link to="/upload" className="underline">
            Upload
          </Link>{' '}
          if you have not yet, or all merchants are already categorized.
        </p>
      ) : null}

      <ul className="flex flex-col gap-6">
        {merchants.map((merchant) => {
          const selected = draftCategory[merchant.merchant_key] ?? ''
          const busy = submittingKey === merchant.merchant_key
          const selectId = `category-${merchant.merchant_key}`

          return (
            <li
              key={merchant.merchant_key}
              className="border-b border-[var(--color-line)] pb-6"
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <p className="font-medium">{merchant.display_name}</p>
                  <p className="text-sm text-[var(--color-muted)]">
                    {merchant.sample_description}
                  </p>
                  <p className="mt-1 text-sm text-[var(--color-muted)]">
                    {merchant.transaction_count} transaction
                    {merchant.transaction_count === 1 ? '' : 's'} ·{' '}
                    {formatMoney(merchant.total_amount)}
                  </p>
                </div>

                <div className="flex flex-col gap-2 sm:min-w-[14rem]">
                  <label
                    htmlFor={selectId}
                    className="text-sm font-medium"
                  >
                    Category
                  </label>
                  <select
                    id={selectId}
                    value={selected}
                    disabled={busy || categories.length === 0}
                    onChange={(e) =>
                      setDraftCategory((prev) => ({
                        ...prev,
                        [merchant.merchant_key]: e.target.value,
                      }))
                    }
                    className="rounded border border-[var(--color-line)] bg-white px-3 py-2 text-sm"
                  >
                    <option value="">Select…</option>
                    {categories.map((category) => (
                      <option key={category} value={category}>
                        {category}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    disabled={busy || !selected}
                    onClick={() => onAssign(merchant)}
                    className="rounded bg-[var(--color-ink)] px-3 py-2 text-sm text-white disabled:opacity-60"
                  >
                    {busy ? 'Saving…' : 'Assign category'}
                  </button>
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
