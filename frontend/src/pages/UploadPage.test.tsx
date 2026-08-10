import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
      screen.queryByRole('button', { name: /^Upload$/i }),
    ).not.toBeInTheDocument()
  })

  it('shows why upload is blocked when files are selected without a card', async () => {
    const user = userEvent.setup()
    mockFetchWallet.mockResolvedValue({
      count: 1,
      cards: [
        {
          id: 7,
          card_product_id: 1,
          card_name: 'Sapphire',
          issuer: 'Chase',
          network: 'Visa',
          is_catalog: true,
          is_active: true,
        },
      ],
    })
    renderUploadPage()

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Upload selected files/i }),
      ).toBeDisabled()
    })

    const file = new File(['date,amount\n'], 'CHASE_APRIL.csv', {
      type: 'text/csv',
    })
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement
    await user.upload(input, file)

    expect(
      await screen.findByText('Select a wallet card.'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Upload selected files/i }),
    ).toBeDisabled()
  })
})
