/** Shapes returned by the Django/DRF backend. Keep monetary values as strings elsewhere. */

export type User = {
  id: number
  username: string
  email: string
}

export type TokenPair = {
  access: string
  refresh: string
}

export type AccessTokenResponse = {
  access: string
}

export type RegisterRequest = {
  username: string
  email: string
  password: string
  password2: string
}

export type LoginRequest = {
  username: string
  password: string
}

export type ApiErrorBody = {
  detail?: string | string[]
  [field: string]: unknown
}
