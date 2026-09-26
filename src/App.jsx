import { useState } from 'react'
import Login from './screens/Login.jsx'
import Signup from './screens/Signup.jsx'
import Otp from './screens/Otp.jsx'
import Dashboard from './screens/Dashboard.jsx'
import IntroPage from './screens/IntroPage.jsx'
import { nameFromEmail } from './utils/helpers.js'
import './App.css'

// 'landing' | 'login' | 'signup' | 'otp' | 'dashboard'
export default function App() {
  const [screen, setScreen] = useState('landing')
  const [user, setUser] = useState(null)
  const [pendingSignup, setPendingSignup] = useState(null)
  const [businesses, setBusinesses] = useState([])

  function handleLogin(email) {
    // No backend yet — derive a placeholder name from the email so the
    // dashboard has something to show. Replace with a real session lookup.
    const derived = nameFromEmail(email)
    setUser({ firstName: derived.first, lastName: derived.last, email })
    setBusinesses([])
    setScreen('dashboard')
  }

  function handleSignup({ first, last, email }) {
    setPendingSignup({ first, last, email })
    setScreen('otp')
  }

  function handleVerified() {
    setUser({ firstName: pendingSignup.first, lastName: pendingSignup.last, email: pendingSignup.email })
    setBusinesses([])
    setScreen('dashboard')
  }

  function handleSignOut() {
    setUser(null)
    setBusinesses([])
    setScreen('landing')
  }

  function handleAddBusiness(business) {
    setBusinesses((prev) => [...prev, business])
  }

  function handleUpdateBusiness(id, updates) {
    setBusinesses((prev) => prev.map((business) => business.id === id ? { ...business, ...updates } : business))
  }

  if (screen === 'landing') {
    return <IntroPage onLogin={() => setScreen('login')} onSignup={() => setScreen('signup')} />
  }

  if (screen === 'login') {
    return <Login onLogin={handleLogin} goToSignup={() => setScreen('signup')} />
  }

  if (screen === 'signup') {
    return <Signup onSignup={handleSignup} goToLogin={() => setScreen('login')} />
  }

  if (screen === 'otp') {
    return <Otp email={pendingSignup.email} onVerified={handleVerified} />
  }

  return <Dashboard user={user} businesses={businesses} onAddBusiness={handleAddBusiness} onUpdateBusiness={handleUpdateBusiness} onSignOut={handleSignOut} />
}
