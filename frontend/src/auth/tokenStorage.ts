const ACCESS_KEY = 'cards.access'
const REFRESH_KEY = 'cards.refresh'

export function getAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_KEY)
}

export function setTokens(access: string, refresh: string): void {
  sessionStorage.setItem(ACCESS_KEY, access)
  sessionStorage.setItem(REFRESH_KEY, refresh)
}

export function setAccessToken(access: string): void {
  sessionStorage.setItem(ACCESS_KEY, access)
}

export function clearTokens(): void {
  sessionStorage.removeItem(ACCESS_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
}

export function hasSession(): boolean {
  return Boolean(getRefreshToken())
}
