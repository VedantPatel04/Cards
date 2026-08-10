type PlaceholderPageProps = {
  title: string
  note: string
}

/** This is only a placeholder till I build the actual page */
export function PlaceholderPage({ title, note }: PlaceholderPageProps) {
  return (
    <section>
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-3 max-w-prose text-[var(--color-muted)]">{note}</p>
    </section>
  )
}
