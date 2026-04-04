import React, { useMemo } from 'react'
import { diffWords } from 'diff'
import Modal from './Modal'

function DiffView({ mine, theirs }) {
  const parts = useMemo(() => diffWords(theirs, mine), [mine, theirs])
  return (
    <pre className="conflict-diff">
      {parts.map((part, i) => {
        if (part.added) return <span key={i} className="diff-added">{part.value}</span>
        if (part.removed) return <span key={i} className="diff-removed">{part.value}</span>
        return <span key={i}>{part.value}</span>
      })}
    </pre>
  )
}

export default function ConflictModal({ mine, theirs, onKeepMine, onKeepTheirs, onDismiss }) {
  return (
    <div className="conflict-modal modal-overlay visible" onClick={e => e.target === e.currentTarget && onDismiss()}>
      <div className="modal modal-wide">
        <h3>File changed on disk</h3>
        <p>The file was modified outside Patr while you were editing. What do you want to do?</p>
        <DiffView mine={mine} theirs={theirs} />
        <p className="conflict-legend">
          <span className="diff-added">Green</span> = mine &nbsp;
          <span className="diff-removed">Red</span> = disk
        </p>
        <div className="modal-actions">
          <button className="btn" onClick={onDismiss}>Dismiss</button>
          <button className="btn" onClick={onKeepTheirs}>Use disk version</button>
          <button className="btn btn-primary" onClick={onKeepMine}>Keep mine</button>
        </div>
      </div>
    </div>
  )
}
