export default function AuthLayout({ quote, cite, children }) {
  return (
    <div className="auth-page">
      <aside className="auth-side">
        <a href="#" className="wordmark">
          Sim4Food
        </a>
        <div className="side-quote">
          <blockquote>&ldquo;{quote}&rdquo;</blockquote>
          <cite>- {cite}</cite>
        </div>
        <p className="side-foot">© 2026 Sim4Food</p>
      </aside>
      <main className="auth-form-side">
        <div className="auth-card">{children}</div>
      </main>
    </div>
  )
}
