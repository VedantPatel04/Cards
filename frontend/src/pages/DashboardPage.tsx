import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { ApiError } from '../api/errors'
import { queryKeys } from '../api/queryKeys'
import { fetchSpendSummary } from '../api/summary'
import { formatMoney } from '../lib/money'

export function DashboardPage() {
  const summaryQuery = useQuery({
    queryKey: queryKeys.summary,
    queryFn: fetchSpendSummary,
  })

  const loading = summaryQuery.isLoading
  const loadError =
    summaryQuery.error instanceof ApiError
      ? summaryQuery.error.message
      : summaryQuery.error
        ? 'Failed to load spend summary.'
        : null

  const summary = summaryQuery.data
  const categories = summary
    ? Object.entries(summary.by_category).sort(([a], [b]) => a.localeCompare(b))
    : []

  return (
    <section className="flex flex-col gap-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-2 max-w-prose text-[var(--color-muted)]">
          Spending summary from your uploaded statements 
        </p>
      </header>

      {loading ? (
        <p className="text-[var(--color-muted)]">Loading summary…</p>
      ) : null}
      {loadError ? (
        <p className="text-[var(--color-danger)]" role="alert">
          {loadError}
        </p>
      ) : null}

      {summary ? (
        <>
          {summary.transaction_count === 0 ? (
            <p className="text-[var(--color-muted)]">
              No transactions yet. Add a card in{' '}
              <Link to="/wallet" className="underline">
                Wallet
              </Link>
              , then import CSVs from{' '}
              <Link to="/upload" className="underline">
                Upload
              </Link>
              .
            </p>
          ) : null}

          <dl className="grid gap-4 sm:grid-cols-2">
            <Stat
              label="Total spend"
              value={formatMoney(summary.total_spend)}
            />
            <Stat
              label="Categorized"
              value={`${summary.categorized_pct}%`}
            />
            <Stat
              label="Months covered by statements"
              value={String(summary.period.months_covered)}
              hint="Sum of ~30-day statement cycles"
            />
            <Stat
              label="Unresolved amount"
              value={formatMoney(summary.unresolved_amount)}
              hint={
                summary.unresolved_count > 0
                  ? `${summary.unresolved_count} purchase/refund row${summary.unresolved_count === 1 ? '' : 's'} still need a category. See Review.`
                  : undefined
              }
            />
          </dl>

          {summary.unresolved_count > 0 ? (
            <p className="text-sm text-[var(--color-muted)]">
              <Link to="/review" className="underline">
                Review merchants
              </Link>{' '}
              to categorize unresolved spend.
            </p>
          ) : null}

          <div>
            <h2 className="text-lg font-semibold">Spending by category</h2>
            <ul className="mt-3 flex flex-col gap-2">
              {categories.map(([category, amount]) => (
                <li
                  key={category}
                  className="flex items-center justify-between border-b border-[var(--color-line)] py-2 text-sm"
                >
                  <span className="capitalize">{category}</span>
                  <span>{formatMoney(amount)}</span>
                </li>
              ))}
            </ul>
          </div>

          {summary.period.earliest && summary.period.latest ? (
            <p className="text-sm text-[var(--color-muted)]">
              {summary.period.earliest} TO {summary.period.latest}{' '}
              ({summary.period.days_span} calendar day
              {summary.period.days_span === 1 ? '' : 's'},{' '}
              {summary.transaction_count} transaction
              {summary.transaction_count === 1 ? '' : 's'}).
            </p>
          ) : null}
        </>
      ) : null}
    </section>
  )
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    <div className="border-b border-[var(--color-line)] pb-3">
      <dt className="text-sm text-[var(--color-muted)]">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tracking-tight">{value}</dd>
      {hint ? (
        <p className="mt-1 text-xs text-[var(--color-muted)]">{hint}</p>
      ) : null}
    </div>
  )
}
