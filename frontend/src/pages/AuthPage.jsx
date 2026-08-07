import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { formatError } from '../api'
import { useAuth } from '../auth'

export default function AuthPage() {
  const { user, login, signup } = useAuth()
  const navigate = useNavigate()
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/" replace />

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      if (mode === 'login') await login(email, password)
      else await signup(email, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(formatError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-panel">
        <p className="brand-mark">Orderflow</p>
        <h1>{mode === 'login' ? 'Welcome back' : 'Create account'}</h1>
        <p className="lede">
          Reserve inventory under contention, then pay or cancel before expiry.
        </p>

        <form className="stack" onSubmit={onSubmit}>
          <label>
            Email
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>

          {error ? <p className="banner error">{error}</p> : null}

          <button className="btn primary" type="submit" disabled={busy}>
            {busy ? 'Working…' : mode === 'login' ? 'Log in' : 'Sign up'}
          </button>
        </form>

        <p className="switch-mode">
          {mode === 'login' ? (
            <>
              New here?{' '}
              <button type="button" className="linkish" onClick={() => setMode('signup')}>
                Create an account
              </button>
            </>
          ) : (
            <>
              Already have an account?{' '}
              <button type="button" className="linkish" onClick={() => setMode('login')}>
                Log in
              </button>
            </>
          )}
        </p>
      </div>
    </main>
  )
}
