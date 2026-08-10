import { apiClient } from './client'
import type {
  ReviewAnswerRequest,
  ReviewAnswerResponse,
  ReviewQueueResponse,
} from './types'

export function fetchReviewQueue(): Promise<ReviewQueueResponse> {
  return apiClient<ReviewQueueResponse>('/api/review/')
}

/** POST /api/review/answer/ — not POST /api/review/ (view docstring is wrong) */
export function answerReview(
  payload: ReviewAnswerRequest,
): Promise<ReviewAnswerResponse> {
  return apiClient<ReviewAnswerResponse>('/api/review/answer/', {
    method: 'POST',
    body: payload,
  })
}
