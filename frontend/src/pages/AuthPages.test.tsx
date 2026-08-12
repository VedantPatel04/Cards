import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/errors'
import { LoginPage, RegisterPage } from '../pages/AuthPages'

const loginMock = vi.fn()
const registerMock = vi.fn()

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({
    status: 'anonymous',
    login: loginMock,
    register: registerMock,
    logout: vi.fn(),
  }),
}))

function renderLogin(initialPath = '/login') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<div>Dashboard page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

function renderRegister() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/dashboard" element={<div>Dashboard page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    loginMock.mockReset()
  })

  it('navigates to dashboard after a successful login', async () => {
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
    expect(await screen.findByText('Dashboard page')).toBeInTheDocument()
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
    expect(screen.queryByText('Dashboard page')).not.toBeInTheDocument()
  })
})

describe('RegisterPage', () => {
  beforeEach(() => {
    registerMock.mockReset()
  })

  it('shows an error and stays on page when passwords do not match', async () => {
    const user = userEvent.setup()
    renderRegister()

    await user.type(screen.getByLabelText('Username'), 'alice')
    await user.type(screen.getByLabelText('Password'), 'Sup3rSecret!')
    await user.type(screen.getByLabelText('Confirm password'), 'different!')
    await user.click(screen.getByRole('button', { name: /Create account/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /Passwords do not match/i,
    )
    expect(registerMock).not.toHaveBeenCalled()
    expect(screen.queryByText('Dashboard page')).not.toBeInTheDocument()
  })

  it('shows an API error when the username is already taken', async () => {
    const user = userEvent.setup()
    registerMock.mockRejectedValue(
      new ApiError(400, { username: ['A user with that username already exists.'] }),
    )
    renderRegister()

    await user.type(screen.getByLabelText('Username'), 'alice')
    await user.type(screen.getByLabelText('Password'), 'Sup3rSecret!')
    await user.type(screen.getByLabelText('Confirm password'), 'Sup3rSecret!')
    await user.click(screen.getByRole('button', { name: /Create account/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /A user with that username already exists/i,
    )
    expect(screen.queryByText('Dashboard page')).not.toBeInTheDocument()
  })

  it('navigates to dashboard after successful registration', async () => {
    const user = userEvent.setup()
    registerMock.mockResolvedValue(undefined)
    renderRegister()

    await user.type(screen.getByLabelText('Username'), 'alice')
    await user.type(screen.getByLabelText('Password'), 'Sup3rSecret!')
    await user.type(screen.getByLabelText('Confirm password'), 'Sup3rSecret!')
    await user.click(screen.getByRole('button', { name: /Create account/i }))

    await waitFor(() => {
      expect(registerMock).toHaveBeenCalledWith({
        username: 'alice',
        password: 'Sup3rSecret!',
        password2: 'Sup3rSecret!',
      })
    })
    expect(await screen.findByText('Dashboard page')).toBeInTheDocument()
  })
})
