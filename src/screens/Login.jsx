import { useState } from 'react'
import AuthLayout from '../components/AuthLayout.jsx'

export default function Login({ onLogin, goToSignup }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
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
          <label htmlFor="login-password">Password</label>
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

        <button type="submit" className="btn-submit" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </AuthLayout>
  )
}
