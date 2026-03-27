import React, { useState, useEffect } from 'react'
import Modal from './Modal'

export default function SettingsModal({ unconfigured, onClose }) {
  const [name, setName] = useState('')
  const [sheet, setSheet] = useState('')
  const [contactsResult, setContactsResult] = useState('')
  const [sentLog, setSentLog] = useState(null)

  useEffect(() => {
    fetch('/api/settings').then(r => r.json()).then(d => {
      setName(d.newsletter_name || '')
      setSheet(d.has_sheet_id ? '(saved)' : '')
    })
  }, [])

  const save = () => {
    const payload = {}
    if (name) payload.newsletter_name = name
    if (sheet && sheet !== '(saved)') payload.sheet_id = sheet
    fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(() => onClose())
  }

  const testContacts = () => {
    setContactsResult('Checking…')
    fetch('/api/contacts/count').then(r => r.json()).then(d => {
      setContactsResult(d.error ? `Error: ${d.error}` : `✓ ${d.count} contact${d.count !== 1 ? 's' : ''} with Send=y`)
    })
  }

  const checkSentLog = () => {
    setSentLog('Loading…')
    fetch('/api/sent-log').then(r => r.json()).then(d => {
      if (d.error) { setSentLog(`Error: ${d.error}`); return }
      if (!d.rows || d.rows.length <= 1) { setSentLog('(no entries yet)'); return }
      const [header, ...rows] = d.rows
      let text = [header.join(' | '), ...rows.slice(-10).map(r => r.join(' | '))].join('\n')
      if (rows.length > 10) text = `(showing last 10 of ${rows.length})\n` + text
      setSentLog(text)
    })
  }

  return (
    <Modal onClose={onClose}>
      <h3>Settings</h3>
      {unconfigured && (
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 12px' }}>
          Configure your newsletter to get started.
        </p>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20 }}>
        <label style={{ fontSize: 13 }}>
          Newsletter name
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            style={{ display: 'block', width: '100%', marginTop: 4, padding: '6px 8px', fontSize: 13, background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-primary)', boxSizing: 'border-box' }}
          />
        </label>
        <label style={{ fontSize: 13 }}>
          Contacts sheet ID{' '}
          <span style={{ color: 'var(--text-placeholder)', fontSize: 11 }}>(stored locally, never in repo)</span>
          <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
            <input
              type="text"
              value={sheet}
              onChange={e => setSheet(e.target.value)}
              style={{ flex: 1, padding: '6px 8px', fontSize: 13, background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-primary)', boxSizing: 'border-box' }}
            />
            <button className="btn" onClick={testContacts} style={{ fontSize: 12, whiteSpace: 'nowrap' }}>Test</button>
          </div>
          {contactsResult && <span style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4, display: 'block' }}>{contactsResult}</span>}
        </label>
        <div>
          <button className="btn" onClick={checkSentLog} style={{ fontSize: 12 }}>Check Sent Log</button>
          {sentLog && (
            <pre style={{ marginTop: 8, fontSize: 11, maxHeight: 160, overflowY: 'auto', background: 'var(--bg-secondary)', padding: 8, borderRadius: 4, whiteSpace: 'pre-wrap' }}>
              {sentLog}
            </pre>
          )}
        </div>
      </div>
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={save}>Save</button>
      </div>
    </Modal>
  )
}
