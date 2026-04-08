import React, { useState, useEffect, useRef } from "react";
import TestSendModal from "./modals/TestSendModal";
import ConfirmModal from "./modals/ConfirmModal";
import HistoryModal from "./modals/HistoryModal";
import DeleteEditionModal from "./modals/DeleteEditionModal";
import EditorPanel from "./EditorPanel";

function useDeployStatus(edition) {
  const [deploymentLive, setDeploymentLive] = useState(false);
  const [emailOnly, setEmailOnly] = useState(false);
  const [gitAvailable, setGitAvailable] = useState(true);
  const [status, setStatus] = useState(null);

  useEffect(() => {
    if (!edition) {
      setStatus(null);
      setDeploymentLive(false);
      setEmailOnly(false);
      return;
    }
    setStatus({ cls: "info", text: "Checking…" });
    fetch(`/api/check-deployment/${edition.slug}`)
      .then((r) => r.json())
      .then((d) => {
        if (d.email_only) {
          setEmailOnly(true);
          setDeploymentLive(false);
          setGitAvailable(d.git_available ?? true);
          setStatus(null);
        } else {
          setEmailOnly(false);
          setDeploymentLive(d.live);
          setGitAvailable(d.git_available ?? true);
          if (d.live) setStatus({ cls: "ok", text: "Published ✓" });
          else
            setStatus({
              cls: "warn",
              text: d.reason ? `Not published: ${d.reason}` : "Not published yet",
            });
        }
      });
  }, [edition?.slug]);

  return {
    deploymentLive,
    emailOnly,
    gitAvailable,
    status,
    setStatus,
    setDeploymentLive,
  };
}

function PreviewFrame({ slug, viewMode, previewKey }) {
  return (
    <iframe
      key={`${slug}-${viewMode}-${previewKey}`}
      className="preview-frame"
      src={`/preview/${slug}/${viewMode}`}
    />
  );
}

function PdfDownloadButton({ slug }) {
  const [state, setState] = useState("idle"); // 'idle' | 'loading' | 'error'

  const download = () => {
    setState("loading");
    fetch(`/preview/${slug}/email.pdf`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.blob();
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${slug}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
        setState("idle");
      })
      .catch(() => setState("error"));
  };

  if (state === "loading")
    return (
      <span className="btn" style={{ opacity: 0.6, cursor: "default" }}>
        Generating PDF…
      </span>
    );
  if (state === "error")
    return (
      <button className="btn btn-danger" onClick={() => setState("idle")}>
        PDF failed — retry?
      </button>
    );
  return (
    <button className="btn" onClick={download}>
      ⬇ Download PDF
    </button>
  );
}

function ViewToggle({ viewMode, onViewModeChange }) {
  return (
    <>
      <button
        className={`btn btn-toggle${viewMode === "email" ? " active" : ""}`}
        onClick={() => onViewModeChange("email")}
      >
        Email
      </button>
      <button
        className={`btn btn-toggle${viewMode === "web" ? " active" : ""}`}
        onClick={() => onViewModeChange("web")}
      >
        Web
      </button>
    </>
  );
}

