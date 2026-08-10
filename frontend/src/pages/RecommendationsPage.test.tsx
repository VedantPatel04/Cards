import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchRecommendations } from '../api/recommendations'
import type { RecommendationsResponse } from '../api/types'
import { RecommendationsPage } from '../pages/RecommendationsPage'

vi.mock('../api/recommendations', () => ({
  fetchRecommendations: vi.fn(),
}))

const mockFetchRecommendations = vi.mocked(fetchRecommendations)

function baseResponse(
  overrides: Partial<RecommendationsResponse> = {},
): RecommendationsResponse {
  return {
    confidence: 'low',
    confidence_note: 'Upload more statements for a stronger read.',
    value_basis: {
      currency: 'usd',
      period: 'per_year',
      months_of_data: 0,
      point_value_cents: '1.0',
      note: 'Money fields are estimated US dollars.',
    },
    recommendations: [],
    ...overrides,
  }
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RecommendationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RecommendationsPage', () => {
  beforeEach(() => {
    mockFetchRecommendations.mockReset()
  })

  it('shows confidence and empty guidance when there are no cards', async () => {
    mockFetchRecommendations.mockResolvedValue(baseResponse())
    renderPage()

    expect(await screen.findByText('low')).toBeInTheDocument()
    expect(
      screen.getByText(/No catalog recommendations yet/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Upload/i })).toHaveAttribute(
      'href',
      '/upload',
    )
  })

  it('renders plan fields from the API without inventing scores', async () => {
    mockFetchRecommendations.mockResolvedValue(
      baseResponse({
        confidence: 'medium',
        confidence_note: 'Decent coverage.',
        value_basis: {
          currency: 'usd',
          period: 'per_year',
          months_of_data: 2,
          point_value_cents: '1.0',
          note: 'total_score is first-year value.',
        },
        recommendations: [
          {
            rank: 1,
            card_id: 12,
            card_name: 'Freedom Unlimited',
            issuer: 'Chase',
            reward_currency: 'cash',
            headline: 'Earns about $15.00 a year on your spending, with no annual fee.',
            spending_score: '15.00',
            annual_fee: '0.00',
            signup_bonus_score: '0.00',
            signup_bonus_status: 'insufficient_data',
            signup_bonus_note: 'Upload 1 more month(s) of statements.',
            signup_bonus_detail: { status: 'insufficient_data' },
            total_score: '15.00',
            ongoing_annual_value: '15.00',
            break_even_annual_spend: null,
            explanation: [
              {
                category: 'dining',
                rate: '1.50',
                effective_rate: '1.50',
                annualized_spend: '0.00',
                value: '0.00',
              },
            ],
          },
        ],
      }),
    )

    renderPage()

    expect(await screen.findByText('Freedom Unlimited')).toBeInTheDocument()
    expect(screen.getByText('medium')).toBeInTheDocument()
    expect(screen.getByText(/#1/)).toBeInTheDocument()
    expect(
      screen.getByText(/Earns about \$15\.00 a year on your spending/i),
    ).toBeInTheDocument()
    expect(screen.getByText('First-year value').closest('div')).toHaveTextContent(
      '$15.00',
    )
    expect(
      screen.getByText('Ongoing annual value').closest('div'),
    ).toHaveTextContent('$15.00')
    expect(screen.getByText('Annual fee').closest('div')).toHaveTextContent(
      '$0.00',
    )
    expect(
      screen.getByText('Signup bonus status').closest('div'),
    ).toHaveTextContent(/insufficient data/i)
    expect(
      screen.getByText(/Upload 1 more month\(s\) of statements/i),
    ).toBeInTheDocument()
  })
})
