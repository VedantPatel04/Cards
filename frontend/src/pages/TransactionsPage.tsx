import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { ApiError } from '../api/errors'
import { queryKeys } from '../api/queryKeys'
import { fetchTransactions } from '../api/transactions'
import type { TransactionRow } from '../api/types'
import { formatMoney } from '../lib/money'

export function TransactionsPage() {
  const transactionsQuery = useQuery({
    queryKey: queryKeys.transactions,
    queryFn: fetchTransactions,
  })

  const loading = transactionsQuery.isLoading
  const loadError =
    transactionsQuery.error instanceof ApiError
      ? transactionsQuery.error.message
      : transactionsQuery.error
        ? 'Failed to load transactions.'
        : null

  const data = transactionsQuery.data
  const rows = data?.transactions ?? []

  return (
    <section className="flex flex-col gap-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Transactions</h1>
        <p className="mt-2 max-w-prose text-[var(--color-muted)]">
          Your transaction history with the newest transactions listed first. Filtering and pagination are not in
          this module — the API returns at most 500 rows.
        </p>
      </header>

      {loading ? (
        <p className="text-[var(--color-muted)]">Loading transactions…</p>
      ) : null}
      {loadError ? (
        <p className="text-[var(--color-danger)]" role="alert">
          {loadError}
        </p>
      ) : null}

      {data?.truncated ? (
        <p className="text-sm text-[var(--color-muted)]">
          Showing {rows.length} of {data.count} transactions (API cap).
        </p>
      ) : null}

      {data && rows.length === 0 && !loading ? (
        <p className="text-[var(--color-muted)]">
          No transactions yet. Import statements from{' '}
          <Link to="/upload" className="underline">
            Upload
          </Link>
          .
        </p>
      ) : null}

      {rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--color-line)] text-[var(--color-muted)]">
                <th className="py-2 pr-3 font-medium">Date</th>
                <th className="py-2 pr-3 font-medium">Description</th>
                <th className="py-2 pr-3 font-medium">Card</th>
                <th className="py-2 pr-3 font-medium">Category</th>
                <th className="py-2 pr-3 font-medium">Type</th>
                <th className="py-2 text-right font-medium">Amount</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <TransactionTableRow key={row.id} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}

function TransactionTableRow({ row }: { row: TransactionRow }) {
  const categoryLabel = row.category.trim() === '' ? 'unresolved' : row.category

  return (
    <tr className="border-b border-[var(--color-line)] align-top">
      <td className="whitespace-nowrap py-2 pr-3">{row.transaction_date}</td>
      <td className="max-w-[16rem] py-2 pr-3">
        <span className="block truncate" title={row.description}>
          {row.description}
        </span>
        {row.filename ? (
          <span className="block truncate text-xs text-[var(--color-muted)]">
            {row.filename}
          </span>
        ) : null}
      </td>
      <td className="py-2 pr-3">
        <span className="block">{row.card_name}</span>
        <span className="block text-xs text-[var(--color-muted)]">
          {row.issuer}
        </span>
      </td>
      <td className="py-2 pr-3 capitalize">{categoryLabel}</td>
      <td className="py-2 pr-3 capitalize">{row.entry_type}</td>
      <td className="whitespace-nowrap py-2 text-right tabular-nums">
        {formatMoney(row.amount)}
      </td>
    </tr>
  )
}
