import { useMutation, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { deleteAccount, fetchAccount } from '../api/auth'
import { ApiError } from '../api/errors'
import { queryKeys } from '../api/queryKeys'
import { useAuth } from '../auth/useAuth'

export function AccountSettingsPage() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  const accountQuery = useQuery({
    queryKey: queryKeys.account,
    queryFn: fetchAccount,
  })

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [showDelete, setShowDelete] = useState(false)

  const deleteMutation = useMutation({
    mutationFn: deleteAccount,
    onSuccess: () => {
      logout()
      navigate('/login', { replace: true })
    },
  })

  async function onDelete(event: FormEvent) {
    event.preventDefault()
    setFormError(null)
    if (confirm.trim() !== 'DELETE') {
      setFormError('Type DELETE exactly to confirm.')
      return
    }
    try {
      await deleteMutation.mutateAsync({ password, confirm: 'DELETE' })
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : 'Could not delete account.',
      )
    }
  }

  const account = accountQuery.data
  const loadError =
    accountQuery.error instanceof ApiError
      ? accountQuery.error.message
      : accountQuery.error
        ? 'Failed to load account.'
        : null

  return (
    <section className="flex flex-col gap-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Account settings</h1>
        <p className="mt-2 max-w-prose text-[var(--color-muted)]">
          Manage your profile and permanently delete your account.
        </p>
      </header>

      {accountQuery.isLoading ? (
        <p className="text-[var(--color-muted)]">Loading account…</p>
      ) : null}
      {loadError ? (
        <p className="text-[var(--color-danger)]" role="alert">
          {loadError}
        </p>
      ) : null}

      {account ? (
        <dl className="grid max-w-md gap-3 text-sm">
          <div>
            <dt className="text-[var(--color-muted)]">Username</dt>
            <dd className="mt-0.5 font-medium">{account.username}</dd>
          </div>
        </dl>
      ) : null}

      <div className="max-w-lg border-t border-[var(--color-line)] pt-6">
        <h2 className="text-lg font-semibold text-[var(--color-danger)]">
          Delete account
        </h2>
        <p className="mt-2 text-sm text-[var(--color-muted)]">
          This permanently removes your wallet, statement uploads, transactions,
          and merchant category labels. Catalog cards are shared and are not
          deleted. This cannot be undone.
        </p>

        {!showDelete ? (
          <button
            type="button"
            onClick={() => setShowDelete(true)}
            className="mt-4 rounded border border-[var(--color-danger)] px-3 py-1.5 text-sm text-[var(--color-danger)]"
          >
            Delete my account…
          </button>
        ) : (
          <form onSubmit={onDelete} className="mt-4 flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm">
              <span>Current password</span>
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="rounded border border-[var(--color-line)] bg-transparent px-3 py-2"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span>
                Type <span className="font-mono">DELETE</span> to confirm
              </span>
              <input
                type="text"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                className="rounded border border-[var(--color-line)] bg-transparent px-3 py-2 font-mono"
              />
            </label>
            {formError ? (
              <p className="text-sm text-[var(--color-danger)]" role="alert">
                {formError}
              </p>
            ) : null}
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => {
                  setShowDelete(false)
                  setFormError(null)
                  setPassword('')
                  setConfirm('')
                }}
                disabled={deleteMutation.isPending}
                className="rounded border border-[var(--color-line)] px-3 py-1.5 text-sm"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={deleteMutation.isPending}
                className="rounded bg-[var(--color-danger)] px-3 py-1.5 text-sm text-white disabled:opacity-60"
              >
                {deleteMutation.isPending ? 'Deleting…' : 'Permanently delete'}
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  )
}
