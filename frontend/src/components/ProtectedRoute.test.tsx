import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GuestRoute, ProtectedRoute } from '../components/ProtectedRoute'

const useAuthMock = vi.fn()

vi.mock('../auth/useAuth', () => ({
  useAuth: () => useAuthMock(),
}))

describe('ProtectedRoute', () => {
  beforeEach(() => {
    useAuthMock.mockReset()
  })

  it('redirects anonymous users to /login', () => {
    useAuthMock.mockReturnValue({ status: 'anonymous' })

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
    useAuthMock.mockReturnValue({ status: 'authenticated' })

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
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
  })

  it('shows a loading indicator while auth status is unknown', () => {
    useAuthMock.mockReturnValue({ status: 'loading' })

    render(
      <MemoryRouter initialEntries={['/wallet']}>
        <Routes>
          <Route element={<ProtectedRoute />}>
            <Route path="/wallet" element={<div>Wallet secret</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText(/Checking session/i)).toBeInTheDocument()
    expect(screen.queryByText('Wallet secret')).not.toBeInTheDocument()
  })
})

describe('GuestRoute', () => {
  beforeEach(() => {
    useAuthMock.mockReset()
  })

  it('renders the login page for anonymous users', () => {
    useAuthMock.mockReturnValue({ status: 'anonymous' })

    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route element={<GuestRoute />}>
            <Route path="/login" element={<div>Login page</div>} />
          </Route>
          <Route path="/dashboard" element={<div>Dashboard page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Login page')).toBeInTheDocument()
    expect(screen.queryByText('Dashboard page')).not.toBeInTheDocument()
  })

  it('redirects authenticated users away from /login to dashboard', () => {
    useAuthMock.mockReturnValue({ status: 'authenticated' })

    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route element={<GuestRoute />}>
            <Route path="/login" element={<div>Login page</div>} />
          </Route>
          <Route path="/dashboard" element={<div>Dashboard page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Dashboard page')).toBeInTheDocument()
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
  })

  it('redirects authenticated users away from / to dashboard', () => {
    useAuthMock.mockReturnValue({ status: 'authenticated' })

    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<GuestRoute />}>
            <Route path="/" element={<div>Welcome page</div>} />
          </Route>
          <Route path="/dashboard" element={<div>Dashboard page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Dashboard page')).toBeInTheDocument()
    expect(screen.queryByText('Welcome page')).not.toBeInTheDocument()
  })
})
