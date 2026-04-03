import React, { useState, useRef, useCallback } from 'react'

const SIDEBAR_WIDTH_KEY = 'patr-sidebar-width'
const MIN_WIDTH = 160
const MAX_WIDTH = 500

export default function Sidebar({ editions, selectedSlug, editingFooter, hidden, onSelect, onFooter, onNewEdition, onSettings, onHelp }) {
  const [width, setWidth] = useState(() => {
    const stored = parseInt(localStorage.getItem(SIDEBAR_WIDTH_KEY), 10)
    return (stored >= MIN_WIDTH && stored <= MAX_WIDTH) ? stored : 260
  })
  const dragging = useRef(false)

  const onMouseDown = useCallback((e) => {
    e.preventDefault()
    dragging.current = true
    const onMouseMove = (e) => {
      if (!dragging.current) return
      // sidebar is on the right; handle is on its left edge
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, window.innerWidth - e.clientX))
      setWidth(newWidth)
    }
    const onMouseUp = (e) => {
      dragging.current = false
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, window.innerWidth - e.clientX))
      localStorage.setItem(SIDEBAR_WIDTH_KEY, newWidth)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }, [])

  const style = hidden ? { display: 'none' } : { width, minWidth: width }

  return (
    <aside className="sidebar" style={style}>
      <div className="sidebar-resize-handle" onMouseDown={onMouseDown} />
      <div className="sidebar-header">
        Editions
        <span style={{ float: 'right', display: 'flex', gap: 4 }}>
          <button className="btn" onClick={onNewEdition} style={{ fontSize: 11, padding: '2px 7px' }}>+</button>
          <button className="btn" onClick={onSettings} style={{ fontSize: 11, padding: '2px 7px' }}>⚙</button>
          <button className="btn" onClick={onHelp} style={{ fontSize: 11, padding: '2px 7px' }}>?</button>
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
      <div
        className={`edition-item footer-item${editingFooter ? ' active' : ''}`}
        onClick={onFooter}
      >
        Footer
      </div>
    </aside>
  )
}
