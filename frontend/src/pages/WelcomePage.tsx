import { Link } from 'react-router-dom'

/**
 * Public landing page
 * GuestRoute sends authenticated visitors to /dashboard
 */
export function WelcomePage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-cream px-6 py-16">
      <div className="w-fit max-w-full">
        <span className="animate-fade-in-up text-sm font-semibold tracking-wide text-amber">
          Cards
        </span>
        <h1 className="animate-fade-in-up mt-3 whitespace-nowrap text-4xl font-bold tracking-tight text-navy max-sm:whitespace-normal [animation-delay:80ms]">
          Find your next favorite credit card
        </h1>
        <div className="animate-fade-in-up mt-8 max-w-md [animation-delay:160ms]">
          <Link
            to="/register"
            className="inline-flex w-full items-center justify-center rounded-md bg-navy px-6 py-3 text-sm font-medium text-cream transition-colors hover:bg-navy/90 focus:outline-none focus:ring-2 focus:ring-amber focus:ring-offset-2 focus:ring-offset-cream"
          >
            Create an account
          </Link>
        </div>
        <p className="animate-fade-in-up mt-8 text-sm text-[var(--color-muted)] [animation-delay:240ms]">
          Already registered?{' '}
          <Link
            to="/login"
            className="font-medium text-navy underline underline-offset-4 transition-colors hover:text-amber"
          >
            Log in
          </Link>
        </p>
        <p className="animate-fade-in-up mt-12 text-sm text-[var(--color-muted)] [animation-delay:320ms]">
          Built with care by Vedant :)
        </p>
      </div>
    </main>
  )
}
