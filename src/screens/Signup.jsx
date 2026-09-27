import { useState } from 'react'
import AuthLayout from '../components/AuthLayout.jsx'
import { isValidEmail, passwordError } from '../utils/validation.js'

export default function Signup({ onSignup, goToLogin }) {
  const [first, setFirst] = useState('')
  const [last, setLast] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()

    if (!isValidEmail(email)) {
      setError('Please enter a valid email address.')
      return
    }
    if (password !== password2) {
      setError("Passwords don't match.")
      return
    }
    const passwordIssue = passwordError(password)
    if (passwordIssue) {
      setError(passwordIssue)
      return
    }

    setError('')
    setSubmitting(true)
    try {
      await onSignup({ first, last, email, password })
    } catch (err) {
      setError(err.message || 'Could not create your account. Please try again.')
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout
      quote="Set up in an afternoon. We had our first waste report by Friday."
      cite="Marcus Idowu, The Green Table"
    >
      <h1>Create your account</h1>
      <p className="lede">
        Already have one?{' '}
        <a href="#" onClick={(e) => { e.preventDefault(); goToLogin() }}>
          Sign in
        </a>
      </p>

      <form className="stack" onSubmit={handleSubmit}>
        <div className="name-row">
          <div className="field">
            <label htmlFor="signup-first">First name</label>
            <input
              id="signup-first"
              type="text"
              placeholder="Jordan"
              autoComplete="given-name"
              required
              value={first}
              onChange={(e) => setFirst(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="signup-last">Last name</label>
            <input
              id="signup-last"
              type="text"
              placeholder="Ellis"
              autoComplete="family-name"
              required
              value={last}
              onChange={(e) => setLast(e.target.value)}
            />
          </div>
        </div>

        <div className="field">
          <label htmlFor="signup-email">Email</label>
          <input
            id="signup-email"
            type="email"
            placeholder="you@business.com"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="signup-password">Create password</label>
          <input
            id="signup-password"
            type="password"
            placeholder="At least 8 characters, with a number and a symbol"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="signup-password2">Verify password</label>
          <input
            id="signup-password2"
            type="password"
            placeholder="Re-enter your password"
            autoComplete="new-password"
            required
            value={password2}
            onChange={(e) => setPassword2(e.target.value)}
          />
          <p className="field-error">{error}</p>
        </div>

        <button type="submit" className="btn-submit" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
      </form>
    </AuthLayout>
  )
}
