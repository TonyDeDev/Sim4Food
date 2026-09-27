'use client'

// TEMPORARY preview route for eyeballing SimView against a recorded fixture
// without needing a login or a database. Delete before committing.
import SimView from '../../components/SimView.jsx'
import fixture from './fixture.json'

export default function SimViewPreview() {
  return <div style={{ padding: 24, background: 'var(--cream)', minHeight: '100vh' }}>
    <div className="whatif-results" style={{ maxWidth: 1100, margin: '0 auto' }}>
      <SimView replay={fixture.replay} runs={fixture.runs} />
    </div>
  </div>
}
