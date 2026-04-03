import React, { useState, useEffect, useRef } from 'react'
import TestSendModal from './modals/TestSendModal'
import ConfirmModal from './modals/ConfirmModal'
import EditorPanel from './EditorPanel'

function useDeployStatus(edition) {
  const [deploymentLive, setDeploymentLive] = useState(false)
  const [status, setStatus] = useState(null)

  useEffect(() => {
    if (!edition) { setStatus(null); setDeploymentLive(false); return }
    setStatus({ cls: 'info', text: 'Checking deployment…' })
    fetch(`/api/check-deployment/${edition.slug}`)
      .then(r => r.json())
      .then(d => {
        setDeploymentLive(d.live)
        if (d.live) setStatus({ cls: 'ok', text: 'Live ✓' })
        else setStatus({ cls: 'warn', text: d.reason ? `Not live: ${d.reason}` : 'Not deployed yet' })
      })
  }, [edition?.slug])

  return { deploymentLive, status, setStatus, setDeploymentLive }
}

function PreviewFrame({ slug, viewMode, previewKey }) {
  return (
    <iframe
      key={`${slug}-${viewMode}-${previewKey}`}
      className="preview-frame"
      src={`/preview/${slug}/${viewMode}`}
    />
  )
}

function ViewToggle({ viewMode, onViewModeChange }) {
  return (
    <>
      <button className={`btn btn-toggle${viewMode === 'email' ? ' active' : ''}`} onClick={() => onViewModeChange('email')}>Email</button>
      <button className={`btn btn-toggle${viewMode === 'web' ? ' active' : ''}`} onClick={() => onViewModeChange('web')}>Web</button>
    </>
  )
}

