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

function DashboardPreview() {
  return (
    <div className="preview-wrap" role="img" aria-label="Illustrative sample Sim4Food dashboard showing a kitchen activity chart and food-use suggestion">
      <div className="preview-card">
        <div className="preview-topline">
          <div className="preview-brand"><Mark /><span>sim4food</span></div>
          <span className="preview-sample">SAMPLE VIEW</span>
        </div>
        <div className="preview-title-row">
          <div><span className="preview-overline">YOUR KITCHEN SNAPSHOT</span><h2>Good morning, Maya</h2></div>
          <div className="preview-avatar">M</div>
        </div>
        <div className="preview-metrics">
          <div className="preview-metric"><span>Food tracked</span><strong>18.6 <small>kg</small></strong><em>across this week</em></div>
          <div className="preview-ring" aria-hidden="true"><span>↗</span></div>
        </div>
        <div className="preview-chart-head"><strong>Kitchen activity</strong><span>THIS WEEK</span></div>
        <div className="preview-chart" aria-hidden="true">
          {[35, 58, 43, 79, 52, 68, 40].map((height, index) => (
            <div className="chart-column" key={index}><i style={{ height: `${height}%` }} /><span>{['M', 'T', 'W', 'T', 'F', 'S', 'S'][index]}</span></div>
          ))}
        </div>
        <div className="preview-tip"><span className="tip-spark">✦</span><p><strong>A little nudge</strong><br />Use leafy greens first in tomorrow’s prep.</p><span className="tip-arrow">↗</span></div>
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
            <h1>Make every<br />ingredient count.</h1>
            <p className="hero-description">A clearer picture of what comes in, what goes out, and where your kitchen can do better.</p>
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
