import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ProtectedRoute } from '../components/ProtectedRoute'

const useAuthMock = vi.fn()

vi.mock('../auth/useAuth', () => ({
  useAuth: () => useAuthMock(),
}))

describe('ProtectedRoute', () => {
  beforeEach(() => {
    useAuthMock.mockReset()
  })

  it('redirects anonymous users to /login', () => {
    useAuthMock.mockReturnValue({
      status: 'anonymous',
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    })

    render(
      <MemoryRouter initialEntries={['/wallet']}>
        <Routes>
          <Route element={<ProtectedRoute />}>
            <Route path="/wallet" element={<div>Wallet secret</div>} />
          </Route>
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Login page')).toBeInTheDocument()
    expect(screen.queryByText('Wallet secret')).not.toBeInTheDocument()
  })

  it('renders child routes when authenticated', () => {
    useAuthMock.mockReturnValue({
      status: 'authenticated',
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    })

    render(
      <MemoryRouter initialEntries={['/wallet']}>
        <Routes>
          <Route element={<ProtectedRoute />}>
            <Route path="/wallet" element={<div>Wallet secret</div>} />
          </Route>
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Wallet secret')).toBeInTheDocument()
  })
})
