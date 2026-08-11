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
      : '/'

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
        <button
          type="submit"
          disabled={submitting}
          className="mt-2 rounded bg-[var(--color-ink)] px-4 py-2.5 text-white disabled:opacity-60"
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <p className="mt-6 text-sm text-[var(--color-muted)]">
        No account?{' '}
        <Link to="/register" className="underline">
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
  const [email, setEmail] = useState('')
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
      await register({ username, email, password, password2 })
      navigate('/', { replace: true })
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
      subtitle="Please fill out all details below to create an account"
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
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={setEmail}
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
        <button
          type="submit"
          disabled={submitting}
          className="mt-2 rounded bg-[var(--color-ink)] px-4 py-2.5 text-white disabled:opacity-60"
        >
          {submitting ? 'Creating…' : 'Create account'}
        </button>
      </form>
      <p className="mt-6 text-sm text-[var(--color-muted)]">
        Already registered?{' '}
        <Link to="/login" className="underline">
          Log in
        </Link>
      </p>
    </AuthShell>
  )
}

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
    <div className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-4 py-10">
      <p className="mb-2 text-sm font-medium tracking-wide text-[var(--color-accent)]">
        Cards
      </p>
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-[var(--color-muted)]">{subtitle}</p>
      <div className="mt-8">{children}</div>
    </div>
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
        className="rounded border border-[var(--color-line)] bg-white px-3 py-2 outline-none focus:border-[var(--color-ink)]"
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
