export function initials(first, last) {
  return ((first || ' ')[0] + (last || ' ')[0]).toUpperCase()
}

// Used on the login screen, where we don't collect a name up front —
// this is a placeholder until a real backend returns the account's name.
export function nameFromEmail(email) {
  const local = email.split('@')[0] || 'friend'
  const parts = local.split(/[.\-_0-9]+/).filter(Boolean)
  const cap = (w) => w.charAt(0).toUpperCase() + w.slice(1)

  if (parts.length >= 2) return { first: cap(parts[0]), last: cap(parts[1]) }
  if (parts.length === 1) return { first: cap(parts[0]), last: 'Owner' }
  return { first: 'Your', last: 'Account' }
}

export function generateOtp() {
  return String(Math.floor(100000 + Math.random() * 900000))
}

export const swatchPalette = ['#8CBF65', '#245C45', '#C9B98A', '#5E9C7C', '#B7DCA0']
