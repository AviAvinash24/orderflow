import { createContext, useContext, useMemo, useState } from 'react'
import { api } from './api'

const STORAGE_KEY = 'orderflow.auth'

function loadStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [session, setSession] = useState(loadStored)

  function persist(next) {
    setSession(next)
    if (next) localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    else localStorage.removeItem(STORAGE_KEY)
  }

  const value = useMemo(
    () => ({
      user: session
        ? { id: session.user_id, email: session.email }
        : null,
      token: session?.access_token ?? null,
      async signup(email, password) {
        const data = await api.signup(email, password)
        persist(data)
        return data
      },
      async login(email, password) {
        const data = await api.login(email, password)
        persist(data)
        return data
      },
      logout() {
        persist(null)
      },
    }),
    [session],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
