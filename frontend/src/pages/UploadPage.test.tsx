import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { uploadStatements } from '../api/uploads'
import { fetchWallet } from '../api/wallet'
import { UploadPage } from '../pages/UploadPage'

vi.mock('../api/wallet', () => ({
  fetchWallet: vi.fn(),
}))

vi.mock('../api/uploads', async () => {
  const actual = await vi.importActual<typeof import('../api/uploads')>(
    '../api/uploads',
  )
  return {
    ...actual,
    fetchUploads: vi.fn(async () => ({ count: 0, uploads: [] })),
    uploadStatements: vi.fn(),
    reassignUpload: vi.fn(),
    deleteUpload: vi.fn(),
  }
})

const mockFetchWallet = vi.mocked(fetchWallet)
const mockUploadStatements = vi.mocked(uploadStatements)

const ONE_CARD = {
  count: 1,
  cards: [
    {
      id: 7,
      card_product_id: 1,
      card_name: 'Sapphire Preferred',
      issuer: 'Chase',
      network: 'Visa',
      is_catalog: true,
      is_active: true,
    },
  ],
}

function renderUploadPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <UploadPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('UploadPage', () => {
  beforeEach(() => {
    mockFetchWallet.mockReset()
    mockUploadStatements.mockReset()
  })

  it('prompts to add a wallet card when the wallet is empty', async () => {
    mockFetchWallet.mockResolvedValue({ count: 0, cards: [] })
    renderUploadPage()

    await waitFor(() => {
      expect(screen.getByText(/Add a card in/i)).toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: /Wallet/i })).toHaveAttribute(
      'href',
      '/wallet',
    )
    expect(
      screen.queryByRole('button', { name: /Upload selected files/i }),
    ).not.toBeInTheDocument()
  })

  it('shows why upload is blocked when files are selected without a card', async () => {
    const user = userEvent.setup()
    mockFetchWallet.mockResolvedValue(ONE_CARD)
    renderUploadPage()

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Upload selected files/i }),
      ).toBeDisabled()
    })

    const file = new File(['date,amount\n'], 'CHASE_APRIL.csv', {
      type: 'text/csv',
    })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, file)

    expect(await screen.findByText('Select a wallet card.')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Upload selected files/i }),
    ).toBeDisabled()
  })

  it('shows per-file results after a successful upload', async () => {
    const user = userEvent.setup()
    mockFetchWallet.mockResolvedValue(ONE_CARD)
    mockUploadStatements.mockResolvedValue({
      count: 1,
      succeeded: 1,
      failed: 0,
      results: [
        {
          ok: true,
          filename: 'CHASE_APRIL.csv',
          upload_id: 5,
          status: 'processed',
          user_card_id: 7,
          summary: {
            rows: 10,
            merchants: 4,
            created: 10,
            updated: 0,
            needs_review: 1,
            coverage_pct: 90,
          },
          http_status: 201,
        },
      ],
    })

    renderUploadPage()

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /Upload selected files/i }),
      ).toBeDisabled(),
    )

    // Wait for wallet query to resolve and populate the card dropdown
    await screen.findByRole('option', { name: /Chase.*Sapphire Preferred/i })

    await user.selectOptions(screen.getByLabelText(/Wallet card/i), '7')

    const file = new File(['date,amount\n'], 'CHASE_APRIL.csv', { type: 'text/csv' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, file)

    await user.click(screen.getByRole('button', { name: /Upload selected files/i }))

    expect(await screen.findByText('Last upload results')).toBeInTheDocument()
    expect(screen.getByText('CHASE_APRIL.csv')).toBeInTheDocument()
    expect(screen.getByText('succeeded')).toBeInTheDocument()
  })
})
