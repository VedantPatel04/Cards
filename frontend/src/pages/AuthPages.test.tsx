import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/errors'
import { LoginPage } from '../pages/AuthPages'

const loginMock = vi.fn()

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({
    status: 'anonymous',
    login: loginMock,
    register: vi.fn(),
    logout: vi.fn(),
  }),
}))

function renderLogin(initialPath = '/login') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>Home page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    loginMock.mockReset()
  })

  it('navigates home after a successful login', async () => {
    const user = userEvent.setup()
    loginMock.mockResolvedValue(undefined)
    renderLogin()

    await user.type(screen.getByLabelText('Username'), 'alice')
    await user.type(screen.getByLabelText('Password'), 'secret')
    await user.click(screen.getByRole('button', { name: /Sign in/i }))

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith({
        username: 'alice',
        password: 'secret',
      })
    })
    expect(await screen.findByText('Home page')).toBeInTheDocument()
  })

  it('shows an error and stays on login when credentials fail', async () => {
    const user = userEvent.setup()
    loginMock.mockRejectedValue(
      new ApiError(401, { detail: 'No active account found with the given credentials' }),
    )
    renderLogin()

    await user.type(screen.getByLabelText('Username'), 'alice')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: /Sign in/i }))

    expect(
      await screen.findByRole('alert'),
    ).toHaveTextContent(/No active account found/i)
    expect(screen.getByRole('button', { name: /Sign in/i })).toBeInTheDocument()
    expect(screen.queryByText('Home page')).not.toBeInTheDocument()
  })
})
