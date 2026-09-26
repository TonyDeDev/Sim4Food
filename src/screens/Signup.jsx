import { useState } from 'react'
import AuthLayout from '../components/AuthLayout.jsx'

export default function Signup({ onSignup, goToLogin }) {
  const [first, setFirst] = useState('')
  const [last, setLast] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [error, setError] = useState('')

  function handleSubmit(e) {
    e.preventDefault()

    if (password !== password2) {
      setError("Passwords don't match.")
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }

    setError('')
    onSignup({ first, last, email, password })
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
            placeholder="At least 8 characters"
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

        <button type="submit" className="btn-submit">
          Create account
        </button>
      </form>
    </AuthLayout>
  )
}
