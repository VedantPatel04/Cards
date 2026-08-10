import { apiClient } from './client'
import type { RecommendationsResponse } from './types'

export function fetchRecommendations(): Promise<RecommendationsResponse> {
  return apiClient<RecommendationsResponse>('/api/recommendations/')
}
