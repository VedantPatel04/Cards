import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchTransactions } from '../api/transactions'
import type { TransactionsResponse } from '../api/types'
import { TransactionsPage } from '../pages/TransactionsPage'

vi.mock('../api/transactions', () => ({
  fetchTransactions: vi.fn(),
}))

const mockFetchTransactions = vi.mocked(fetchTransactions)

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TransactionsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('TransactionsPage', () => {
  beforeEach(() => {
    mockFetchTransactions.mockReset()
  })

  it('shows empty guidance when there are no transactions', async () => {
    mockFetchTransactions.mockResolvedValue({
      count: 0,
      truncated: false,
      transactions: [],
    })

    renderPage()

    expect(await screen.findByText(/No transactions yet/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Upload/i })).toHaveAttribute(
      'href',
      '/upload',
    )
  })

  it('renders a basic table from the API payload', async () => {
    const payload: TransactionsResponse = {
      count: 1,
      truncated: false,
      transactions: [
        {
          id: 101,
          upload_id: 7,
          filename: 'stmt.csv',
          user_card_id: 3,
          card_name: 'Freedom Unlimited',
          issuer: 'Chase',
          transaction_date: '2026-07-16',
          amount: '35.34',
          description: 'WAL-MART #2297',
          normalized_description: 'Wal Mart',
          merchant_key: 'WAL MART',
          category: 'groceries',
          entry_type: 'spend',
          resolution_source: 'bank',
          confidence: 0.7,
        },
      ],
    }
    mockFetchTransactions.mockResolvedValue(payload)

    renderPage()

    expect(await screen.findByText('WAL-MART #2297')).toBeInTheDocument()
    expect(screen.getByText('2026-07-16')).toBeInTheDocument()
    expect(screen.getByText('Freedom Unlimited')).toBeInTheDocument()
    expect(screen.getByText('groceries')).toBeInTheDocument()
    expect(screen.getByText('spend')).toBeInTheDocument()
    expect(screen.getByText('$35.34')).toBeInTheDocument()
  })

  it('labels blank categories as unresolved', async () => {
    mockFetchTransactions.mockResolvedValue({
      count: 1,
      truncated: false,
      transactions: [
        {
          id: 102,
          upload_id: 7,
          filename: 'stmt.csv',
          user_card_id: 3,
          card_name: 'Freedom Unlimited',
          issuer: 'Chase',
          transaction_date: '2026-07-15',
          amount: '10.00',
          description: 'MYSTERY',
          normalized_description: 'Mystery',
          merchant_key: 'MYSTERY',
          category: '',
          entry_type: 'spend',
          resolution_source: '',
          confidence: 0,
        },
      ],
    })

    renderPage()

    expect(await screen.findByText('unresolved')).toBeInTheDocument()
  })
})
