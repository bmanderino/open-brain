import { useState, useEffect, useRef } from 'react'

const API = (window.__BRAIN_CONFIG__?.apiUrl) || 'http://localhost:8000'

const css = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #0a0a0f;
    --bg2: #0f0f1a;
    --bg3: #141428;
    --border: #1e1e3a;
    --border-hi: #2e2e5a;
    --accent: #4af;
    --accent2: #a4f;
    --accent-dim: rgba(68, 170, 255, 0.12);
    --text: #c8d0e8;
    --text-dim: #5a6080;
    --text-hi: #eef2ff;
    --green: #4fd;
    --red: #f64;
    --font-display: 'Syne', sans-serif;
    --font-mono: 'Martian Mono', monospace;
  }

  html, body, #root {
    height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-mono);
    font-size: 13px;
    line-height: 1.6;
    overflow: hidden;
  }

  .app {
    display: grid;
    grid-template-rows: auto 1fr;
    height: 100vh;
    overflow: hidden;
  }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 28px;
    border-bottom: 1px solid var(--border);
    background: var(--bg2);
    flex-shrink: 0;
  }

  .logo {
    display: flex;
    align-items: baseline;
    gap: 10px;
  }

  .logo-text {
    font-family: var(--font-display);
    font-size: 22px;
    font-weight: 800;
    color: var(--text-hi);
    letter-spacing: -0.5px;
  }

  .logo-text span { color: var(--accent); }

  .logo-sub {
    font-size: 11px;
    color: var(--text-dim);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 8px var(--green);
    animation: pulse 2.5s ease-in-out infinite;
  }

  .status-dot.offline {
    background: var(--red);
    box-shadow: 0 0 8px var(--red);
    animation: none;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  .main {
    display: grid;
    grid-template-columns: 380px 1fr;
    overflow: hidden;
  }

  .left-panel {
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--border);
    overflow: hidden;
    background: var(--bg2);
  }

  .panel-section {
    padding: 20px;
    border-bottom: 1px solid var(--border);
  }

  .section-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: var(--text-dim);
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .section-label::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  textarea {
    width: 100%;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text-hi);
    font-family: var(--font-mono);
    font-size: 12.5px;
    line-height: 1.7;
    padding: 12px 14px;
    resize: none;
    outline: none;
    transition: border-color 0.15s;
    min-height: 110px;
  }

  textarea:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-dim);
  }

  textarea::placeholder { color: var(--text-dim); }

  .tags-row {
    display: flex;
    gap: 6px;
    margin-top: 8px;
    flex-wrap: wrap;
    align-items: center;
  }

  .tag-input {
    background: transparent;
    border: none;
    outline: none;
    color: var(--accent2);
    font-family: var(--font-mono);
    font-size: 11px;
    width: 120px;
  }

  .tag-input::placeholder { color: var(--text-dim); }

  .tag-chip {
    background: rgba(164, 68, 255, 0.1);
    border: 1px solid rgba(164, 68, 255, 0.25);
    color: var(--accent2);
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    cursor: pointer;
    transition: background 0.1s;
  }

  .tag-chip:hover { background: rgba(164, 68, 255, 0.2); }

  .ingest-btn {
    margin-top: 10px;
    width: 100%;
    background: var(--accent);
    border: none;
    border-radius: 5px;
    color: #000;
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 9px;
    cursor: pointer;
    transition: opacity 0.15s, transform 0.1s;
  }

  .ingest-btn:hover { opacity: 0.85; }
  .ingest-btn:active { transform: scale(0.98); }
  .ingest-btn:disabled { opacity: 0.35; cursor: not-allowed; }

  .feedback {
    margin-top: 8px;
    font-size: 11px;
    min-height: 16px;
  }

  .feedback.ok { color: var(--green); }
  .feedback.err { color: var(--red); }

  .entries-list {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .entries-list::-webkit-scrollbar { width: 4px; }
  .entries-list::-webkit-scrollbar-track { background: transparent; }
  .entries-list::-webkit-scrollbar-thumb { background: var(--border-hi); border-radius: 2px; }

  .entry-card {
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 11px 13px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
    animation: fadeIn 0.25s ease forwards;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .entry-card:hover {
    border-color: var(--border-hi);
    background: var(--bg);
  }

  .entry-content {
    color: var(--text);
    font-size: 12px;
    line-height: 1.6;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .entry-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 7px;
    flex-wrap: wrap;
  }

  .entry-date { font-size: 10px; color: var(--text-dim); }
  .entry-source { font-size: 10px; color: var(--accent); opacity: 0.7; }
  .entry-tag { font-size: 10px; color: var(--accent2); opacity: 0.8; }

  .entry-delete {
    margin-left: auto;
    background: transparent;
    border: none;
    color: var(--text-dim);
    font-size: 13px;
    cursor: pointer;
    padding: 0 2px;
    line-height: 1;
    opacity: 0;
    transition: opacity 0.15s, color 0.15s;
  }

  .entry-card:hover .entry-delete { opacity: 1; }
  .entry-delete:hover { color: var(--red) !important; }

  .entry-actions {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .act {
    background: transparent;
    border: none;
    color: var(--text-dim);
    font-family: var(--font-mono);
    font-size: 10px;
    cursor: pointer;
    padding: 0;
    transition: opacity 0.15s, color 0.15s;
  }

  .act:hover { color: var(--accent); }
  .entry-card .act { opacity: 0; }
  .entry-card:hover .act { opacity: 1; }

  .badge-pin, .badge-sup {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 1px 5px;
    border-radius: 3px;
  }

  .badge-pin {
    background: rgba(68, 255, 221, 0.08);
    border: 1px solid rgba(68, 255, 221, 0.25);
    color: var(--green);
  }

  .badge-sup {
    background: rgba(255, 102, 68, 0.08);
    border: 1px solid rgba(255, 102, 68, 0.25);
    color: var(--red);
  }

  .superseded { opacity: 0.55; }

  .toggle-row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
    color: var(--text-dim);
    cursor: pointer;
    user-select: none;
  }

  .related-panel {
    border: 1px solid var(--border-hi);
    border-radius: 6px;
    background: var(--bg2);
    padding: 12px 14px;
    font-size: 11px;
    color: var(--text-dim);
  }

  .related-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
    color: var(--accent2);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .related-head span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .related-item {
    padding: 8px 0;
    border-top: 1px solid var(--border);
    cursor: pointer;
  }

  .related-item .entry-content { color: var(--text-hi); }

  .entry-type {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 1px 5px;
    border-radius: 3px;
    background: rgba(68, 170, 255, 0.08);
    border: 1px solid rgba(68, 170, 255, 0.2);
    color: var(--accent);
    opacity: 0.8;
  }

  .entry-topics {
    font-size: 10px;
    color: var(--text-dim);
    font-style: italic;
    margin-top: 4px;
  }

  .result-type {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 1px 6px;
    border-radius: 3px;
    background: rgba(68, 170, 255, 0.08);
    border: 1px solid rgba(68, 170, 255, 0.2);
    color: var(--accent);
    margin-left: 6px;
  }

  .result-actions {
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
    font-size: 11px;
    color: var(--text-dim);
  }

  .result-actions-label {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--accent2);
    margin-bottom: 4px;
  }

  .right-panel {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--bg);
  }

  .search-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 18px 24px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .search-prefix {
    color: var(--accent);
    font-size: 16px;
    flex-shrink: 0;
  }

  .search-input {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: var(--text-hi);
    font-family: var(--font-mono);
    font-size: 14px;
    caret-color: var(--accent);
  }

  .search-input::placeholder { color: var(--text-dim); }

  .search-btn {
    background: transparent;
    border: 1px solid var(--border-hi);
    border-radius: 4px;
    color: var(--accent);
    font-family: var(--font-mono);
    font-size: 11px;
    padding: 5px 12px;
    cursor: pointer;
    transition: background 0.15s;
    flex-shrink: 0;
  }

  .search-btn:hover { background: var(--accent-dim); }

  .results-area {
    flex: 1;
    overflow-y: auto;
    padding: 20px 24px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .results-area::-webkit-scrollbar { width: 4px; }
  .results-area::-webkit-scrollbar-track { background: transparent; }
  .results-area::-webkit-scrollbar-thumb { background: var(--border-hi); border-radius: 2px; }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    gap: 12px;
    color: var(--text-dim);
    text-align: center;
  }

  .empty-glyph { font-size: 40px; opacity: 0.3; }

  .empty-label {
    font-family: var(--font-display);
    font-size: 15px;
    color: var(--text-dim);
  }

  .empty-sub {
    font-size: 11px;
    color: var(--text-dim);
    opacity: 0.6;
    max-width: 280px;
  }

  .result-card {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: 6px;
    padding: 14px 16px;
    animation: fadeIn 0.2s ease forwards;
  }

  .result-score {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 10px;
    color: var(--accent);
    margin-bottom: 8px;
  }

  .score-bar {
    height: 3px;
    width: 60px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
  }

  .score-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transition: width 0.3s ease;
  }

  .result-content {
    color: var(--text-hi);
    font-size: 12.5px;
    line-height: 1.7;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .result-meta {
    display: flex;
    gap: 10px;
    margin-top: 10px;
    font-size: 10px;
    color: var(--text-dim);
    flex-wrap: wrap;
  }

  .loading-row {
    display: flex;
    gap: 5px;
    align-items: center;
    color: var(--text-dim);
    font-size: 12px;
    padding: 20px 0;
  }

  .dot-anim span { animation: blink 1.2s infinite; display: inline-block; }
  .dot-anim span:nth-child(2) { animation-delay: 0.2s; }
  .dot-anim span:nth-child(3) { animation-delay: 0.4s; }

  @keyframes blink {
    0%, 80%, 100% { opacity: 0; }
    40% { opacity: 1; }
  }
`

// The API's error text for a failed response, or a bare status when there is none.
async function errorDetail(r) {
  try {
    const d = await r.json()
    if (typeof d.detail === 'string') return d.detail
  } catch {}
  return `HTTP ${r.status}`
}

export default function App() {
  const [content, setContent] = useState('')
  const [tagInput, setTagInput] = useState('')
  const [tags, setTags] = useState([])
  const [ingesting, setIngesting] = useState(false)
  const [feedback, setFeedback] = useState(null)

  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState(null)
  const [searchError, setSearchError] = useState(null)

  const [entries, setEntries] = useState([])
  const [online, setOnline] = useState(false)
  const [loadError, setLoadError] = useState(null)
  const [showSuperseded, setShowSuperseded] = useState(false)
  const [related, setRelated] = useState(null)

  useEffect(() => {
    fetch(`${API}/health`)
      .then(r => r.ok ? setOnline(true) : setOnline(false))
      .catch(() => setOnline(false))
  }, [])

  useEffect(() => {
    loadEntries()
  }, [showSuperseded])

  async function loadEntries() {
    try {
      const r = await fetch(`${API}/entries?limit=30&include_superseded=${showSuperseded}`)
      if (!r.ok) throw new Error(await errorDetail(r))
      const d = await r.json()
      setEntries(d.entries || [])
      setLoadError(null)
    } catch (err) {
      setLoadError(err instanceof TypeError ? 'could not reach Brain API' : err.message)
    }
  }

  function addTag(e) {
    if ((e.key === 'Enter' || e.key === ',') && tagInput.trim()) {
      e.preventDefault()
      const t = tagInput.trim().replace(/,/g, '')
      if (t && !tags.includes(t)) setTags([...tags, t])
      setTagInput('')
    }
  }

  function removeTag(t) {
    setTags(tags.filter(x => x !== t))
  }

  async function ingest() {
    if (!content.trim()) return
    setIngesting(true)
    setFeedback(null)
    try {
      const r = await fetch(`${API}/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, tags, source: 'web-ui' }),
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      const d = await r.json()
      if (d.duplicate_of) {
        setFeedback({ type: 'err', msg: '= not stored: a near-duplicate entry already exists' })
        setContent('')
        setTags([])
        return
      }
      const typeLabel = d.metadata?.type && d.metadata.type !== 'other'
        ? ` [${d.metadata.type.replace('_', ' ')}]`
        : ''
      const topicsLabel = d.metadata?.topics?.length
        ? ` — ${d.metadata.topics.join(', ')}`
        : ''
      const metaNote = d.metadata_status === 'failed' ? ' (metadata extraction failed)' : ''
      const similar = d.possibly_supersedes?.length
        ? ` -- ${d.possibly_supersedes.length} similar, see right panel`
        : ''
      setFeedback({ type: 'ok', msg: `-> stored in brain${typeLabel}${topicsLabel}${metaNote}${similar}` })
      if (d.possibly_supersedes?.length) {
        setRelated({
          entry: { id: d.id, content },
          title: 'possibly replaces',
          items: d.possibly_supersedes,
        })
      }
      setContent('')
      setTags([])
      loadEntries()
    } catch (err) {
      const msg = err instanceof TypeError ? 'could not reach Brain API' : err.message
      setFeedback({ type: 'err', msg: `x ${msg}` })
    } finally {
      setIngesting(false)
    }
  }

  async function search() {
    if (!query.trim()) return
    setSearching(true)
    setResults(null)
    setSearchError(null)
    try {
      const r = await fetch(`${API}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, limit: 8, include_superseded: showSuperseded }),
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      const d = await r.json()
      setResults(d.results || [])
    } catch (err) {
      setSearchError(err instanceof TypeError ? 'could not reach Brain API' : err.message)
    } finally {
      setSearching(false)
    }
  }

  function handleSearchKey(e) {
    if (e.key === 'Enter') search()
  }

  function handleIngestKey(e) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) ingest()
  }

  async function deleteEntry(id, e) {
    e.stopPropagation()
    const entry = entries.find(x => x.id === id)
    const preview = entry ? entry.content.slice(0, 80) : ''
    if (!window.confirm(`Delete this entry permanently?\n\n${preview}`)) return
    try {
      const r = await fetch(`${API}/entries/${id}`, { method: 'DELETE' })
      // 404 means it is already gone, which is what the user wanted
      if (!r.ok && r.status !== 404) throw new Error(await errorDetail(r))
      setEntries(prev => prev.filter(x => x.id !== id))
    } catch (err) {
      const msg = err instanceof TypeError ? 'could not reach Brain API' : err.message
      setFeedback({ type: 'err', msg: `x could not delete: ${msg}` })
    }
  }

  const errorText = err => (err instanceof TypeError ? 'could not reach Brain API' : err.message)

  async function patchEntry(id, body) {
    try {
      const r = await fetch(`${API}/entries/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      return await r.json()
    } catch (err) {
      setFeedback({ type: 'err', msg: `x could not update: ${errorText(err)}` })
      return null
    }
  }

  // Mirror a PATCH response into every list that shows the entry. An entry that just became
  // superseded leaves the lists unless superseded entries are being shown.
  function applyUpdate(u) {
    const hide = !!u.superseded_by && !showSuperseded
    const apply = list => list && (hide
      ? list.filter(x => x.id !== u.id)
      : list.map(x => x.id === u.id ? { ...x, pinned: u.pinned, superseded_by: u.superseded_by } : x))
    setEntries(apply)
    setResults(apply)
    setRelated(prev => prev && { ...prev, items: apply(prev.items) })
  }

  async function togglePin(item, ev) {
    ev.stopPropagation()
    const u = await patchEntry(item.id, { pinned: !item.pinned })
    if (u) applyUpdate(u)
  }

  async function setSuperseded(id, newId) {
    const u = await patchEntry(id, { superseded_by: newId })
    if (u) applyUpdate(u)
  }

  async function openRelated(item, ev) {
    ev.stopPropagation()
    const entry = { id: item.id, content: item.content }
    setRelated({ entry, title: 'related to', items: [], loading: true })
    const keep = update => setRelated(prev => (prev && prev.entry.id === entry.id ? { ...prev, ...update } : prev))
    try {
      const r = await fetch(`${API}/entries/${item.id}/related?include_superseded=${showSuperseded}`)
      if (!r.ok) throw new Error(await errorDetail(r))
      const d = await r.json()
      keep({ items: d.related || [], loading: false })
    } catch (err) {
      keep({ items: [], loading: false, error: errorText(err) })
    }
  }

  function itemBadges(item) {
    return (
      <>
        {item.pinned && <span className="badge-pin">pinned</span>}
        {item.superseded_by && <span className="badge-sup">superseded</span>}
      </>
    )
  }

  function itemActions(item) {
    return (
      <>
        <button className="act" onClick={ev => togglePin(item, ev)}>{item.pinned ? 'unpin' : 'pin'}</button>
        <button className="act" onClick={ev => openRelated(item, ev)}>related</button>
        {item.superseded_by && (
          <button className="act" onClick={ev => { ev.stopPropagation(); setSuperseded(item.id, '') }}>restore</button>
        )}
      </>
    )
  }

  function formatDate(iso) {
    if (!iso) return ''
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  return (
    <>
      <style>{css}</style>
      <div className="app">
        <header className="header">
          <div className="logo">
            <span className="logo-text">open<span>brain</span></span>
            <span className="logo-sub">knowledge layer</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: 'var(--text-dim)' }}>
            <div className={`status-dot ${online ? '' : 'offline'}`} />
            {online ? 'connected' : 'offline'}
          </div>
        </header>

        <div className="main">
          <div className="left-panel">
            <div className="panel-section">
              <div className="section-label">capture</div>
              <textarea
                placeholder="Drop a thought, decision, note, link... (Ctrl+Enter to save)"
                value={content}
                onChange={e => setContent(e.target.value)}
                onKeyDown={handleIngestKey}
              />
              <div className="tags-row">
                {tags.map(t => (
                  <span key={t} className="tag-chip" onClick={() => removeTag(t)}>
                    #{t} x
                  </span>
                ))}
                <input
                  className="tag-input"
                  placeholder="+ tag, enter"
                  value={tagInput}
                  onChange={e => setTagInput(e.target.value)}
                  onKeyDown={addTag}
                />
              </div>
              <button
                className="ingest-btn"
                onClick={ingest}
                disabled={ingesting || !content.trim()}
              >
                {ingesting ? 'storing...' : 'store in brain ->'}
              </button>
              {feedback && (
                <div className={`feedback ${feedback.type}`}>{feedback.msg}</div>
              )}
            </div>

            <div className="panel-section" style={{ paddingBottom: 12 }}>
              <div className="section-label">recent</div>
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={showSuperseded}
                  onChange={e => setShowSuperseded(e.target.checked)}
                />
                show superseded
              </label>
            </div>

            <div className="entries-list">
              {loadError && (
                <div className="feedback err" style={{ textAlign: 'center', marginTop: 20 }}>
                  x could not load entries: {loadError}
                </div>
              )}
              {entries.length === 0 && !loadError && (
                <div style={{ color: 'var(--text-dim)', fontSize: 11, textAlign: 'center', marginTop: 20 }}>
                  nothing stored yet
                </div>
              )}
              {entries.map(e => (
                <div key={e.id} className={`entry-card${e.superseded_by ? ' superseded' : ''}`} onClick={() => {
                  setQuery(e.content.slice(0, 60))
                  setResults(null)
                }}>
                  <div className="entry-content">{e.content}</div>
                  <div className="entry-meta">
                    <span className="entry-date">{formatDate(e.created_at)}</span>
                    <span className="entry-source">via {e.source}</span>
                    {itemBadges(e)}
                    {e.type && e.type !== 'other' && (
                      <span className="entry-type">{e.type.replace('_', ' ')}</span>
                    )}
                    {e.tags?.map(t => (
                      <span key={t} className="entry-tag">#{t}</span>
                    ))}
                    <span className="entry-actions">
                      {itemActions(e)}
                      <button className="entry-delete" onClick={(ev) => deleteEntry(e.id, ev)} title="delete">✕</button>
                    </span>
                  </div>
                  {e.topics?.length > 0 && (
                    <div className="entry-topics">{e.topics.join(' · ')}</div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="right-panel">
            <div className="search-bar">
              <span className="search-prefix">&#9906;</span>
              <input
                className="search-input"
                placeholder="search your brain by meaning, not just keywords..."
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={handleSearchKey}
              />
              <button className="search-btn" onClick={search} disabled={searching}>
                {searching ? '...' : 'search'}
              </button>
            </div>

            <div className="results-area">
              {related && (
                <div className="related-panel">
                  <div className="related-head">
                    <span>{related.title}: {related.entry.content.slice(0, 60)}</span>
                    <button className="act" onClick={() => setRelated(null)} title="close">✕</button>
                  </div>
                  {related.loading && <div>finding similar entries...</div>}
                  {related.error && <div style={{ color: 'var(--red)' }}>x {related.error}</div>}
                  {!related.loading && !related.error && related.items.length === 0 && (
                    <div>nothing similar enough</div>
                  )}
                  {related.items.map(n => (
                    <div key={n.id} className="related-item" onClick={ev => openRelated(n, ev)}>
                      <div className="entry-content">{n.content}</div>
                      <div className="entry-meta">
                        <span className="entry-date">{formatDate(n.created_at)}</span>
                        <span>{(n.score * 100).toFixed(0)}% similar</span>
                        {itemBadges(n)}
                        <span className="entry-actions">
                          <button
                            className="act"
                            title="mark this entry as replaced by the one above"
                            onClick={ev => { ev.stopPropagation(); setSuperseded(n.id, related.entry.id) }}
                          >
                            outdated
                          </button>
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {searchError && (
                <div className="empty-state">
                  <div className="empty-glyph">&#9888;</div>
                  <div className="empty-label">search failed</div>
                  <div className="empty-sub">{searchError}</div>
                </div>
              )}

              {!results && !searching && !searchError && (
                <div className="empty-state">
                  <div className="empty-glyph">&#9678;</div>
                  <div className="empty-label">semantic search</div>
                  <div className="empty-sub">
                    search by meaning -- "why I chose postgres" will surface entries about database decisions even if those exact words are not there
                  </div>
                </div>
              )}

              {searching && (
                <div className="loading-row">
                  querying brain
                  <span className="dot-anim">
                    <span>.</span><span>.</span><span>.</span>
                  </span>
                </div>
              )}

              {results && results.length === 0 && (
                <div className="empty-state">
                  <div className="empty-glyph">&#8709;</div>
                  <div className="empty-label">no results</div>
                  <div className="empty-sub">try rephrasing, or store more thoughts first</div>
                </div>
              )}

              {results?.map((r, i) => (
                <div key={r.id} className={`result-card${r.superseded_by ? ' superseded' : ''}`} style={{ animationDelay: `${i * 0.04}s` }}>
                  <div className="result-score">
                    <span>{(r.score * 100).toFixed(0)}% match</span>
                    <div className="score-bar">
                      <div className="score-fill" style={{ width: `${r.score * 100}%` }} />
                    </div>
                    {r.metadata?.type && r.metadata.type !== 'other' && (
                      <span className="result-type">{r.metadata.type.replace('_', ' ')}</span>
                    )}
                  </div>
                  <div className="result-content">{r.content}</div>
                  <div className="result-meta">
                    <span>{formatDate(r.created_at)}</span>
                    <span>via {r.source}</span>
                    {r.tags?.map(t => <span key={t}>#{t}</span>)}
                    {itemBadges(r)}
                    {r.metadata?.topics?.map(t => (
                      <span key={t} style={{ color: 'var(--accent)', opacity: 0.6 }}>{t}</span>
                    ))}
                    {r.metadata?.people?.map(p => (
                      <span key={p} style={{ color: 'var(--accent2)', opacity: 0.6 }}>{p}</span>
                    ))}
                    <span className="entry-actions">{itemActions(r)}</span>
                  </div>
                  {r.metadata?.action_items?.length > 0 && (
                    <div className="result-actions">
                      <div className="result-actions-label">action items</div>
                      {r.metadata.action_items.map((a, j) => (
                        <div key={j}>- {a}</div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
