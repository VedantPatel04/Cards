/** TanStack Query keys — invalidate after uploads, review answers, or wallet deletes */
export const queryKeys = {
  account: ['account'] as const,
  catalog: ['catalog'] as const,
  wallet: ['wallet'] as const,
  uploads: ['uploads'] as const,
  transactions: ['transactions'] as const,
  review: ['review'] as const,
  summary: ['summary'] as const,
  recommendations: ['recommendations'] as const,
}

/** Domains that change when statements or categories change. */
export const statementDependentKeys = [
  queryKeys.uploads,
  queryKeys.transactions,
  queryKeys.review,
  queryKeys.summary,
  queryKeys.recommendations,
] as const
