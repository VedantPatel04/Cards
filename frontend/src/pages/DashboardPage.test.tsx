import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchSpendSummary } from '../api/summary'
import type { SpendSummaryResponse } from '../api/types'
import { DashboardPage } from '../pages/DashboardPage'

vi.mock('../api/summary', () => ({
  fetchSpendSummary: vi.fn(),
}))

const mockFetchSpendSummary = vi.mocked(fetchSpendSummary)

function emptySummary(
  overrides: Partial<SpendSummaryResponse> = {},
): SpendSummaryResponse {
  return {
    period: {
      earliest: null,
      latest: null,
      days_span: 0,
      months_covered: 0,
      months_breakdown: [],
    },
    by_category: {
      dining: '0.00',
      entertainment: '0.00',
      gas: '0.00',
      groceries: '0.00',
      other: '0.00',
      shopping: '0.00',
      travel: '0.00',
    },
    annualized: {
      dining: '0.00',
      entertainment: '0.00',
      gas: '0.00',
      groceries: '0.00',
      other: '0.00',
      shopping: '0.00',
      travel: '0.00',
    },
    total_spend: '0.00',
    transaction_count: 0,
    unresolved_count: 0,
    unresolved_amount: '0.00',
    categorized_pct: '100.0',
    ...overrides,
  }
}

function renderDashboard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DashboardPage', () => {
  beforeEach(() => {
    mockFetchSpendSummary.mockReset()
  })

  it('shows empty-state guidance when there are no transactions', async () => {
    mockFetchSpendSummary.mockResolvedValue(emptySummary())
    renderDashboard()

    expect(await screen.findByText(/No transactions yet/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Wallet/i })).toHaveAttribute(
      'href',
      '/wallet',
    )
    expect(screen.getByRole('link', { name: /Upload/i })).toHaveAttribute(
      'href',
      '/upload',
    )
  })

  it('renders plan metrics from the summary payload without recomputing money', async () => {
    mockFetchSpendSummary.mockResolvedValue(
      emptySummary({
        period: {
          earliest: '2026-01-01',
          latest: '2026-01-31',
          days_span: 31,
          months_covered: 1,
          months_breakdown: [{ month: '2026-01', transaction_count: 6 }],
        },
        by_category: {
          dining: '270.00',
          entertainment: '0.00',
          gas: '0.00',
          groceries: '0.00',
          other: '0.00',
          shopping: '50.00',
          travel: '0.00',
        },
        total_spend: '320.00',
        transaction_count: 6,
        unresolved_count: 1,
        unresolved_amount: '75.00',
        categorized_pct: '83.3',
      }),
    )

    renderDashboard()

    expect(await screen.findByText('$320.00')).toBeInTheDocument()
    expect(screen.getByText('83.3%')).toBeInTheDocument()
    expect(
      screen.getByText('Statement months covered').closest('div'),
    ).toHaveTextContent('1')
    expect(screen.getByText('$75.00')).toBeInTheDocument()
    expect(screen.getByText('$270.00')).toBeInTheDocument()
    expect(screen.getByText('$50.00')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /Review merchants/i }),
    ).toHaveAttribute('href', '/review')
  })
})
