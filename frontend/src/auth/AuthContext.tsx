import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import * as authApi from '../api/auth'
import { onAuthFailure } from '../api/client'
import { ApiError } from '../api/errors'
import type { LoginRequest, RegisterRequest } from '../api/types'
import {
  AuthContext,
  type AuthStatus,
} from './authContextBase'
import {
  clearTokens,
  hasSession,
  setTokens,
} from './tokenStorage'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(() =>
    hasSession() ? 'loading' : 'anonymous',
  )

  const logout = useCallback(() => {
    clearTokens()
    setStatus('anonymous')
  }, [])

  useEffect(() => {
    return onAuthFailure(() => setStatus('anonymous'))
  }, [])

  useEffect(() => {
    if (!hasSession()) {
      setStatus('anonymous')
      return
    }

    let cancelled = false

    ;(async () => {
      try {
        await authApi.pingAuth()
        if (!cancelled) setStatus('authenticated')
      } catch (err) {
        if (cancelled) return
        // Refresh-or-clear already ran inside apiClient for 401s.
        if (err instanceof ApiError && err.status === 401) {
          setStatus('anonymous')
          return
        }

        if (hasSession()) setStatus('authenticated')
        else setStatus('anonymous')
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (payload: LoginRequest) => {
    const tokens = await authApi.login(payload)
    setTokens(tokens.access, tokens.refresh)
    setStatus('authenticated')
  }, [])

  const register = useCallback(
    async (payload: RegisterRequest) => {
      await authApi.register(payload)
      await login({ username: payload.username, password: payload.password })
    },
    [login],
  )

  const value = useMemo(
    () => ({ status, login, register, logout }),
    [status, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
