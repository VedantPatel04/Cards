import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { ApiError } from '../api/errors'
import { queryKeys } from '../api/queryKeys'
import { fetchRecommendations } from '../api/recommendations'
import type { RecommendationCard } from '../api/types'
import { formatMoney } from '../lib/money'

export function RecommendationsPage() {
  const recommendationsQuery = useQuery({
    queryKey: queryKeys.recommendations,
    queryFn: fetchRecommendations,
  })

  const loading = recommendationsQuery.isLoading
  const loadError =
    recommendationsQuery.error instanceof ApiError
      ? recommendationsQuery.error.message
      : recommendationsQuery.error
        ? 'Failed to load recommendations.'
        : null

  const data = recommendationsQuery.data
  const cards = data?.recommendations ?? []

  return (
    <section className="flex flex-col gap-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">
          Recommendations
        </h1>
        <p className="mt-2 max-w-prose text-[var(--color-muted)]">
          The best cards for YOU - based on your spending.
        </p>
      </header>

      {loading ? (
        <p className="text-[var(--color-muted)]">Loading recommendations…</p>
      ) : null}
      {loadError ? (
        <p className="text-[var(--color-danger)]" role="alert">
          {loadError}
        </p>
      ) : null}

      {data ? (
        cards.length === 0 ? (
          <p className="text-[var(--color-muted)]">
            No recommendations yet. Upload transaction statements via{' '}
            <Link to="/upload" className="underline">
              Upload
            </Link>
            , then return here.
          </p>
        ) : (
          <ol className="flex flex-col gap-8">
            {cards.map((card) => (
              <RecommendationItem key={card.card_id} card={card} />
            ))}
          </ol>
        )
      ) : null}
    </section>
  )
}

function humanizeLabel(value: string) {
  return value.replaceAll('_', ' ')
}

function firstYearSavingsHint(card: RecommendationCard) {
  if (card.signup_bonus_status === 'no_bonus') {
    return 'No signup bonus'
  }
  return `Includes ${formatMoney(card.signup_bonus_score)} signup bonus`
}

function RecommendationItem({ card }: { card: RecommendationCard }) {
  return (
    <li className="border-b border-[var(--color-line)] pb-8">
      <div className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold tracking-tight">
          <span className="mr-2 text-sm font-medium text-[var(--color-muted)]">
            #{card.rank}
          </span>
          {card.card_name}
        </h2>
        <p className="text-sm text-[var(--color-muted)]">
          {card.issuer}
          {card.reward_currency
            ? ` · ${humanizeLabel(card.reward_currency)}`
            : ''}
        </p>
      </div>

      {card.rank_note ? (
        <p className="mt-1 text-sm text-[var(--color-muted)]">{card.rank_note}</p>
      ) : null}

      <p className="mt-3 max-w-prose">{card.headline}</p>

      <dl className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
        <Metric
          label="First-year savings"
          value={formatMoney(card.total_score)}
          hint={firstYearSavingsHint(card)}
        />
        <Metric
          label="Ongoing annual savings"
          value={formatMoney(card.ongoing_annual_value)}
          hint="Without signup bonus"
        />
        <Metric label="Annual fee" value={formatMoney(card.annual_fee)} />
        <Metric
          label="Signup bonus status"
          value={humanizeLabel(card.signup_bonus_status)}
          hint={card.signup_bonus_note || undefined}
        />
        {card.break_even_annual_spend ? (
          <Metric
            className="sm:col-span-2"
            label="Break-even annual spend"
            value={formatMoney(card.break_even_annual_spend)}
            hint="At your current category spending rates."
          />
        ) : null}
      </dl>

      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-medium">
          Categorical Spending
        </summary>
        <ul className="mt-3 flex flex-col gap-2 text-sm">
          {card.explanation.map((line) => (
            <li
              key={`${card.card_id}-${line.category}`}
              className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--color-line)] py-1"
            >
              <span className="capitalize">{line.category}</span>
              <span className="text-[var(--color-muted)]">
                {line.effective_rate}% on projected annual {formatMoney(line.annualized_spend)} →{' '}
                {formatMoney(line.value)} saved
              </span>
            </li>
          ))}
        </ul>
      </details>
    </li>
  )
}

function Metric({
  label,
  value,
  hint,
  className = '',
}: {
  label: string
  value: string
  hint?: string
  className?: string
}) {
  return (
    <div className={className}>
      <dt className="text-sm text-[var(--color-muted)]">{label}</dt>
      <dd className="mt-1 text-lg font-semibold capitalize tracking-tight">
        {value}
      </dd>
      {hint ? (
        <p className="mt-1 text-xs text-[var(--color-muted)]">{hint}</p>
      ) : null}
    </div>
  )
}
