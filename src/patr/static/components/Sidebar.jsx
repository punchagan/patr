import React, { useState, useEffect } from 'react'

function AuthBar() {
  const [status, setStatus] = useState(null)

  const refresh = () => fetch('/api/auth-status').then(r => r.json()).then(setStatus)

  useEffect(() => { refresh() }, [])

  const disconnect = () => fetch('/oauth/disconnect', { method: 'POST' }).then(refresh)

  if (!status) return <div className="auth-bar" />

  return (
    <div className="auth-bar">
      <span className={`auth-dot ${status.needs_credentials || !status.connected ? 'err' : 'ok'}`} />
      <span className="auth-label">
        {status.needs_credentials ? 'No credentials.json' : status.connected ? 'Gmail connected' : 'Not connected'}
      </span>
      {!status.connected && !status.needs_credentials && (
        <a className="btn" href="/oauth/start" style={{ fontSize: 11, padding: '3px 8px' }}>Connect</a>
      )}
      {status.connected && (
        <button className="btn" onClick={disconnect} style={{ fontSize: 11, padding: '3px 8px' }}>Disconnect</button>
      )}
    </div>
  )
}

export default function Sidebar({ editions, selectedSlug, onSelect, onNewEdition, onSettings }) {
  return (
    <aside className="sidebar">
      <AuthBar />
      <div className="sidebar-header">
        Editions
        <span style={{ float: 'right', display: 'flex', gap: 4 }}>
          <button className="btn" onClick={onNewEdition} style={{ fontSize: 11, padding: '2px 7px' }}>+</button>
          <button className="btn" onClick={onSettings} style={{ fontSize: 11, padding: '2px 7px' }}>⚙</button>
        </span>
      </div>
      <div className="edition-list">
        {editions.length === 0 ? (
          <div style={{ padding: 16, color: 'var(--text-placeholder)', fontSize: 13 }}>Loading…</div>
        ) : (
          editions.map(e => (
            <div
              key={e.slug}
              className={`edition-item${e.slug === selectedSlug ? ' active' : ''}`}
              onClick={() => onSelect(e)}
            >
              <div className="edition-title">{e.title}</div>
              <div className="edition-meta">
                <span>{e.date}</span>
                <span className={`badge ${e.draft ? 'badge-draft' : 'badge-live'}`}>
                  {e.draft ? 'Draft' : 'Live'}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </aside>
  )
}