export default function MainPanel({ edition, editingFooter, theme, hasSheetId, gmailConnected, focusMode, onToggleFocus, onToggleTheme, onEditionUpdated, initialEditorMode = 'write', initialViewMode = 'email' }) {
  const [draft, setDraft] = useState(edition?.draft ?? true)
  const [editorMode, setEditorMode] = useState(initialEditorMode)
  const [viewMode, setViewMode] = useState(initialViewMode)
  const [previewKey, setPreviewKey] = useState(0)
  const [showTestSend, setShowTestSend] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const { deploymentLive, status, setStatus, setDeploymentLive } = useDeployStatus(edition)
  const isInitialLoad = useRef(true)

  useEffect(() => {
    setDraft(edition?.draft ?? true)
    if (isInitialLoad.current && edition) {
      isInitialLoad.current = false
      setEditorMode(initialEditorMode)
      setViewMode(initialViewMode)
    } else if (!isInitialLoad.current) {
      setEditorMode('write')
      setViewMode('email')
    }
  }, [edition?.slug])

  useEffect(() => {
    if (!edition) return
    const suffix = editorMode === 'split' ? '/split'
      : editorMode === 'preview' ? `/${viewMode}`
      : ''
    history.replaceState(null, '', `#${edition.slug}${suffix}`)
  }, [edition?.slug, editorMode, viewMode])

  const toggleDraft = () => {
    fetch(`/api/toggle-draft/${edition.slug}`, { method: 'POST' })
      .then(r => r.json())
      .then(d => { setDraft(d.draft); onEditionUpdated(edition.slug) })
  }

  const doPublish = () => {
    setStatus({ cls: 'info', text: 'Publishing…' })
    fetch(`/api/publish/${edition.slug}`, { method: 'POST' })
      .then(r => r.json())
      .then(d => {
        if (d.ok) { setStatus({ cls: 'ok', text: 'Published ✓' }); setDeploymentLive(true) }
        else setStatus({ cls: 'err', text: `Publish failed: ${d.error}` })
      })
  }

  const onTestSent = (d) => {
    if (d.ok) setStatus({ cls: 'ok', text: `Test sent to ${d.sent} recipient${d.sent !== 1 ? 's' : ''} ✓` })
    else setStatus({ cls: 'err', text: `Error: ${d.error}` })
  }

  const onSent = (d) => {
    if (d.ok) {
      let msg = `Sent to ${d.sent} recipient${d.sent !== 1 ? 's' : ''} ✓`
      if (d.skipped) msg += `, ${d.skipped} already sent`
      if (d.failed?.length) msg += `, ${d.failed.length} failed`
      setStatus({ cls: d.failed?.length ? 'warn' : 'ok', text: msg })
    } else {
      setStatus({ cls: 'err', text: `Error: ${d.error}` })
    }
    onEditionUpdated(edition.slug)
  }

  const canSend = !draft && deploymentLive && hasSheetId && gmailConnected

  const showEditor = editorMode === 'write' || editorMode === 'split'
  const showPreview = editorMode === 'split' || editorMode === 'preview'

  return (
    <main className="main">
      <div className="toolbar">
        <span className={`toolbar-title${edition || editingFooter ? '' : ' empty'}`}>
          {editingFooter ? 'Footer' : edition ? edition.title : 'Select an edition'}
        </span>
        {edition && <>
          <button className={`btn btn-toggle${editorMode === 'write' ? ' active' : ''}`} onClick={() => setEditorMode('write')}>Write</button>
          <button className={`btn btn-toggle${editorMode === 'split' ? ' active' : ''}`} onClick={() => setEditorMode('split')}>Split</button>
          <button className={`btn btn-toggle${editorMode === 'preview' && viewMode === 'email' ? ' active' : ''}`} onClick={() => { setEditorMode('preview'); setViewMode('email') }}>Preview Email</button>
          <button className={`btn btn-toggle${editorMode === 'preview' && viewMode === 'web' ? ' active' : ''}`} onClick={() => { setEditorMode('preview'); setViewMode('web') }}>Preview Web</button>
        </>}
        <button className="btn btn-theme" onClick={onToggleFocus} title={focusMode ? 'Exit focus mode (Esc)' : 'Focus mode (F)'}>
          {focusMode ? '⊠' : '⛶'}
        </button>
        <button className="btn btn-theme" onClick={onToggleTheme} title="Toggle dark mode">
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>
      </div>

      {editingFooter ? (
        <div className="content-area">
          <div className="editor-pane">
            <EditorPanel key="footer" slug="footer" isFooter onSaved={() => {}} />
          </div>
        </div>
      ) : !edition ? (
        <div className="empty-state">← Select an edition to preview</div>
      ) : (
        <div className="content-area">
          <div
            className={`editor-pane${editorMode === 'split' ? ' bordered' : ''}`}
            style={{ display: showEditor ? undefined : 'none' }}
          >
            <EditorPanel key={edition.slug} slug={edition.slug} focusMode={focusMode} onSaved={() => setPreviewKey(k => k + 1)} />
          </div>
          {showPreview && (
            <div className={editorMode === 'split' ? 'split-preview' : 'full-preview'}>
              {editorMode === 'split' && (
                <div className="split-preview-bar">
                  <ViewToggle viewMode={viewMode} onViewModeChange={setViewMode} />
                  <button className="btn" style={{ marginLeft: 'auto' }} onClick={() => setPreviewKey(k => k + 1)}>↺ Refresh</button>
                </div>
              )}
              {editorMode === 'preview' && viewMode === 'email' && (
                <div className="split-preview-bar">
                  <a className="btn" href={`/preview/${edition.slug}/email.pdf`} download>⬇ Download PDF</a>
                </div>
              )}
              <PreviewFrame slug={edition.slug} viewMode={viewMode} previewKey={previewKey} />
            </div>
          )}
        </div>
      )}

      {edition && !focusMode && (
        <div className="action-bar">
          <div className="spacer" />
          {status && <span className={`status-msg ${status.cls}`}>{status.text}</span>}
          <button className="btn btn-draft-toggle" onClick={toggleDraft}>
            {draft ? 'Mark as Live' : 'Mark as Draft'}
          </button>
          <button className="btn" onClick={doPublish} disabled={draft}>Publish</button>
          <button className="btn" onClick={() => setShowTestSend(true)} disabled={!gmailConnected} title={!gmailConnected ? 'Connect Gmail in ⚙ Settings to enable sending' : undefined}>Test Send</button>
          <button className="btn btn-danger" onClick={() => setShowConfirm(true)} disabled={!canSend} title={!gmailConnected ? 'Connect Gmail in ⚙ Settings to enable sending' : !hasSheetId ? 'Add a contacts sheet ID in ⚙ Settings to enable sending' : undefined} >Send All</button>
        </div>
      )}

      {showTestSend && (
        <TestSendModal
          slug={edition.slug}
          onClose={() => setShowTestSend(false)}
          onSent={onTestSent}
        />
      )}
      {showConfirm && (
        <ConfirmModal
          title={edition.title}
          onClose={() => setShowConfirm(false)}
          onConfirm={() => {
            setShowConfirm(false)
            fetch(`/api/send/${edition.slug}`, { method: 'POST' })
              .then(r => r.json())
              .then(onSent)
          }}
        />
      )}
    </main>
  )
}
