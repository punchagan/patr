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
  const [showSettings, setShowSettings] = useState(false)
  const [showNewEdition, setShowNewEdition] = useState(false)
  const [showHelp, setShowHelp] = useState(false)

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
        selectedSlug={selectedEdition?.slug}
        onSelect={setSelectedEdition}
        onNewEdition={() => setShowNewEdition(true)}
        onSettings={() => setShowSettings(true)}
        onHelp={() => setShowHelp(true)}
      />
      <MainPanel
        edition={selectedEdition}
        theme={theme}
        contactCount={contactCount}
        onToggleTheme={toggleTheme}
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
