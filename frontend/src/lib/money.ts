import type { MoneyString } from '../api/types'

const usd = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

/**
 * Display helper ... pass through the backend string — do not compute money in the UI. Returns the raw string if parsing fails */
export function formatMoney(value: MoneyString | null | undefined): string {
  if (value == null || value === '') return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return value
  return usd.format(n)
}
