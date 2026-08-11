import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  addCatalogCard,
  deleteWalletCard,
  fetchCatalog,
  fetchWallet,
} from '../api/wallet'
import { WalletPage } from '../pages/WalletPage'

vi.mock('../api/wallet', () => ({
  fetchCatalog: vi.fn(),
  fetchWallet: vi.fn(),
  addCatalogCard: vi.fn(),
  addCustomCard: vi.fn(),
  deleteWalletCard: vi.fn(),
}))

const mockFetchCatalog = vi.mocked(fetchCatalog)
const mockFetchWallet = vi.mocked(fetchWallet)
const mockAddCatalogCard = vi.mocked(addCatalogCard)
const mockDeleteWalletCard = vi.mocked(deleteWalletCard)

const FREEDOM_UNLIMITED = {
  id: 3,
  card_product_id: 12,
  card_name: 'Freedom Unlimited',
  issuer: 'Chase',
  network: 'Visa',
  is_catalog: true,
  is_active: true,
}

function renderWallet() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <WalletPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('WalletPage', () => {
  beforeEach(() => {
    mockFetchCatalog.mockReset()
    mockFetchWallet.mockReset()
    mockAddCatalogCard.mockReset()
    mockDeleteWalletCard.mockReset()
  })

  it('adds a catalog card to the wallet', async () => {
    const user = userEvent.setup()

    mockFetchCatalog.mockResolvedValue({
      count: 1,
      cards: [
        {
          id: 12,
          name: 'Freedom Unlimited',
          issuer: 'Chase',
          network: 'Visa',
          card_type: 'credit',
          annual_fee: '0.00',
          base_reward_rate: '1.50',
          signup_bonus: '200.00',
          signup_bonus_required_spending: '500.00',
        },
      ],
    })
    mockFetchWallet
      .mockResolvedValueOnce({ count: 0, cards: [] })
      .mockResolvedValue({ count: 1, cards: [FREEDOM_UNLIMITED] })
    mockAddCatalogCard.mockResolvedValue(FREEDOM_UNLIMITED)

    renderWallet()

    expect(await screen.findByText(/Wallet is empty/i)).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Catalog card'), '12')
    await user.click(screen.getByRole('button', { name: /Add catalog card/i }))

    await waitFor(() => {
      expect(mockAddCatalogCard).toHaveBeenCalledWith({ card_product_id: 12 })
    })
    expect(await screen.findByText('Freedom Unlimited')).toBeInTheDocument()
    expect(screen.queryByText(/Wallet is empty/i)).not.toBeInTheDocument()
  })

  it('opens a confirm dialog and removes the card on confirm', async () => {
    const user = userEvent.setup()

    mockFetchCatalog.mockResolvedValue({ count: 0, cards: [] })
    mockFetchWallet
      .mockResolvedValueOnce({ count: 1, cards: [FREEDOM_UNLIMITED] })
      .mockResolvedValue({ count: 0, cards: [] })
    mockDeleteWalletCard.mockResolvedValue(undefined)

    renderWallet()

    expect(await screen.findByText('Freedom Unlimited')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Remove$/i }))

    // Confirm dialog opens
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText(/Remove Freedom Unlimited\?/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Remove card/i }))

    await waitFor(() => {
      expect(mockDeleteWalletCard.mock.calls[0]?.[0]).toBe(3)
    })
    await waitFor(() => {
      expect(screen.queryByText('Freedom Unlimited')).not.toBeInTheDocument()
    })
  })
})
