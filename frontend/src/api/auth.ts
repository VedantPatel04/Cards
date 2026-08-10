import { apiClient } from './client'
import type {
  LoginRequest,
  RegisterRequest,
  TokenPair,
  User,
} from './types'

export function register(payload: RegisterRequest): Promise<User> {
  return apiClient<User>('/api/register/', {
    method: 'POST',
    body: payload,
    skipAuth: true,
  })
}

export function login(payload: LoginRequest): Promise<TokenPair> {
  return apiClient<TokenPair>('/api/token/', {
    method: 'POST',
    body: payload,
    skipAuth: true,
  })
}

/** Cheap authenticated probe used after login / on app entry. */
export function pingAuth(): Promise<{ message: string }> {
  return apiClient<{ message: string }>('/api/isAuthenticated/')
}
