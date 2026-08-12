import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/errors'
import { useAuth } from '../auth/useAuth'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from =
    typeof location.state === 'object' &&
    location.state !== null &&
    'from' in location.state &&
    typeof (location.state as { from: unknown }).from === 'string'
      ? (location.state as { from: string }).from
      : '/dashboard'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login({ username, password })
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : networkOrUnknown(err, 'Login failed.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell title="Log in" subtitle="Use your Cards username and password.">
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field
          label="Username"
          name="username"
          autoComplete="username"
          value={username}
          onChange={setUsername}
          required
        />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
          required
        />
        {error ? <ErrorText>{error}</ErrorText> : null}
        <button type="submit" disabled={submitting} className={authSubmitClass}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <p className="mt-6 text-sm text-[var(--color-muted)]">
        No account?{' '}
        <Link to="/register" className={authLinkClass}>
          Register
        </Link>
      </p>
    </AuthShell>
  )
}

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)

    if (password !== password2) {
      setError('Passwords do not match.')
      return
    }

    setSubmitting(true)
    try {
      await register({ username, password, password2 })
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : networkOrUnknown(err, 'Registration failed.'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      title="Create account"
      subtitle="Choose a username and password to get started."
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field
          label="Username"
          name="username"
          autoComplete="username"
          value={username}
          onChange={setUsername}
          required
        />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={setPassword}
          required
        />
        <Field
          label="Confirm password"
          name="password2"
          type="password"
          autoComplete="new-password"
          value={password2}
          onChange={setPassword2}
          required
        />
        {error ? <ErrorText>{error}</ErrorText> : null}
        <button type="submit" disabled={submitting} className={authSubmitClass}>
          {submitting ? 'Creating…' : 'Create account'}
        </button>
      </form>
      <p className="mt-6 text-sm text-[var(--color-muted)]">
        Already registered?{' '}
        <Link to="/login" className={authLinkClass}>
          Log in
        </Link>
      </p>
    </AuthShell>
  )
}

const authSubmitClass =
  'mt-2 inline-flex w-full items-center justify-center rounded-md bg-navy px-6 py-3 text-sm font-medium text-cream transition-colors hover:bg-navy/90 focus:outline-none focus:ring-2 focus:ring-amber focus:ring-offset-2 focus:ring-offset-cream disabled:opacity-60'

const authLinkClass =
  'font-medium text-navy underline underline-offset-4 transition-colors hover:text-amber'

function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: ReactNode
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-cream px-6 py-16">
      <div className="w-full max-w-md">
        <Link
          to="/"
          className="animate-fade-in-up text-sm font-semibold tracking-wide text-amber"
        >
          Cards
        </Link>
        <h1 className="animate-fade-in-up mt-3 text-3xl font-bold tracking-tight text-navy [animation-delay:80ms]">
          {title}
        </h1>
        <p className="animate-fade-in-up mt-2 text-[var(--color-muted)] [animation-delay:160ms]">
          {subtitle}
        </p>
        <div className="animate-fade-in-up mt-8 [animation-delay:240ms]">
          {children}
        </div>
      </div>
    </main>
  )
}

function Field({
  label,
  name,
  value,
  onChange,
  type = 'text',
  autoComplete,
  required,
}: {
  label: string
  name: string
  value: string
  onChange: (value: string) => void
  type?: string
  autoComplete?: string
  required?: boolean
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="font-medium">{label}</span>
      <input
        name={name}
        type={type}
        autoComplete={autoComplete}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-[var(--color-line)] bg-white px-3 py-2 outline-none transition-colors focus:border-navy focus:ring-2 focus:ring-amber focus:ring-offset-2 focus:ring-offset-cream"
      />
    </label>
  )
}

function ErrorText({ children }: { children: ReactNode }) {
  return (
    <p className="text-sm text-[var(--color-danger)]" role="alert">
      {children}
    </p>
  )
}

/** TypeError from fetch usually means CORS block or API unreachable. */
function networkOrUnknown(err: unknown, fallback: string): string {
  if (err instanceof TypeError) {
    return 'Cannot reach the API. Is the backend running, and is this UI origin in CORS_ALLOWED_ORIGINS?'
  }
  return fallback
}
