import React, { useMemo } from 'react'
import { diffLines } from 'diff'

function buildRows(mine, theirs) {
  const parts = diffLines(theirs, mine)
  const rows = []
  let i = 0
  while (i < parts.length) {
    const part = parts[i]
    if (!part.added && !part.removed) {
      rows.push({ left: part.value, right: part.value, type: 'same' })
      i++
    } else if (part.removed) {
      if (i + 1 < parts.length && parts[i + 1].added) {
        rows.push({ left: parts[i + 1].value, right: part.value, type: 'changed' })
        i += 2
      } else {
        rows.push({ left: '', right: part.value, type: 'removed' })
        i++
      }
    } else {
      rows.push({ left: part.value, right: '', type: 'added' })
      i++
    }
  }
  return rows
}

function SideBySideDiff({ mine, theirs }) {
  const rows = useMemo(() => buildRows(mine, theirs), [mine, theirs])
  return (
    <div className="conflict-diff-side">
      <div className="conflict-diff-header">
        <div>Mine</div>
        <div>Disk</div>
      </div>
      <div className="conflict-diff-body">
        {rows.map((row, i) => (
          <div key={i} className={`diff-row diff-row-${row.type}`}>
            <pre className="diff-cell diff-cell-left">{row.left}</pre>
            <pre className="diff-cell diff-cell-right">{row.right}</pre>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ConflictModal({ mine, theirs, onKeepMine, onKeepTheirs, onDismiss }) {
  return (
    <div className="conflict-modal modal-overlay visible" onClick={e => e.target === e.currentTarget && onDismiss()}>
      <div className="modal modal-conflict">
        <h3>File changed on disk</h3>
        <p>The file was modified outside Patr while you were editing. What do you want to do?</p>
        <SideBySideDiff mine={mine} theirs={theirs} />
        <div className="modal-actions">
          <button className="btn" onClick={onDismiss}>Dismiss</button>
          <button className="btn" onClick={onKeepTheirs}>Use disk version</button>
          <button className="btn btn-primary" onClick={onKeepMine}>Keep mine</button>
        </div>
      </div>
    </div>
  )
}
