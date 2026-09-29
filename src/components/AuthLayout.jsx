export default function AuthLayout({ children }) {
  return (
    <div className="auth-page">
      <aside className="auth-side">
        <a href="#" className="wordmark">
          Sim4Food
        </a>
        <div className="side-quote">
          <p className="side-slogan">
            <span>Waste less.</span>
            <span>Save more.</span>
            <span>Make an impact.</span>
          </p>
        </div>
        <p className="side-foot">© 2026 Sim4Food</p>
      </aside>
      <main className="auth-form-side">
        <div className="auth-card">{children}</div>
      </main>
    </div>
  )
}
