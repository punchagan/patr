import React from 'react'

export default function Modal({ onClose, children }) {
  return (
    <div className="modal-overlay visible" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">{children}</div>
    </div>
  )
}
