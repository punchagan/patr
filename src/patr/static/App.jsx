import React, { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import MainPanel from './components/MainPanel'
import SettingsModal from './components/modals/SettingsModal'
import NewEditionModal from './components/modals/NewEditionModal'
import HelpModal from './components/modals/HelpModal'

export default function App() {
  const [editions, setEditions] = useState([])
  const [selectedEdition, setSelectedEdition] = useState(null)
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light')
  const [contactCount, setContactCount] = useState(null)
  const [hasSheetId, setHasSheetId] = useState(false)
  const [editingFooter, setEditingFooter] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showNewEdition, setShowNewEdition] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  const [focusMode, setFocusMode] = useState(false)

  useEffect(() => {
    document.body.classList.toggle('dark', theme === 'dark')
  }, [theme])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') setFocusMode(false)
      if (e.key === 'f' && !e.ctrlKey && !e.metaKey && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA' && !e.target.isContentEditable)
        setFocusMode(f => !f)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const loadEditions = (selectSlug) => {
    return fetch('/api/editions').then(r => r.json()).then(list => {
      setEditions(list)
      if (selectSlug) {
        const match = list.find(e => e.slug === selectSlug)
        if (match) setSelectedEdition(match)
      }
      return list
    })
  }

  const [initialEditorMode] = useState(() => {
    const mode = location.hash.slice(1).split('/')[1] || ''
    return mode === 'split' ? 'split' : (mode === 'email' || mode === 'web') ? 'preview' : 'write'
  })
  const [initialViewMode] = useState(() => {
    const mode = location.hash.slice(1).split('/')[1] || ''
    return mode === 'web' ? 'web' : 'email'
  })

  useEffect(() => {
    fetch('/api/contacts/count').then(r => r.json()).then(d => setContactCount(d.count))
    fetch('/api/settings').then(r => r.json()).then(d => setHasSheetId(!!d.has_sheet_id))
    if (document.body.dataset.unconfigured) setShowSettings(true)

    const hashSlug = location.hash.slice(1).split('/')[0]
    loadEditions().then(list => {
      if (hashSlug) {
        const match = list.find(e => e.slug === hashSlug)
        if (match) setSelectedEdition(match)
      }
    })
  }, [])

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    localStorage.setItem('theme', next)
  }

  const onEditionUpdated = (slug) => {
    loadEditions(slug).then(list => {
      const updated = list.find(e => e.slug === (slug || selectedEdition?.slug))
      if (updated) setSelectedEdition(updated)
    })
  }

  return (
    <div className="layout">
      <Sidebar
        editions={editions}
        selectedSlug={editingFooter ? null : selectedEdition?.slug}
        editingFooter={editingFooter}
        hidden={focusMode}
        onSelect={e => { setSelectedEdition(e); setEditingFooter(false) }}
        onFooter={() => { setSelectedEdition(null); setEditingFooter(true) }}
        onNewEdition={() => setShowNewEdition(true)}
        onSettings={() => setShowSettings(true)}
        onHelp={() => setShowHelp(true)}
      />
      <MainPanel
        edition={selectedEdition}
        editingFooter={editingFooter}
        theme={theme}
        contactCount={contactCount}
        hasSheetId={hasSheetId}
        focusMode={focusMode}
        onToggleFocus={() => setFocusMode(f => !f)}
        onToggleTheme={toggleTheme}
        initialEditorMode={initialEditorMode}
        initialViewMode={initialViewMode}
        onEditionUpdated={onEditionUpdated}
      />
      {showSettings && (
        <SettingsModal
          unconfigured={!!document.body.dataset.unconfigured}
          onClose={() => setShowSettings(false)}
        />
      )}
      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
      {showNewEdition && (
        <NewEditionModal
          onClose={() => setShowNewEdition(false)}
          onCreate={(slug) => { setShowNewEdition(false); loadEditions(slug) }}
        />
      )}
    </div>
  )
}
