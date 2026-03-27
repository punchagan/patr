import React from 'react'
import Modal from './Modal'

export default function ConfirmModal({ title, contactCount, onClose, onConfirm }) {
  const count = contactCount ?? '?'
  return (
    <Modal onClose={onClose}>
      <h3>Send to everyone?</h3>
      <p>
        This will send "{title}" to {count} recipient{count !== 1 ? 's' : ''}. This cannot be undone.
      </p>
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={onConfirm}>Send</button>
      </div>
    </Modal>
  )
}
