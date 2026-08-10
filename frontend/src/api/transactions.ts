import { apiClient } from './client'
import type { TransactionsResponse } from './types'

export function fetchTransactions(): Promise<TransactionsResponse> {
  return apiClient<TransactionsResponse>('/api/transactions/')
}
