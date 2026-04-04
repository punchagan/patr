import React, { useState, useEffect } from 'react'
import Modal from './Modal'

export default function ConfirmModal({ slug, title, onClose, onConfirm }) {
  const [count, setCount] = useState(null)
  const [missingImages, setMissingImages] = useState(null)

  useEffect(() => {
    fetch('/api/contacts/count').then(r => r.json()).then(d => { if (d.count != null) setCount(d.count) })
    fetch(`/api/edition/${slug}/check-images`).then(r => r.json()).then(d => setMissingImages(d.missing ?? []))
  }, [slug])

  const loading = count === null || missingImages === null
  const blocked = missingImages?.length > 0

  return (
    <Modal onClose={onClose}>
      <h3>Send to everyone?</h3>
      <p>
        This will send "{title}" to {count ?? '…'} recipient{count !== 1 ? 's' : ''}. This cannot be undone.
      </p>
      {blocked && (
        <div className="warning-box">
          <strong>Missing images</strong> — these files are referenced in the edition but don't exist in the edition folder:
          <ul style={{ margin: '6px 0 0', paddingLeft: 20, fontSize: 13 }}>
            {missingImages.map(f => <li key={f}><code>{f}</code></li>)}
          </ul>
          <p style={{ margin: '8px 0 0', fontSize: 13 }}>Upload them before sending.</p>
        </div>
      )}
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={onConfirm} disabled={loading || blocked}>Send</button>
      </div>
    </Modal>
  )
}
