import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { answerReview, fetchReviewQueue } from '../api/review'
import { ReviewPage } from '../pages/ReviewPage'

vi.mock('../api/review', () => ({
  fetchReviewQueue: vi.fn(),
  answerReview: vi.fn(),
}))

const mockFetchReviewQueue = vi.mocked(fetchReviewQueue)
const mockAnswerReview = vi.mocked(answerReview)

function renderReviewPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ReviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ReviewPage', () => {
  beforeEach(() => {
    mockFetchReviewQueue.mockReset()
    mockAnswerReview.mockReset()
  })

  it('shows empty guidance when the review queue has no merchants', async () => {
    mockFetchReviewQueue.mockResolvedValue({
      count: 0,
      truncated: false,
      categories: ['dining', 'groceries'],
      merchants: [],
    })

    renderReviewPage()

    expect(
      await screen.findByText(/Nothing to review/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Upload/i })).toHaveAttribute(
      'href',
      '/upload',
    )
  })

  it('posts the selected category and drops the merchant after success', async () => {
    const user = userEvent.setup()
    mockFetchReviewQueue
      .mockResolvedValueOnce({
        count: 1,
        truncated: false,
        categories: ['dining', 'shopping'],
        merchants: [
          {
            merchant_key: 'MYSTERY VENDOR',
            display_name: 'Mystery Vendor',
            sample_description: 'SQ *MYSTERY VENDOR',
            transaction_count: 2,
            total_amount: '25.00',
          },
        ],
      })
      .mockResolvedValueOnce({
        count: 0,
        truncated: false,
        categories: ['dining', 'shopping'],
        merchants: [],
      })

    mockAnswerReview.mockResolvedValue({
      merchant_key: 'MYSTERY VENDOR',
      category: 'shopping',
      transactions_updated: 2,
    })

    renderReviewPage()

    expect(await screen.findByText('Mystery Vendor')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Category'), 'shopping')
    await user.click(screen.getByRole('button', { name: /Assign category/i }))

    await waitFor(() => {
      expect(mockAnswerReview.mock.calls[0]?.[0]).toEqual({
        merchant_key: 'MYSTERY VENDOR',
        category: 'shopping',
      })
    })

    await waitFor(() => {
      expect(screen.queryByText('Mystery Vendor')).not.toBeInTheDocument()
    })
    expect(screen.getByText(/Nothing to review/i)).toBeInTheDocument()
  })
})
