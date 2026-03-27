import React, { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import MainPanel from './components/MainPanel'
import SettingsModal from './components/modals/SettingsModal'
import NewEditionModal from './components/modals/NewEditionModal'

export default function App() {
  const [editions, setEditions] = useState([])
  const [selectedEdition, setSelectedEdition] = useState(null)
  const [viewMode, setViewMode] = useState('email')
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light')
  const [contactCount, setContactCount] = useState(null)
  const [showSettings, setShowSettings] = useState(false)
  const [showNewEdition, setShowNewEdition] = useState(false)

  useEffect(() => {
    document.body.classList.toggle('dark', theme === 'dark')
  }, [theme])

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

  useEffect(() => {
    fetch('/api/contacts/count').then(r => r.json()).then(d => setContactCount(d.count))
    if (document.body.dataset.unconfigured) setShowSettings(true)

    const [hashSlug, hashView] = location.hash.slice(1).split('/')
    loadEditions().then(list => {
      if (hashSlug) {
        const match = list.find(e => e.slug === hashSlug)
        if (match) {
          setSelectedEdition(match)
          if (hashView) setViewMode(hashView)
        }
      }
    })
  }, [])

  const selectEdition = (edition) => {
    setSelectedEdition(edition)
    setViewMode('email')
  }

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
        selectedSlug={selectedEdition?.slug}
        onSelect={selectEdition}
        onNewEdition={() => setShowNewEdition(true)}
        onSettings={() => setShowSettings(true)}
      />
      <MainPanel
        edition={selectedEdition}
        viewMode={viewMode}
        theme={theme}
        contactCount={contactCount}
        onViewModeChange={setViewMode}
        onToggleTheme={toggleTheme}
        onEditionUpdated={onEditionUpdated}
      />
      {showSettings && (
        <SettingsModal
          unconfigured={!!document.body.dataset.unconfigured}
          onClose={() => setShowSettings(false)}
        />
      )}
      {showNewEdition && (
        <NewEditionModal
          onClose={() => setShowNewEdition(false)}
          onCreate={(slug) => { setShowNewEdition(false); loadEditions(slug) }}
        />
      )}
    </div>
  )
}
