import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState, type FormEvent } from 'react'

import { ApiError } from '../api/errors'
import { queryKeys, statementDependentKeys } from '../api/queryKeys'
import type { CatalogCard, WalletCard } from '../api/types'
import {
  addCatalogCard,
  addCustomCard,
  deleteWalletCard,
  fetchCatalog,
  fetchWallet,
} from '../api/wallet'
import { formatMoney } from '../lib/money'

export function WalletPage() {
  const queryClient = useQueryClient()

  const catalogQuery = useQuery({
    queryKey: queryKeys.catalog,
    queryFn: fetchCatalog,
  })

  const walletQuery = useQuery({
    queryKey: queryKeys.wallet,
    queryFn: fetchWallet,
  })

  const ownedProductIds = useMemo(() => {
    const ids = new Set<number>()
    for (const card of walletQuery.data?.cards ?? []) {
      ids.add(card.card_product_id)
    }
    return ids
  }, [walletQuery.data])

  const availableCatalog = useMemo(
    () =>
      (catalogQuery.data?.cards ?? []).filter(
        (card) => !ownedProductIds.has(card.id),
      ),
    [catalogQuery.data, ownedProductIds],
  )

  async function invalidateWalletRelated() {
    await queryClient.invalidateQueries({ queryKey: queryKeys.wallet })
    await queryClient.invalidateQueries({ queryKey: queryKeys.catalog })
    await Promise.all(
      statementDependentKeys.map((key) =>
        queryClient.invalidateQueries({ queryKey: key }),
      ),
    )
  }

  const addCatalogMutation = useMutation({
    mutationFn: (cardProductId: number) =>
      addCatalogCard({ card_product_id: cardProductId }),
    onSuccess: invalidateWalletRelated,
  })

  const addCustomMutation = useMutation({
    mutationFn: addCustomCard,
    onSuccess: invalidateWalletRelated,
  })

  const deleteMutation = useMutation({
    mutationFn: deleteWalletCard,
    onSuccess: invalidateWalletRelated,
  })

  const [selectedCatalogId, setSelectedCatalogId] = useState('')
  const [customName, setCustomName] = useState('')
  const [customIssuer, setCustomIssuer] = useState('')
  const [customNetwork, setCustomNetwork] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<WalletCard | null>(null)

  async function onAddCatalog(event: FormEvent) {
    event.preventDefault()
    setFormError(null)
    const id = Number(selectedCatalogId)
    if (!Number.isInteger(id) || id <= 0) {
      setFormError('Choose a catalog card.')
      return
    }
    try {
      await addCatalogMutation.mutateAsync(id)
      setSelectedCatalogId('')
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Could not add card.')
    }
  }

  async function onAddCustom(event: FormEvent) {
    event.preventDefault()
    setFormError(null)
    try {
      await addCustomMutation.mutateAsync({
        name: customName.trim(),
        issuer: customIssuer.trim(),
        network: customNetwork.trim(),
      })
      setCustomName('')
      setCustomIssuer('')
      setCustomNetwork('')
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Could not add card.')
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return
    try {
      await deleteMutation.mutateAsync(pendingDelete.id)
      setPendingDelete(null)
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : 'Could not remove card.',
      )
      setPendingDelete(null)
    }
  }

  const loading = catalogQuery.isLoading || walletQuery.isLoading
  const loadError =
    catalogQuery.error instanceof ApiError
      ? catalogQuery.error.message
      : walletQuery.error instanceof ApiError
        ? walletQuery.error.message
        : catalogQuery.error || walletQuery.error
          ? 'Failed to load wallet data.'
          : null

  return (
    <section className="flex flex-col gap-10">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Wallet</h1>
        <p className="mt-2 max-w-prose text-[var(--color-muted)]">
          Cards you own. Catalog picks score rewards; custom cards track spend
          only (no reward rules).
        </p>
      </header>

      {loading ? (
        <p className="text-[var(--color-muted)]">Loading wallet…</p>
      ) : null}
      {loadError ? (
        <p className="text-[var(--color-danger)]" role="alert">
          {loadError}
        </p>
      ) : null}
      {formError ? (
        <p className="text-[var(--color-danger)]" role="alert">
          {formError}
        </p>
      ) : null}

      <div>
        <h2 className="text-lg font-semibold">Your cards</h2>
        {(walletQuery.data?.cards.length ?? 0) === 0 && !loading ? (
          <p className="mt-3 text-[var(--color-muted)]">
            Wallet is empty. Add a catalog or custom card below.
          </p>
        ) : (
          <ul className="mt-4 flex flex-col gap-3">
            {(walletQuery.data?.cards ?? []).map((card) => (
              <li
                key={card.id}
                className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-line)] pb-3"
              >
                <div>
                  <p className="font-medium">{card.card_name}</p>
                  <p className="text-sm text-[var(--color-muted)]">
                    {card.issuer} · {card.network}
                    {card.is_catalog ? '' : ' · custom'}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setFormError(null)
                    setPendingDelete(card)
                  }}
                  className="rounded border border-[var(--color-line)] px-3 py-1.5 text-sm hover:border-[var(--color-danger)] hover:text-[var(--color-danger)]"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <form onSubmit={onAddCatalog} className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Add from catalog</h2>
        {catalogQuery.data?.count === 0 ? (
          <p className="text-sm text-[var(--color-muted)]">
            Catalog is empty. Seed card products on the backend before adding
            from catalog.
          </p>
        ) : availableCatalog.length === 0 && !loading ? (
          <p className="text-sm text-[var(--color-muted)]">
            Every catalog card is already in your wallet.
          </p>
        ) : (
          <>
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="font-medium">Catalog card</span>
              <select
                value={selectedCatalogId}
                onChange={(e) => setSelectedCatalogId(e.target.value)}
                className="rounded border border-[var(--color-line)] bg-white px-3 py-2"
                required
              >
                <option value="">Select a card…</option>
                {availableCatalog.map((card) => (
                  <CatalogOption key={card.id} card={card} />
                ))}
              </select>
            </label>
            <button
              type="submit"
              disabled={addCatalogMutation.isPending || !selectedCatalogId}
              className="w-fit rounded bg-[var(--color-ink)] px-4 py-2 text-sm text-white disabled:opacity-60"
            >
              {addCatalogMutation.isPending ? 'Adding…' : 'Add catalog card'}
            </button>
          </>
        )}
      </form>

      <form onSubmit={onAddCustom} className="flex max-w-md flex-col gap-3">
        <h2 className="text-lg font-semibold">Add custom card</h2>
        <p className="text-sm text-[var(--color-muted)]">
          Requires name, issuer, and network. If name+issuer already exist in
          the catalog, that product is attached instead of creating a duplicate.
        </p>
        <Field
          label="Name"
          value={customName}
          onChange={setCustomName}
          required
        />
        <Field
          label="Issuer"
          value={customIssuer}
          onChange={setCustomIssuer}
          required
        />
        <Field
          label="Network"
          value={customNetwork}
          onChange={setCustomNetwork}
          required
          placeholder="e.g. Visa"
        />
        <button
          type="submit"
          disabled={addCustomMutation.isPending}
          className="w-fit rounded bg-[var(--color-ink)] px-4 py-2 text-sm text-white disabled:opacity-60"
        >
          {addCustomMutation.isPending ? 'Adding…' : 'Add custom card'}
        </button>
      </form>

      {pendingDelete ? (
        <DeleteConfirmDialog
          card={pendingDelete}
          busy={deleteMutation.isPending}
          onCancel={() => setPendingDelete(null)}
          onConfirm={confirmDelete}
        />
      ) : null}
    </section>
  )
}

function CatalogOption({ card }: { card: CatalogCard }) {
  return (
    <option value={card.id}>
      {card.issuer} — {card.name} (fee {formatMoney(card.annual_fee)})
    </option>
  )
}

function Field({
  label,
  value,
  onChange,
  required,
  placeholder,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  required?: boolean
  placeholder?: string
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="font-medium">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        placeholder={placeholder}
        className="rounded border border-[var(--color-line)] bg-white px-3 py-2 outline-none focus:border-[var(--color-ink)]"
      />
    </label>
  )
}

function DeleteConfirmDialog({
  card,
  busy,
  onCancel,
  onConfirm,
}: {
  card: WalletCard
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="wallet-delete-title"
    >
      <div className="w-full max-w-md rounded bg-[var(--color-paper)] p-5 shadow-lg">
        <h2 id="wallet-delete-title" className="text-lg font-semibold">
          Remove {card.card_name}?
        </h2>
        <p className="mt-2 text-sm text-[var(--color-muted)]">
          This permanently deletes the wallet entry and its transactions. Empty
          statement uploads for this account may be removed too. This cannot be
          undone.
        </p>
        <div className="mt-5 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded border border-[var(--color-line)] px-3 py-1.5 text-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded bg-[var(--color-danger)] px-3 py-1.5 text-sm text-white disabled:opacity-60"
          >
            {busy ? 'Removing…' : 'Remove card'}
          </button>
        </div>
      </div>
    </div>
  )
}
