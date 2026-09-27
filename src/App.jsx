"use client";

import { useCallback, useEffect, useState } from 'react'
import Login from './screens/Login.jsx'
import Signup from './screens/Signup.jsx'
import Dashboard from './screens/Dashboard.jsx'
import IntroPage from './screens/IntroPage.jsx'
import { getSession, listRestaurants, login, logout, signup } from './utils/api.js'

// 'boot' | 'landing' | 'login' | 'signup' | 'dashboard'
export default function App() {
  const [screen, setScreen] = useState('boot')
  const [user, setUser] = useState(null)
  const [businesses, setBusinesses] = useState([])

  useEffect(() => {
    let cancelled = false
    getSession().then(async (sessionUser) => {
      if (cancelled) return
      if (!sessionUser) {
        setScreen('landing')
        return
      }
      setUser(sessionUser)
      const restaurants = await listRestaurants().catch(() => [])
      if (cancelled) return
      setBusinesses(restaurants.map((r) => ({
        id: r.id, name: r.name, type: r.business_type || '', location: r.location || '', files: {},
      })))
      setScreen('dashboard')
    })
    return () => { cancelled = true }
  }, [])

  async function handleLogin(email, password) {
    const loggedInUser = await login({ email, password })
    const restaurants = await listRestaurants().catch(() => [])
    setUser(loggedInUser)
    setBusinesses(restaurants.map((r) => ({
      id: r.id, name: r.name, type: r.business_type || '', location: r.location || '', files: {},
    })))
    setScreen('dashboard')
  }

  async function handleSignup({ first, last, email, password }) {
    const newUser = await signup({ first, last, email, password })
    setUser(newUser)
    setBusinesses([])
    setScreen('dashboard')
  }

  async function handleSignOut() {
    await logout().catch(() => {})
    setUser(null)
    setBusinesses([])
    setScreen('landing')
  }

  function handleAddBusiness(business) {
    setBusinesses((prev) => [...prev, business])
  }

  // Stable identity: Dashboard re-hydrates upload status in an effect that depends on it.
  const handleUpdateBusiness = useCallback((id, updates) => {
    setBusinesses((prev) => prev.map((business) => business.id === id ? { ...business, ...updates } : business))
  }, [])

  // Merges against the latest state rather than a captured snapshot: uploads
  // run concurrently and finish out of order, so a caller-built files map can
  // be stale by the time the slowest one lands and would clobber the others.
  function handleUploadRecord(id, key, filename) {
    setBusinesses((prev) => prev.map((business) => business.id === id
      ? { ...business, files: { ...business.files, [key]: filename } }
      : business))
  }

  if (screen === 'boot') {
    return null
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

  return <Dashboard user={user} businesses={businesses} onAddBusiness={handleAddBusiness} onUpdateBusiness={handleUpdateBusiness} onUploadRecord={handleUploadRecord} onSignOut={handleSignOut} />
}
