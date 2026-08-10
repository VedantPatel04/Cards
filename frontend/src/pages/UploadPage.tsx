import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '../api/errors'
import { queryKeys, statementDependentKeys } from '../api/queryKeys'
import type { UploadFileResult, UploadListItem, WalletCard } from '../api/types'
import {
  deleteUpload,
  fetchUploads,
  reassignUpload,
  uploadStatements,
} from '../api/uploads'
import { fetchWallet } from '../api/wallet'

export function UploadPage() {
  const queryClient = useQueryClient()

  const walletQuery = useQuery({
    queryKey: queryKeys.wallet,
    queryFn: fetchWallet,
  })

  const uploadsQuery = useQuery({
    queryKey: queryKeys.uploads,
    queryFn: fetchUploads,
  })

  const walletCards = walletQuery.data?.cards ?? []

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [userCardId, setUserCardId] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [fileInputKey, setFileInputKey] = useState(0)
  const [batchResults, setBatchResults] = useState<UploadFileResult[] | null>(
    null,
  )
  const [formError, setFormError] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<UploadListItem | null>(
    null,
  )
  const [reassignFor, setReassignFor] = useState<UploadListItem | null>(null)
  const [reassignCardId, setReassignCardId] = useState('')

  async function invalidateStatementData() {
    await Promise.all(
      statementDependentKeys.map((key) =>
        queryClient.invalidateQueries({ queryKey: key }),
      ),
    )
  }

  const uploadMutation = useMutation({
    mutationFn: ({
      cardId,
      selected,
    }: {
      cardId: number
      selected: File[]
    }) => uploadStatements(cardId, selected),
    onSuccess: async (batch) => {
      setBatchResults(batch.results)
      await invalidateStatementData()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteUpload,
    onSuccess: async () => {
      setPendingDelete(null)
      await invalidateStatementData()
    },
  })

  const reassignMutation = useMutation({
    mutationFn: ({
      uploadId,
      cardId,
    }: {
      uploadId: number
      cardId: number
    }) => reassignUpload(uploadId, cardId),
    onSuccess: async () => {
      setReassignFor(null)
      setReassignCardId('')
      await invalidateStatementData()
    },
  })

  const otherCardsForReassign = useMemo(() => {
    const cards = walletQuery.data?.cards ?? []
    if (!reassignFor) return cards
    return cards.filter((c) => c.id !== reassignFor.user_card_id)
  }, [reassignFor, walletQuery.data?.cards])

  async function onUpload(event: FormEvent) {
    event.preventDefault()
    setFormError(null)
    setBatchResults(null)

    const cardId = Number(userCardId)
    if (!Number.isInteger(cardId) || cardId <= 0) {
      setFormError('Select a wallet card.')
      return
    }
    if (files.length === 0) {
      setFormError('Choose at least one CSV file.')
      return
    }

    try {
      await uploadMutation.mutateAsync({ cardId, selected: files })
      setFiles([])
      setFileInputKey((k) => k + 1)
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Upload failed.')
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return
    try {
      await deleteMutation.mutateAsync(pendingDelete.upload_id)
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : 'Could not delete upload.',
      )
      setPendingDelete(null)
    }
  }

  async function onReassign(event: FormEvent) {
    event.preventDefault()
    if (!reassignFor) return
    setFormError(null)
    const cardId = Number(reassignCardId)
    if (!Number.isInteger(cardId) || cardId <= 0) {
      setFormError('Select a wallet card to reassign to.')
      return
    }
    try {
      await reassignMutation.mutateAsync({
        uploadId: reassignFor.upload_id,
        cardId,
      })
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : 'Could not reassign upload.',
      )
    }
  }

  const loading = walletQuery.isLoading || uploadsQuery.isLoading
  const loadError =
    (walletQuery.error instanceof ApiError && walletQuery.error.message) ||
    (uploadsQuery.error instanceof ApiError && uploadsQuery.error.message) ||
    (walletQuery.error || uploadsQuery.error
      ? 'Failed to load upload data.'
      : null)

  // Explain why submit is disabled once the user has started the form
  // (avoids a permanent red error on first paint).
  const uploadBlockReason = uploadMutation.isPending
    ? null
    : files.length > 0 && !userCardId
      ? 'Select a wallet card.'
      : userCardId && files.length === 0
        ? 'Choose at least one CSV file.'
        : null

  return (
    <section className="flex flex-col gap-10">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Upload</h1>
        <p className="mt-2 max-w-prose text-[var(--color-muted)]">
          Attach Chase CSVs to one wallet card. You can select multiple files
          and upload them in one request. Per-file results appear below.
        </p>
      </header>

      {loading ? (
        <p className="text-[var(--color-muted)]">Loading…</p>
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

      {walletCards.length === 0 && !walletQuery.isLoading ? (
        <p className="text-[var(--color-muted)]">
          Add a card in{' '}
          <Link to="/wallet" className="underline">
            Wallet
          </Link>{' '}
          before uploading statements.
        </p>
      ) : (
        <form onSubmit={onUpload} className="flex max-w-lg flex-col gap-4">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium">Wallet card</span>
            <select
              value={userCardId}
              onChange={(e) => setUserCardId(e.target.value)}
              className="rounded border border-[var(--color-line)] bg-white px-3 py-2"
              required
            >
              <option value="">Select a card…</option>
              {walletCards.map((card) => (
                <WalletOption key={card.id} card={card} />
              ))}
            </select>
          </label>

          <div className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium" id="csv-files-heading">
              CSV files
            </span>
            {/*
              Must NOT live inside a <label>. A label that contains (or is
              htmlFor-linked to) a file input makes the entire label hit-target
              open the picker — including surrounding text and empty space.
              Only the Choose files button may call input.click().
            */}
            <input
              key={fileInputKey}
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              multiple
              className="sr-only"
              tabIndex={-1}
              aria-labelledby="csv-files-heading"
              onChange={(e) =>
                setFiles(e.target.files ? Array.from(e.target.files) : [])
              }
            />
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="rounded border border-[var(--color-line)] bg-white px-4 py-2 hover:border-[var(--color-ink)]"
              >
                Choose files
              </button>
              <span className="text-[var(--color-muted)]">
                {files.length === 0
                  ? 'No files selected'
                  : `${files.length} file${files.length === 1 ? '' : 's'} selected`}
              </span>
            </div>
            {files.length > 0 ? (
              <ul className="mt-1 list-inside list-disc text-[var(--color-muted)]">
                {files.map((file) => (
                  <li key={`${file.name}-${file.size}-${file.lastModified}`}>
                    {file.name}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          <div className="flex flex-col gap-1.5">
            <button
              type="submit"
              disabled={
                uploadMutation.isPending || !userCardId || files.length === 0
              }
              className="w-fit rounded bg-[var(--color-ink)] px-4 py-2 text-sm text-white disabled:opacity-60"
            >
              {uploadMutation.isPending
                ? 'Uploading…'
                : 'Upload selected files'}
            </button>
            {uploadBlockReason ? (
              <p className="text-sm text-[var(--color-danger)]" role="alert">
                {uploadBlockReason}
              </p>
            ) : null}
          </div>
        </form>
      )}

      {batchResults ? (
        <div>
          <h2 className="text-lg font-semibold">Last upload results</h2>
          <ul className="mt-3 flex flex-col gap-2">
            {batchResults.map((result, index) => (
              <li
                key={`${result.filename}-${index}`}
                className="border-b border-[var(--color-line)] pb-2 text-sm"
              >
                <p className="font-medium">
                  {result.filename}{' '}
                  <span
                    className={
                      result.ok
                        ? 'text-green-800'
                        : 'text-[var(--color-danger)]'
                    }
                  >
                    {result.ok ? 'succeeded' : 'failed'}
                  </span>
                </p>
                {result.ok && result.summary ? (
                  <p className="text-[var(--color-muted)]">
                    {result.summary.rows} rows · {result.summary.created} created
                    · {result.summary.updated} updated ·{' '}
                    {result.summary.needs_review} need review · coverage{' '}
                    {result.summary.coverage_pct}%
                  </p>
                ) : null}
                {!result.ok && result.detail ? (
                  <p className="text-[var(--color-danger)]">{result.detail}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <h2 className="text-lg font-semibold">Past uploads</h2>
        {(uploadsQuery.data?.uploads.length ?? 0) === 0 && !uploadsQuery.isLoading ? (
          <p className="mt-3 text-[var(--color-muted)]">No statements imported yet.</p>
        ) : (
          <ul className="mt-4 flex flex-col gap-4">
            {(uploadsQuery.data?.uploads ?? []).map((upload) => (
              <li
                key={upload.upload_id}
                className="flex flex-col gap-2 border-b border-[var(--color-line)] pb-4 sm:flex-row sm:items-start sm:justify-between"
              >
                <div>
                  <p className="font-medium">{upload.filename}</p>
                  <p className="text-sm text-[var(--color-muted)]">
                    {upload.card_name ?? 'Unknown card'}
                    {upload.issuer ? ` · ${upload.issuer}` : ''} ·{' '}
                    {upload.transaction_count} transactions · {upload.status}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setFormError(null)
                      setReassignFor(upload)
                      setReassignCardId('')
                    }}
                    className="rounded border border-[var(--color-line)] px-3 py-1.5 text-sm"
                  >
                    Reassign
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setFormError(null)
                      setPendingDelete(upload)
                    }}
                    className="rounded border border-[var(--color-line)] px-3 py-1.5 text-sm hover:border-[var(--color-danger)] hover:text-[var(--color-danger)]"
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {pendingDelete ? (
        <ConfirmDialog
          title={`Delete ${pendingDelete.filename}?`}
          body="This permanently deletes the statement import and its transactions."
          confirmLabel={deleteMutation.isPending ? 'Deleting…' : 'Delete upload'}
          busy={deleteMutation.isPending}
          danger
          onCancel={() => setPendingDelete(null)}
          onConfirm={confirmDelete}
        />
      ) : null}

      {reassignFor ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="reassign-title"
        >
          <form
            onSubmit={onReassign}
            className="w-full max-w-md rounded bg-[var(--color-paper)] p-5 shadow-lg"
          >
            <h2 id="reassign-title" className="text-lg font-semibold">
              Reassign {reassignFor.filename}
            </h2>
            <p className="mt-2 text-sm text-[var(--color-muted)]">
              Moves every transaction on this import to another wallet card.
              Use this when the statement was attached to the wrong card (do not
              re-upload the same file).
            </p>
            {otherCardsForReassign.length === 0 ? (
              <p className="mt-3 text-sm text-[var(--color-muted)]">
                Add another card in Wallet before reassigning.
              </p>
            ) : (
              <label className="mt-4 flex flex-col gap-1.5 text-sm">
                <span className="font-medium">New wallet card</span>
                <select
                  value={reassignCardId}
                  onChange={(e) => setReassignCardId(e.target.value)}
                  className="rounded border border-[var(--color-line)] bg-white px-3 py-2"
                  required
                >
                  <option value="">Select a card…</option>
                  {otherCardsForReassign.map((card) => (
                    <WalletOption key={card.id} card={card} />
                  ))}
                </select>
              </label>
            )}
            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setReassignFor(null)}
                disabled={reassignMutation.isPending}
                className="rounded border border-[var(--color-line)] px-3 py-1.5 text-sm"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={
                  reassignMutation.isPending ||
                  otherCardsForReassign.length === 0 ||
                  !reassignCardId
                }
                className="rounded bg-[var(--color-ink)] px-3 py-1.5 text-sm text-white disabled:opacity-60"
              >
                {reassignMutation.isPending ? 'Saving…' : 'Reassign'}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </section>
  )
}

function WalletOption({ card }: { card: WalletCard }) {
  return (
    <option value={card.id}>
      {card.issuer} — {card.card_name}
    </option>
  )
}

function ConfirmDialog({
  title,
  body,
  confirmLabel,
  busy,
  danger,
  onCancel,
  onConfirm,
}: {
  title: string
  body: string
  confirmLabel: string
  busy: boolean
  danger?: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded bg-[var(--color-paper)] p-5 shadow-lg">
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="mt-2 text-sm text-[var(--color-muted)]">{body}</p>
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
            className={
              danger
                ? 'rounded bg-[var(--color-danger)] px-3 py-1.5 text-sm text-white disabled:opacity-60'
                : 'rounded bg-[var(--color-ink)] px-3 py-1.5 text-sm text-white disabled:opacity-60'
            }
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
