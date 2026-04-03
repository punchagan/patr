import React, { useState, useEffect } from 'react'
import Modal from './Modal'

export default function ConfirmModal({ title, onClose, onConfirm }) {
  const [count, setCount] = useState(null)
  useEffect(() => {
    fetch('/api/contacts/count').then(r => r.json()).then(d => { if (d.count != null) setCount(d.count) })
  }, [])
  return (
    <Modal onClose={onClose}>
      <h3>Send to everyone?</h3>
      <p>
        This will send "{title}" to {count ?? '…'} recipient{count !== 1 ? 's' : ''}. This cannot be undone.
      </p>
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={onConfirm} disabled={count === null}>Send</button>
      </div>
    </Modal>
  )
}
