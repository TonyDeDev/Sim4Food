import { useState } from 'react'
import AuthLayout from '../components/AuthLayout.jsx'

export default function Login({ onLogin, goToSignup }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await onLogin(email, password)
    } catch (err) {
      setError(err.message || 'Could not sign in. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout quote="We finally know where the food was actually going." cite="Dana Wu, Millbrook Cafe">
      <h1>Welcome back</h1>
      <p className="lede">
        New to Sim4Food?{' '}
        <a href="#" onClick={(e) => { e.preventDefault(); goToSignup() }}>
          Create an account
        </a>
      </p>

      <form className="stack" onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="login-email">Email</label>
          <input
            id="login-email"
            type="email"
            placeholder="you@business.com"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="field">
          <div className="password-label-row">
            <label htmlFor="login-password">Password</label>
            <a href="#">Forgot password?</a>
          </div>
          <input
            id="login-password"
            type="password"
            placeholder="Enter your password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <p className="field-error" role="alert">{error}</p>}
        </div>

        <div className="remember-row">
          <input
            type="checkbox"
            id="login-remember"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
          />
          <label htmlFor="login-remember">Stay signed in on this device</label>
        </div>

        <button type="submit" className="btn-submit" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>

      <div className="divider">
        <div className="line" />
        <span>or continue with</span>
        <div className="line" />
      </div>

      <div className="oauth-grid">
        <button className="oauth-btn" type="button" aria-label="Continue with Google">
          <svg viewBox="0 0 24 24">
            <path fill="#4285F4" d="M23.49 12.27c0-.82-.07-1.6-.2-2.36H12v4.47h6.47c-.28 1.5-1.13 2.77-2.4 3.62v3h3.88c2.27-2.09 3.54-5.17 3.54-8.73z" />
            <path fill="#34A853" d="M12 24c3.24 0 5.95-1.07 7.93-2.9l-3.88-3c-1.08.72-2.45 1.15-4.05 1.15-3.12 0-5.76-2.1-6.7-4.93H1.3v3.09C3.26 21.3 7.31 24 12 24z" />
            <path fill="#FBBC05" d="M5.3 14.32c-.24-.72-.38-1.49-.38-2.32s.14-1.6.38-2.32V6.59H1.3A11.98 11.98 0 000 12c0 1.94.46 3.77 1.3 5.41z" />
            <path fill="#EA4335" d="M12 4.75c1.76 0 3.35.6 4.6 1.8l3.44-3.44C17.94 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.3 6.59l4 3.09c.94-2.83 3.58-4.93 6.7-4.93z" />
          </svg>
        </button>
        <button className="oauth-btn" type="button" aria-label="Continue with Apple">
          <svg viewBox="0 0 24 24">
            <path
              fill="#26352D"
              d="M16.36 1c.1 1.14-.32 2.24-1 3.06-.7.84-1.87 1.5-2.98 1.4-.13-1.1.4-2.26 1.05-3.02C14.13 1.55 15.3.94 16.36 1zm3.9 16.6c-.53 1.18-.78 1.7-1.46 2.75-.95 1.45-2.28 3.25-3.93 3.27-1.47.02-1.85-.96-3.84-.95-1.99.01-2.4.97-3.87.95-1.65-.02-2.9-1.65-3.85-3.1-2.64-4.02-2.92-8.73-1.29-11.24 1.16-1.78 2.99-2.83 4.71-2.83 1.75 0 2.85 1 4.3 1 1.4 0 2.26-1 4.3-1 1.53 0 3.15.83 4.3 2.27-3.78 2.07-3.17 7.45.63 8.88z"
            />
          </svg>
        </button>
        <button className="oauth-btn" type="button" aria-label="Continue with email link">
          <svg viewBox="0 0 24 24" fill="none" stroke="#26352D" strokeWidth="1.6">
            <rect x="2.5" y="5" width="19" height="14" rx="2" />
            <path d="M3 6.5l9 6.5 9-6.5" />
          </svg>
        </button>
      </div>

      <p className="signup-note">
        Don&apos;t have an account?{' '}
        <a href="#" onClick={(e) => { e.preventDefault(); goToSignup() }}>
          Sign up for free
        </a>
      </p>
    </AuthLayout>
  )
}
