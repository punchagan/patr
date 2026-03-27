import React, { useState, useEffect, useRef } from 'react'
import Modal from './Modal'

export default function NewEditionModal({ onClose, onCreate }) {
  const [title, setTitle] = useState('')
  const [error, setError] = useState(null)
  const inputRef = useRef(null)

  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 50) }, [])

  const create = () => {
    if (!title.trim()) return
    setError(null)
    fetch('/api/new-edition', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) { setError(d.error); return }
        onCreate(d.slug)
      })
  }

  return (
    <Modal onClose={onClose}>
      <h3>New Edition</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20 }}>
        <label style={{ fontSize: 13 }}>
          Title
          <input
            ref={inputRef}
            type="text"
            value={title}
            onChange={e => setTitle(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') create(); if (e.key === 'Escape') onClose() }}
            placeholder="e.g. Spring Edition"
            style={{ display: 'block', width: '100%', marginTop: 4, padding: '6px 8px', fontSize: 13, background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-primary)', boxSizing: 'border-box' }}
          />
        </label>
        {error && <span style={{ fontSize: 12, color: '#f08080' }}>{error}</span>}
      </div>
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={create}>Create</button>
      </div>
    </Modal>
  )
}
