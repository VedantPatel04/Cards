import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'

export function AppLayout() {
  const { logout } = useAuth()

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col px-4 py-6">
      <header className="mb-8 flex items-center justify-between border-b border-[var(--color-line)] pb-4">
        <NavLink to="/" className="text-xl font-semibold tracking-tight">
          Cards
        </NavLink>
        <nav className="flex items-center gap-4 text-sm">
          <NavLink
            to="/"
            className={({ isActive }) =>
              isActive ? 'font-medium' : 'text-[var(--color-muted)]'
            }
            end
          >
            Home
          </NavLink>
          <button
            type="button"
            onClick={logout}
            className="rounded border border-[var(--color-line)] px-3 py-1.5 hover:border-[var(--color-ink)]"
          >
            Log out
          </button>
        </nav>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  )
}
