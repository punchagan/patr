import React, { useState, useEffect, useRef, useCallback } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { EditorView } from '@codemirror/view'
import { EditorSelection } from '@codemirror/state'
import '../editor.css'

async function uploadImage(file, slug) {
  const formData = new FormData()
  formData.append('file', file)
  const r = await fetch(`/api/edition/${slug}/upload-image`, { method: 'POST', body: formData })
  if (!r.ok) return null
  return (await r.json()).path
}

function wrapSelection(view, before, after = before) {
  const { state } = view
  const changes = []
  const newRanges = []
  for (const range of state.selection.ranges) {
    if (range.empty) {
      changes.push({ from: range.from, insert: before + after })
      newRanges.push(EditorSelection.cursor(range.from + before.length))
    } else {
      changes.push({ from: range.from, insert: before })
      changes.push({ from: range.to, insert: after })
      newRanges.push(EditorSelection.range(range.from + before.length, range.to + before.length))
    }
  }
  view.dispatch(state.update({ changes, selection: EditorSelection.create(newRanges) }))
  view.focus()
}

function prefixLine(view, prefix) {
  const { state } = view
  const line = state.doc.lineAt(state.selection.main.from)
  view.dispatch(state.update({ changes: { from: line.from, insert: prefix } }))
  view.focus()
}

function insertAtPos(view, text) {
  const { state } = view
  const pos = state.selection.main.head
  view.dispatch(state.update({
    changes: { from: pos, insert: text },
    selection: { anchor: pos + text.length },
  }))
  view.focus()
}

function ToolbarButton({ onClick, title, children }) {
  return (
    <button
      type="button"
      className="editor-toolbar-btn"
      title={title}
      onMouseDown={e => { e.preventDefault(); onClick() }}
    >
      {children}
    </button>
  )
}

function EditorToolbar({ viewRef, slug }) {
  const v = () => viewRef.current
  const wrap = (b, a = b) => v() && wrapSelection(v(), b, a)
  const prefix = (p) => v() && prefixLine(v(), p)

  const handleLink = () => {
    const url = prompt('URL:')
    if (url) wrap('[', `](${url})`)
  }

  const handleImageUpload = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.onchange = async () => {
      const file = input.files[0]
      if (!file) return
      const path = await uploadImage(file, slug)
      if (path && v()) insertAtPos(v(), `![](${path})`)
    }
    input.click()
  }

  return (
    <div className="editor-toolbar">
      <ToolbarButton onClick={() => wrap('**')} title="Bold">B</ToolbarButton>
      <ToolbarButton onClick={() => wrap('*')} title="Italic"><em>I</em></ToolbarButton>
      <ToolbarButton onClick={() => wrap('~~')} title="Strikethrough"><s>S</s></ToolbarButton>
      <span className="editor-toolbar-sep" />
      <ToolbarButton onClick={() => prefix('# ')} title="Heading 1">H1</ToolbarButton>
      <ToolbarButton onClick={() => prefix('## ')} title="Heading 2">H2</ToolbarButton>
      <ToolbarButton onClick={() => prefix('### ')} title="Heading 3">H3</ToolbarButton>
      <span className="editor-toolbar-sep" />
      <ToolbarButton onClick={() => prefix('- ')} title="Bullet list">• List</ToolbarButton>
      <ToolbarButton onClick={() => prefix('1. ')} title="Ordered list">1. List</ToolbarButton>
      <ToolbarButton onClick={() => prefix('> ')} title="Blockquote">❝</ToolbarButton>
      <span className="editor-toolbar-sep" />
      <ToolbarButton onClick={handleLink} title="Link">🔗</ToolbarButton>
      <ToolbarButton onClick={handleImageUpload} title="Insert image">🖼</ToolbarButton>
    </div>
  )
}