function OverflowMenu({ onHistory, onDelete }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div className="overflow-menu" ref={ref}>
      <button className="btn" onClick={() => setOpen((o) => !o)} title="More actions">
        ⋯
      </button>
      {open && (
        <div className="overflow-dropdown">
          <button
            className="btn overflow-item"
            onClick={() => { setOpen(false); onHistory(); }}
          >
            History
          </button>
          <button
            className="btn btn-danger overflow-item"
            onClick={() => { setOpen(false); onDelete(); }}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

export default function MainPanel({
  edition,
  editingFooter,
  theme,
  hasSheetId,
  gmailConnected,
  focusMode,
  onToggleFocus,
  onToggleTheme,
  onEditionUpdated,
  onEditionDeleted,
  initialEditorMode = "write",
  initialViewMode = "email",
}) {
  const [draft, setDraft] = useState(edition?.draft ?? true);
  const [editorMode, setEditorMode] = useState(initialEditorMode);
  const [viewMode, setViewMode] = useState(initialViewMode);
  const [previewKey, setPreviewKey] = useState(0);
  const [showTestSend, setShowTestSend] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const {
    deploymentLive,
    emailOnly,
    gitAvailable,
    status,
    setStatus,
    setDeploymentLive,
  } = useDeployStatus(edition);
  const isInitialLoad = useRef(true);
  const editorRef = useRef(null);

  useEffect(() => {
    setDraft(edition?.draft ?? true);
    if (isInitialLoad.current && edition) {
      isInitialLoad.current = false;
      setEditorMode(initialEditorMode);
      setViewMode(initialViewMode);
    } else if (!isInitialLoad.current) {
      setEditorMode("write");
      setViewMode("email");
    }
  }, [edition?.slug]);

  useEffect(() => {
    if (!edition) return;
    const suffix =
      editorMode === "split"
        ? "/split"
        : editorMode === "preview"
        ? `/${viewMode}`
        : "";
    history.replaceState(null, "", `#${edition.slug}${suffix}`);
  }, [edition?.slug, editorMode, viewMode]);

  const doPublish = () => {
    setStatus({ cls: "info", text: "Publishing…" });
    fetch(`/api/publish/${edition.slug}`, { method: "POST" })
      .then((r) => r.json())
      .then((d) => {
        if (d.ok) {
          setDraft(false);
          setStatus({ cls: "ok", text: "Published ✓" });
          setDeploymentLive(true);
          onEditionUpdated(edition.slug);
        } else setStatus({ cls: "err", text: `Publish failed: ${d.error}` });
      });
  };

  const doUnpublish = () => {
    setStatus({ cls: "info", text: "Unpublishing…" });
    fetch(`/api/unpublish/${edition.slug}`, { method: "POST" })
      .then((r) => r.json())
      .then((d) => {
        if (d.ok) {
          setDraft(true);
          setStatus({ cls: "ok", text: "Unpublished ✓" });
          setDeploymentLive(false);
          onEditionUpdated(edition.slug);
        } else setStatus({ cls: "err", text: `Unpublish failed: ${d.error}` });
      });
  };

  const onTestSent = (d) => {
    if (d.ok)
      setStatus({
        cls: "ok",
        text: `Test sent to ${d.sent} recipient${d.sent !== 1 ? "s" : ""} ✓`,
      });
    else setStatus({ cls: "err", text: `Error: ${d.error}` });
  };

  const onSent = (d) => {
    if (d.ok) {
      let msg = `Sent to ${d.sent} recipient${d.sent !== 1 ? "s" : ""} ✓`;
      if (d.skipped) msg += `, ${d.skipped} already sent`;
      if (d.failed?.length) msg += `, ${d.failed.length} failed`;
      setStatus({ cls: d.failed?.length ? "warn" : "ok", text: msg });
    } else {
      setStatus({ cls: "err", text: `Error: ${d.error}` });
    }
    onEditionUpdated(edition.slug);
  };

  const canSend =
    (emailOnly || deploymentLive) && hasSheetId && gmailConnected;

  const showEditor = editorMode === "write" || editorMode === "split";
  const showPreview = editorMode === "split" || editorMode === "preview";

  return (
    <main className="main">
      <div className="toolbar">
        <span
          className={`toolbar-title${edition || editingFooter ? "" : " empty"}`}
        >
          {editingFooter
            ? "Footer"
            : edition
            ? edition.title
            : "Select an edition"}
        </span>
        {edition && (
          <>
            <button
              className={`btn btn-toggle${
                editorMode === "write" ? " active" : ""
              }`}
              onClick={() => setEditorMode("write")}
            >
              Write
            </button>
            <button
              className={`btn btn-toggle${
                editorMode === "split" ? " active" : ""
              }`}
              onClick={() => setEditorMode("split")}
            >
              Split
            </button>
            <button
              className={`btn btn-toggle${
                editorMode === "preview" && viewMode === "email"
                  ? " active"
                  : ""
              }`}
              onClick={() => {
                setEditorMode("preview");
                setViewMode("email");
              }}
            >
              Preview Email
            </button>
            {!emailOnly && (
              <button
                className={`btn btn-toggle${
                  editorMode === "preview" && viewMode === "web"
                    ? " active"
                    : ""
                }`}
                onClick={() => {
                  setEditorMode("preview");
                  setViewMode("web");
                }}
              >
                Preview Web
              </button>
            )}
          </>
        )}
        <button
          className="btn btn-theme"
          onClick={onToggleFocus}
          title={focusMode ? "Exit focus mode (Esc)" : "Focus mode (F)"}
        >
          {focusMode ? "⊠" : "⛶"}
        </button>
        <button
          className="btn btn-theme"
          onClick={onToggleTheme}
          title="Toggle dark mode"
        >
          {theme === "dark" ? "☀️" : "🌙"}
        </button>
      </div>

      {editingFooter ? (
        <div className="content-area">
          <div className="editor-pane">
            <EditorPanel
              key="footer"
              slug="footer"
              isFooter
              onSaved={() => {}}
            />
          </div>
        </div>
      ) : !edition ? (
        <div className="empty-state">← Select an edition to preview</div>
      ) : (
        <div className="content-area">
          <div
            className={`editor-pane${
              editorMode === "split" ? " bordered" : ""
            }`}
            style={{ display: showEditor ? undefined : "none" }}
          >
            <EditorPanel
              ref={editorRef}
              key={edition.slug}
              slug={edition.slug}
              focusMode={focusMode}
              onSaved={() => setPreviewKey((k) => k + 1)}
            />
          </div>
          {showPreview && (
            <div
              className={
                editorMode === "split" ? "split-preview" : "full-preview"
              }
            >
              {editorMode === "split" && (
                <div className="split-preview-bar">
                  {!emailOnly && (
                    <ViewToggle
                      viewMode={viewMode}
                      onViewModeChange={setViewMode}
                    />
                  )}
                  <button
                    className="btn"
                    style={{ marginLeft: "auto" }}
                    onClick={() => setPreviewKey((k) => k + 1)}
                  >
                    ↺ Refresh
                  </button>
                </div>
              )}
              {editorMode === "preview" && viewMode === "email" && (
                <div className="split-preview-bar">
                  <PdfDownloadButton slug={edition.slug} />
                </div>
              )}
              <PreviewFrame
                slug={edition.slug}
                viewMode={viewMode}
                previewKey={previewKey}
              />
            </div>
          )}
        </div>
      )}

      {edition && !focusMode && (
        <div className="action-bar">
          <div className="spacer" />
          {status && (
            <span className={`status-msg ${status.cls}`}>{status.text}</span>
          )}
          {!emailOnly && gitAvailable && (
            draft ? (
              <button className="btn" onClick={doPublish}>Publish</button>
            ) : (
              <button className="btn" onClick={doUnpublish}>Unpublish</button>
            )
          )}
          <button
            className="btn"
            onClick={() => setShowTestSend(true)}
            disabled={!gmailConnected}
            title={
              !gmailConnected
                ? "Connect Gmail in ⚙ Settings to enable sending"
                : undefined
            }
          >
            Test Send
          </button>
          <button
            className="btn btn-danger"
            onClick={() => setShowConfirm(true)}
            disabled={!canSend}
            title={
              !gmailConnected
                ? "Connect Gmail in ⚙ Settings to enable sending"
                : !hasSheetId
                ? "Add a contacts sheet ID in ⚙ Settings to enable sending"
                : undefined
            }
          >
            Send All
          </button>
          <OverflowMenu
            onHistory={() => setShowHistory(true)}
            onDelete={() => setShowDelete(true)}
          />
        </div>
      )}

      {showDelete && (
        <DeleteEditionModal
          title={edition.title}
          onClose={() => setShowDelete(false)}
          onConfirm={() => {
            fetch(`/api/edition/${edition.slug}`, { method: "DELETE" })
              .then((r) => r.json())
              .then((d) => {
                setShowDelete(false);
                if (d.ok) onEditionDeleted?.();
              });
          }}
        />
      )}
      {showHistory && (
        <HistoryModal
          slug={edition.slug}
          currentContent={editorRef.current?.getBody() ?? ""}
          onRestore={(content) => editorRef.current?.restoreBody(content)}
          onClose={() => setShowHistory(false)}
        />
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
          slug={edition.slug}
          title={edition.title}
          onClose={() => setShowConfirm(false)}
          onConfirm={() => {
            setShowConfirm(false);
            setStatus({ cls: "ok", text: "Sending…" });
            fetch(`/api/send/${edition.slug}`, { method: "POST" }).then(
              async (r) => {
                if (!r.ok) {
                  onSent(await r.json());
                  return;
                }
                const reader = r.body.getReader();
                const decoder = new TextDecoder();
                let buffer = "";
                const read = async () => {
                  const { done, value } = await reader.read();
                  if (done) return;
                  buffer += decoder.decode(value, { stream: true });
                  const parts = buffer.split("\n\n");
                  buffer = parts.pop();
                  for (const part of parts) {
                    if (!part.startsWith("data: ")) continue;
                    const event = JSON.parse(part.slice(6));
                    if (event.type === "progress")
                      setStatus({
                        cls: "ok",
                        text: `Sending… ${event.sent} / ${event.total}`,
                      });
                    else if (event.type === "done")
                      onSent({
                        ok: true,
                        sent: event.sent,
                        failed: event.failed,
                        skipped: event.skipped,
                      });
                  }
                  return read();
                };
                return read();
              },
            );
          }}
        />
      )}
    </main>
  );
}
