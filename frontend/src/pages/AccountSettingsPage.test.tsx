import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { deleteAccount, fetchAccount } from '../api/auth'
import { AccountSettingsPage } from '../pages/AccountSettingsPage'

vi.mock('../api/auth', async () => {
  const actual = await vi.importActual<typeof import('../api/auth')>('../api/auth')
  return {
    ...actual,
    fetchAccount: vi.fn(),
    deleteAccount: vi.fn(),
  }
})

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({
    status: 'authenticated',
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  }),
}))

const mockFetchAccount = vi.mocked(fetchAccount)
const mockDeleteAccount = vi.mocked(deleteAccount)

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AccountSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AccountSettingsPage', () => {
  beforeEach(() => {
    mockFetchAccount.mockReset()
    mockDeleteAccount.mockReset()
    mockFetchAccount.mockResolvedValue({
      id: 1,
      username: 'alice',
    })
  })

  it('shows profile and deletes after password + DELETE confirm', async () => {
    const user = userEvent.setup()
    mockDeleteAccount.mockResolvedValue(undefined)

    renderPage()

    expect(await screen.findByText('alice')).toBeInTheDocument()
    expect(screen.queryByText(/@/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Delete my account/i }))
    await user.type(screen.getByLabelText(/Current password/i), 'Sup3rSecret!pw')
    await user.type(screen.getByLabelText(/Type DELETE/i), 'DELETE')
    await user.click(screen.getByRole('button', { name: /Permanently delete/i }))

    await waitFor(() => {
      expect(mockDeleteAccount.mock.calls[0]?.[0]).toEqual({
        password: 'Sup3rSecret!pw',
        confirm: 'DELETE',
      })
    })
  })
})