export default function EditorPanel({ slug, isFooter, focusMode, onTitleChange, onSaved }) {
  const [title, setTitle] = useState('')
  const [intro, setIntro] = useState('')
  const [initialBody, setInitialBody] = useState('')
  const [saveStatus, setSaveStatus] = useState('')
  const [isDark, setIsDark] = useState(() => document.body.classList.contains('dark'))

  const loading = useRef(false)
  const saveTimer = useRef(null)
  const commitTimer = useRef(null)
  const slugRef = useRef(slug)
  const titleRef = useRef(title)
  const introRef = useRef(intro)
  const bodyRef = useRef('')
  const viewRef = useRef(null)

  useEffect(() => { titleRef.current = title }, [title])
  useEffect(() => { introRef.current = intro }, [intro])

  // Track dark mode changes
  useEffect(() => {
    const obs = new MutationObserver(() => setIsDark(document.body.classList.contains('dark')))
    obs.observe(document.body, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])

  // Image paste/drop on the CodeMirror DOM
  useEffect(() => {
    const view = viewRef.current
    if (!view) return

    const onPaste = async (e) => {
      const files = [...(e.clipboardData?.files || [])].filter(f => f.type.startsWith('image/'))
      for (const file of files) {
        e.preventDefault()
        const path = await uploadImage(file, slugRef.current)
        if (path) insertAtPos(view, `![](${path})`)
      }
    }
    const onDrop = async (e) => {
      const files = [...(e.dataTransfer?.files || [])].filter(f => f.type.startsWith('image/'))
      if (!files.length) return
      e.preventDefault()
      for (const file of files) {
        const path = await uploadImage(file, slugRef.current)
        if (path) insertAtPos(view, `![](${path})`)
      }
    }

    view.dom.addEventListener('paste', onPaste)
    view.dom.addEventListener('drop', onDrop)
    return () => {
      view.dom.removeEventListener('paste', onPaste)
      view.dom.removeEventListener('drop', onDrop)
    }
  }, [viewRef.current]) // re-run when view is created

  // Load content when slug changes, flush pending save for previous slug
  useEffect(() => {
    if (!slug) return

    const prevSlug = slugRef.current
    slugRef.current = slug
    if (prevSlug && prevSlug !== slug && saveTimer.current !== null) {
      clearTimeout(saveTimer.current)
      saveTimer.current = null
      clearTimeout(commitTimer.current)
      commitTimer.current = null
      fetch(`/api/edition/${prevSlug}/content`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: titleRef.current, intro: introRef.current, body: bodyRef.current }),
      })
    }

    loading.current = true
    setSaveStatus('')
    fetch(`/api/edition/${slug}/content`)
      .then(r => r.json())
      .then(d => {
        setTitle(d.title || '')
        setIntro(d.intro || '')
        setInitialBody(d.body || '')
        bodyRef.current = d.body || ''
      })
      .finally(() => { loading.current = false })
  }, [slug])

  const scheduleCommit = useCallback(() => {
    clearTimeout(commitTimer.current)
    commitTimer.current = setTimeout(() => {
      fetch(`/api/edition/${slug}/commit`, { method: 'POST' })
    }, 5000)
  }, [slug])

  const scheduleSave = useCallback(() => {
    clearTimeout(saveTimer.current)
    scheduleCommit()
    saveTimer.current = setTimeout(() => {
      setSaveStatus('Saving…')
      fetch(`/api/edition/${slug}/content`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: titleRef.current, intro: introRef.current, body: bodyRef.current }),
      })
        .then(r => r.json())
        .then(d => {
          setSaveStatus(d.ok ? 'Saved' : `Error: ${d.error}`)
          if (d.ok) { setTimeout(() => setSaveStatus(''), 2000); onSaved?.() }
        })
        .catch(() => setSaveStatus('Save failed'))
    }, 1000)
  }, [slug, scheduleCommit])

  const handleBodyChange = useCallback((val) => {
    if (loading.current) return
    bodyRef.current = val
    scheduleSave()
  }, [scheduleSave])

  const handleTitleChange = (e) => {
    setTitle(e.target.value)
    titleRef.current = e.target.value
    onTitleChange?.(e.target.value)
    scheduleSave()
  }

  const handleIntroChange = (e) => {
    setIntro(e.target.value)
    introRef.current = e.target.value
    scheduleSave()
  }

  return (
    <div className="editor-panel">
      {!isFooter && !focusMode && <>
        <div className="editor-field">
          <label>Title</label>
          <input
            type="text"
            className="editor-title-input"
            value={title}
            onChange={handleTitleChange}
            autoComplete="off"
          />
        </div>
        <div className="editor-field">
          <label>Intro</label>
          <textarea
            className="editor-intro-input"
            rows={2}
            value={intro}
            onChange={handleIntroChange}
          />
        </div>
      </>}
      <div className="editor-field" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <label>Body</label>
        <EditorToolbar viewRef={viewRef} slug={slug} />
        <div className="editor-body-wrap">
          <CodeMirror
            value={initialBody}
            onChange={handleBodyChange}
            onCreateEditor={(view) => { viewRef.current = view }}
            extensions={[markdown(), EditorView.lineWrapping]}
            theme={isDark ? 'dark' : 'light'}
            placeholder="Write something…"
            basicSetup={{ lineNumbers: false, foldGutter: false, highlightActiveLine: false }}
            style={{ fontSize: 14, height: '100%' }}
          />
        </div>
      </div>
      <div className={`editor-save-status${saveStatus ? ' visible' : ''}`}>{saveStatus}</div>
    </div>
  )
}
