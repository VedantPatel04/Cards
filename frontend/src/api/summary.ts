import { apiClient } from './client'
import type { SpendSummaryResponse } from './types'

export function fetchSpendSummary(): Promise<SpendSummaryResponse> {
  return apiClient<SpendSummaryResponse>('/api/summary/')
}
