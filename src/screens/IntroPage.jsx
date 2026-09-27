import { useEffect } from 'react'

function Mark({ className = '' }) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <rect x="1" y="1" width="38" height="38" rx="13" fill="currentColor" />
      <path d="M20 29V19m0 4c-5.8 0-9-3.2-9-8.5 5.9 0 9 3.1 9 8.5Zm0-3c0-5.5 3.1-8.7 9-8.7 0 5.5-3.2 8.7-9 8.7Z" stroke="#FFF8EA" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function ArrowIcon() {
  return <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M3.75 10h12.5m-5-5 5 5-5 5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
}

// The actual Home tab (InventoryOverview.jsx), reusing its real classes
// (stat-card, inventory-table, badge-*, already loaded globally via App.css)
// with static sample numbers - a live per-user dashboard can't be shown on a
// public marketing page, but the layout, labels and styling are the real ones.
function DashboardPreview() {
  return (
    <div className="preview-wrap" role="img" aria-label="Sample Sim4Food dashboard showing revenue, waste cost, stock health, an upcoming event, and ingredient stock levels">
      <div className="preview-card">
        <div className="preview-topline">
          <div className="preview-brand"><Mark /><span>sim4food</span></div>
          <span className="preview-sample">SAMPLE VIEW</span>
        </div>
        <div className="preview-title-row">
          <div><span className="preview-overline">HOME · THE CORNER CAFÉ</span><h2>This week at a glance</h2></div>
        </div>

        <div className="stat-grid preview-stat-grid" aria-hidden="true">
          <div className="stat-card">
            <p className="stat-label">Revenue (7 days)</p>
            <p className="stat-value">$3,240</p>
            <p className="stat-delta up">+8% vs prior week</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Waste cost (last week)</p>
            <p className="stat-value">$164</p>
            <p className="stat-delta up">-15% vs prior week</p>
          </div>
          <div className="stat-card stat-card-warn">
            <p className="stat-label">Stock health</p>
            <p className="stat-value">1 low</p>
            <p className="stat-sub">Basil: 2.4d left</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Next event</p>
            <p className="stat-value is-long-text">Fall Harvest Deal</p>
            <p className="stat-sub">in 5 days</p>
          </div>
        </div>

        <div className="inventory-table-wrap preview-table-wrap" aria-hidden="true">
          <table className="inventory-table">
            <thead>
              <tr><th>Ingredient</th><th>On hand</th><th>Avg. used / day</th><th>Est. runway</th><th>Status</th></tr>
            </thead>
            <tbody>
              <tr><td>Chicken breast</td><td>4.2 kg</td><td>0.6 kg</td><td>7.0 days</td><td><span className="badge badge-good">OK</span></td></tr>
              <tr><td>Basil</td><td>0.3 kg</td><td>0.15 kg</td><td>2.0 days</td><td><span className="badge badge-warn">Low</span></td></tr>
              <tr><td>Romaine lettuce</td><td>0 kg</td><td>0.4 kg</td><td>0.0 days</td><td><span className="badge badge-bad">Out</span></td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

export default function IntroPage({ onLogin, onSignup }) {
  useEffect(() => {
    const items = document.querySelectorAll('[data-reveal]')
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduceMotion || !('IntersectionObserver' in window)) {
      items.forEach((item) => item.classList.add('is-visible'))
      return undefined
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible')
          observer.unobserve(entry.target)
        }
      })
    }, { threshold: 0.16 })

    items.forEach((item) => observer.observe(item))
    return () => observer.disconnect()
  }, [])

  return (
    <div className="intro-site">
      <header className="intro-nav">
        <a className="intro-wordmark" href="#home" aria-label="Sim4Food home">
          <Mark /><span>sim<span>4</span>food</span>
        </a>
        <nav aria-label="Main navigation">
          <a href="#about">About</a>
          <a href="#how-it-works">How it works</a>
          <a href="#contact">Contact</a>
        </nav>
        <button className="nav-login" onClick={onLogin}>Log in <ArrowIcon /></button>
      </header>

      <main>
        <section className="intro-hero" id="home">
          <div className="hero-copy" data-reveal>
            <div className="hero-kicker"><span className="kicker-dot" /> FOOD WASTE, MADE VISIBLE</div>
            <h1 className="hero-headline-stat">Canada loses $58 billion<br />worth of food every year.</h1>
            <p className="hero-description">Waste less. Save more. Make an impact.</p>
            <div className="hero-actions">
              <button className="hero-primary" onClick={onLogin}>Log in to Sim4Food <ArrowIcon /></button>
              <a className="hero-secondary" href="#how-it-works">Explore the idea <span>↓</span></a>
            </div>
            <div className="hero-note"><span className="note-sun">✳</span> Built for cafés, restaurants, and the people behind every plate.</div>
          </div>
          <a className="scroll-cue" href="#why-it-matters"><span /> Scroll to explore</a>
        </section>

        <section className="preview-section">
          <div className="preview-section-copy" data-reveal>
            <p className="eyebrow">A CLEARER PICTURE</p>
            <h2>See what your<br />kitchen is telling you.</h2>
            <p>Sim4Food is designed to bring inventory, recipes, and sales into one view, so useful patterns are easier to spot.</p>
          </div>
          <div className="preview-frame" data-reveal><DashboardPreview /></div>
        </section>

        <section className="why-section" id="why-it-matters">
          <div className="section-intro" data-reveal>
            <p className="eyebrow">THE CHALLENGE</p>
            <h2>Good food deserves<br />a better chance.</h2>
            <p>Food waste is easy to miss when orders, prep, and sales live in different places. The result is lost ingredients, lost money, and resources spent for no reason.</p>
          </div>
          <div className="why-cards">
            <article className="why-card" data-reveal>
              <span className="why-number">01</span><div className="why-icon icon-cost">$</div>
              <h3>Protect your margins</h3><p>Ingredients that never reach a plate still show up in your costs.</p>
            </article>
            <article className="why-card" data-reveal>
              <span className="why-number">02</span><div className="why-icon icon-leaf">✳</div>
              <h3>Respect what it takes</h3><p>Growing, moving, and preparing food uses land, water, energy, and care.</p>
            </article>
            <article className="why-card" data-reveal>
              <span className="why-number">03</span><div className="why-icon icon-eye">◉</div>
              <h3>See the full picture</h3><p>Without connected information, repeated patterns can stay hidden.</p>
            </article>
          </div>
        </section>

        <section className="how-section" id="how-it-works">
          <div className="how-heading" data-reveal>
            <p className="eyebrow">A SIMPLER WAY FORWARD</p>
            <h2>From daily data<br /><em>to better decisions.</em></h2>
            <p>Sim4Food brings the information you already have into one useful view.</p>
          </div>
          <div className="steps-list">
            <article className="step-card" data-reveal><span className="step-index">01</span><div className="step-art art-stack"><i /><i /><i /></div><div><h3>Bring your records together</h3><p>Start with inventory, recipes, and sales history from your business.</p></div><ArrowIcon /></article>
            <article className="step-card" data-reveal><span className="step-index">02</span><div className="step-art art-scan"><i /><i /><i /></div><div><h3>Spot the patterns</h3><p>See how ingredients move through purchasing, prep, and sales.</p></div><ArrowIcon /></article>
            <article className="step-card" data-reveal><span className="step-index">03</span><div className="step-art art-sprout"><span>✳</span><i /></div><div><h3>Choose a practical next step</h3><p>Use clearer signals to guide ordering and preparation decisions.</p></div><ArrowIcon /></article>
          </div>
        </section>

        <section className="about-section" id="about">
          <div className="about-art" data-reveal aria-hidden="true">
            <div className="about-sun" />
            <div className="plate plate-back" />
            <div className="plate plate-front"><span className="plate-leaf leaf-a" /><span className="plate-leaf leaf-b" /><span className="plate-tomato" /><span className="plate-bean" /></div>
            <div className="about-stamp"><span>LESS WASTE</span><b>✳</b><span>MORE GOOD</span></div>
            <div className="about-caption">A little more care,<br />in every kitchen.</div>
          </div>
          <div className="about-copy" data-reveal>
            <p className="eyebrow">ABOUT SIM4FOOD</p>
            <h2>Better insight.<br /><em>Less food lost.</em></h2>
            <p>Sim4Food is a software idea for food businesses that want to make better use of the ingredients they buy. It aims to connect everyday business records and turn them into a clearer view of food use.</p>
            <p>Our goal is to help kitchens reduce avoidable waste in a way that supports both their business and the planet. We believe the first step is understanding what is happening, without blame or complicated processes.</p>
            <button className="text-link" onClick={onSignup}>Join the journey <ArrowIcon /></button>
          </div>
        </section>

        <section className="contact-section" id="contact">
          <div className="contact-top" data-reveal>
            <div><p className="eyebrow">LET’S MAKE FOOD GO FURTHER</p><h2>Have a question<br />or an idea?</h2></div>
            <a className="contact-email" href="mailto:hello@sim4food.example">hello@sim4food.example <ArrowIcon /></a>
          </div>
          <div className="contact-bottom">
            <a className="intro-wordmark footer-wordmark" href="#home"><Mark /><span>sim<span>4</span>food</span></a>
            <p>Thoughtful tools for a more resourceful food system.</p>
            <div className="social-links"><a href="https://www.instagram.com/" target="_blank" rel="noreferrer">Instagram <span>↗</span></a><a href="https://www.linkedin.com/" target="_blank" rel="noreferrer">LinkedIn <span>↗</span></a></div>
            <small>© 2026 Sim4Food · Contact details are placeholders</small>
          </div>
        </section>
      </main>
    </div>
  )
}
