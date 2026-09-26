import { useEffect, useRef, useState } from 'react'
import AuthLayout from '../components/AuthLayout.jsx'
import { generateOtp } from '../utils/helpers.js'

export default function Otp({ email, onVerified, onResend }) {
  const [otp, setOtp] = useState(generateOtp())
  const [digits, setDigits] = useState(Array(6).fill(''))
  const [error, setError] = useState('')
  const inputRefs = useRef([])

  useEffect(() => {
    inputRefs.current[0]?.focus()
  }, [])

  function handleChange(index, value) {
    const clean = value.replace(/[^0-9]/g, '').slice(0, 1)
    const next = [...digits]
    next[index] = clean
    setDigits(next)
    if (clean && inputRefs.current[index + 1]) {
      inputRefs.current[index + 1].focus()
    }
  }

  function handleKeyDown(index, e) {
    if (e.key === 'Backspace' && !digits[index] && inputRefs.current[index - 1]) {
      inputRefs.current[index - 1].focus()
    }
  }

  function handleResend() {
    const fresh = generateOtp()
    setOtp(fresh)
    setDigits(Array(6).fill(''))
    setError('')
    inputRefs.current[0]?.focus()
    onResend?.(fresh)
  }

  function handleSubmit(e) {
    e.preventDefault()
    const entered = digits.join('')
    if (entered.length < 6) {
      setError('Enter all 6 digits.')
      return
    }
    if (entered !== otp) {
      setError("That code doesn't match. Try again.")
      return
    }
    setError('')
    onVerified()
  }

  return (
    <AuthLayout quote="One quick check and we were in — no fuss." cite="Priya Anand, Anand & Sons">
      <h1>Confirm your email</h1>
      <p className="lede">We've sent a 6-digit code to {email}.</p>

      <div className="otp-banner">
        This is a demo, so no email actually goes out — your code is <strong>{otp}</strong>.
        {/* Swap this banner for a real email-sending call once there's a backend. */}
      </div>

      <form className="stack" onSubmit={handleSubmit}>
        <div className="otp-boxes">
          {digits.map((digit, i) => (
            <input
              key={i}
              ref={(el) => (inputRefs.current[i] = el)}
              type="text"
              inputMode="numeric"
              maxLength={1}
              value={digit}
              onChange={(e) => handleChange(i, e.target.value)}
              onKeyDown={(e) => handleKeyDown(i, e)}
            />
          ))}
        </div>
        <p className="field-error">{error}</p>
        <button type="submit" className="btn-submit">
          Verify and continue
        </button>
      </form>

      <p className="resend-row">
        Didn't get a code?{' '}
        <a href="#" onClick={(e) => { e.preventDefault(); handleResend() }}>
          Send a new one
        </a>
      </p>
    </AuthLayout>
  )
}
