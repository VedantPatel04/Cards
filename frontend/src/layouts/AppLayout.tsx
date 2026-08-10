import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? 'font-medium' : 'text-[var(--color-muted)] hover:text-[var(--color-ink)]'

export function AppLayout() {
  const { logout } = useAuth()

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-6">
      <header className="mb-8 flex flex-col gap-4 border-b border-[var(--color-line)] pb-4 sm:flex-row sm:items-center sm:justify-between">
        <NavLink to="/" className="text-xl font-semibold tracking-tight">
          Cards
        </NavLink>
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <NavLink to="/" className={navLinkClass} end>
            Dashboard
          </NavLink>
          <NavLink to="/wallet" className={navLinkClass}>
            Wallet
          </NavLink>
          <NavLink to="/upload" className={navLinkClass}>
            Upload
          </NavLink>
          <NavLink to="/review" className={navLinkClass}>
            Review
          </NavLink>
          <NavLink to="/recommendations" className={navLinkClass}>
            Recommendations
          </NavLink>
          <NavLink to="/transactions" className={navLinkClass}>
            Transactions
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
      <main className="flex-1 pb-10">
        <Outlet />
      </main>
    </div>
  )
}
