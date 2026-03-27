import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Link from '@tiptap/extension-link'
import Placeholder from '@tiptap/extension-placeholder'
import { Markdown } from 'tiptap-markdown'
import '../editor.css'

function absolutifyImages(markdown, slug) {
  return markdown.replace(/!\[([^\]]*)\]\((?!https?:\/\/|\/)(.*?)\)/g, `![$1](/newsletter/${slug}/$2)`)
}

function relativifyImages(markdown, slug) {
  const prefix = `/newsletter/${slug}/`
  const escaped = prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return markdown.replace(new RegExp(`!\\[([^\\]]*)\\]\\(${escaped}(.*?)\\)`, 'g'), '![$1]($2)')
}

async function uploadImage(file, slug) {
  const formData = new FormData()
  formData.append('file', file)
  const r = await fetch(`/api/edition/${slug}/upload-image`, { method: 'POST', body: formData })
  if (!r.ok) return null
  return (await r.json()).path
}

function ToolbarButton({ onClick, active, title, children }) {
  return (
    <button
      type="button"
      className={`editor-toolbar-btn${active ? ' active' : ''}`}
      title={title}
      onMouseDown={e => { e.preventDefault(); onClick() }}
    >
      {children}
    </button>
  )
}

function EditorToolbar({ editor, slug }) {
  if (!editor) return null

  const triggerImageUpload = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.onchange = async () => {
      const file = input.files[0]
      if (!file) return
      const path = await uploadImage(file, slug)
      if (path) editor.chain().focus().setImage({ src: `/newsletter/${slug}/${path}` }).run()
    }
    input.click()
  }

  const setLink = () => {
    const url = prompt('URL:')
    if (url) editor.chain().focus().setLink({ href: url }).run()
    else if (url === '') editor.chain().focus().unsetLink().run()
  }

  return (
    <div className="editor-toolbar">
      <ToolbarButton onClick={() => editor.chain().focus().toggleBold().run()} active={editor.isActive('bold')} title="Bold">B</ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().toggleItalic().run()} active={editor.isActive('italic')} title="Italic"><em>I</em></ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().toggleStrike().run()} active={editor.isActive('strike')} title="Strikethrough"><s>S</s></ToolbarButton>
      <span className="editor-toolbar-sep" />
      <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} active={editor.isActive('heading', { level: 1 })} title="Heading 1">H1</ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} active={editor.isActive('heading', { level: 2 })} title="Heading 2">H2</ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()} active={editor.isActive('heading', { level: 3 })} title="Heading 3">H3</ToolbarButton>
      <span className="editor-toolbar-sep" />
      <ToolbarButton onClick={() => editor.chain().focus().toggleBulletList().run()} active={editor.isActive('bulletList')} title="Bullet list">• List</ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().toggleOrderedList().run()} active={editor.isActive('orderedList')} title="Ordered list">1. List</ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().toggleBlockquote().run()} active={editor.isActive('blockquote')} title="Blockquote">❝</ToolbarButton>
      <span className="editor-toolbar-sep" />
      <ToolbarButton onClick={setLink} active={editor.isActive('link')} title="Link">🔗</ToolbarButton>
      <ToolbarButton onClick={triggerImageUpload} title="Insert image">🖼</ToolbarButton>
    </div>
  )
}

export default function EditorPanel({ slug, onTitleChange, onSaved }) {
  const [title, setTitle] = useState('')
  const [intro, setIntro] = useState('')
  const [saveStatus, setSaveStatus] = useState('')
  const loading = useRef(false)
  const saveTimer = useRef(null)

  // Use refs to avoid stale closures in debounced save
  const titleRef = useRef(title)
  const introRef = useRef(intro)
  useEffect(() => { titleRef.current = title }, [title])
  useEffect(() => { introRef.current = intro }, [intro])

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit,
      Markdown,
      Image,
      Link.configure({ openOnClick: false }),
      Placeholder.configure({ placeholder: 'Write something…' }),
    ],
    onUpdate: () => { if (!loading.current) scheduleSave() },
  })

  // Image paste/drop
  useEffect(() => {
    if (!editor || !editor.view?.dom) return
    const el = editor.view.dom

    const onPaste = async (e) => {
      const files = [...(e.clipboardData?.files || [])].filter(f => f.type.startsWith('image/'))
      for (const file of files) {
        e.preventDefault()
        const path = await uploadImage(file, slug)
        if (path) editor.chain().focus().setImage({ src: `/newsletter/${slug}/${path}` }).run()
      }
    }
    const onDrop = async (e) => {
      const files = [...(e.dataTransfer?.files || [])].filter(f => f.type.startsWith('image/'))
      if (!files.length) return
      e.preventDefault()
      for (const file of files) {
        const path = await uploadImage(file, slug)
        if (path) editor.chain().focus().setImage({ src: `/newsletter/${slug}/${path}` }).run()
      }
    }

    el.addEventListener('paste', onPaste)
    el.addEventListener('drop', onDrop)
    return () => { el.removeEventListener('paste', onPaste); el.removeEventListener('drop', onDrop) }
  }, [editor, slug])

  // Load content when slug changes
  useEffect(() => {
    if (!editor || !slug) return
    loading.current = true
    setSaveStatus('')
    fetch(`/api/edition/${slug}/content`)
      .then(r => r.json())
      .then(d => {
        setTitle(d.title || '')
        setIntro(d.intro || '')
        editor.commands.setContent(absolutifyImages(d.body || '', slug))
      })
      .finally(() => { loading.current = false })
  }, [slug, editor])

  const scheduleSave = useCallback(() => {
    clearTimeout(saveTimer.current)
    setSaveStatus('Saving…')
    saveTimer.current = setTimeout(() => {
      if (!editor) return
      const body = relativifyImages(editor.storage.markdown.getMarkdown(), slug)
      fetch(`/api/edition/${slug}/content`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: titleRef.current, intro: introRef.current, body }),
      })
        .then(r => r.json())
        .then(d => {
          setSaveStatus(d.ok ? 'Saved' : `Error: ${d.error}`)
          if (d.ok) { setTimeout(() => setSaveStatus(''), 2000); onSaved?.() }
        })
        .catch(() => setSaveStatus('Save failed'))
    }, 1000)
  }, [editor, slug])

  const handleTitleChange = (e) => {
    setTitle(e.target.value)
    onTitleChange?.(e.target.value)
    scheduleSave()
  }

  return (
    <div className="editor-panel">
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
          onChange={e => { setIntro(e.target.value); scheduleSave() }}
        />
      </div>
      <div className="editor-field" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <label>Body</label>
        <EditorToolbar editor={editor} slug={slug} />
        <div className="editor-body-wrap" onClick={() => editor?.commands.focus()}>
          <EditorContent editor={editor} />
        </div>
      </div>
      <div className={`editor-save-status${saveStatus ? ' visible' : ''}`}>{saveStatus}</div>
    </div>
  )
}
