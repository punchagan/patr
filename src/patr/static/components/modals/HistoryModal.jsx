import React, { useState, useEffect } from "react";
import SideBySideDiff from "./SideBySideDiff";

export default function HistoryModal({
  slug,
  currentContent,
  onRestore,
  onClose,
}) {
  const [versions, setVersions] = useState(null);
  const [selected, setSelected] = useState(null);
  const [versionContent, setVersionContent] = useState(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [confirmRestore, setConfirmRestore] = useState(false);

  useEffect(() => {
    fetch(`/api/edition/${slug}/versions`)
      .then((r) => r.json())
      .then((d) => setVersions(d.versions ?? []));
  }, [slug]);

  const selectVersion = (v) => {
    if (selected?.id === v.id) return;
    setSelected(v);
    setVersionContent(null);
    setConfirmRestore(false);
    setLoadingContent(true);
    fetch(`/api/edition/${slug}/versions/${v.id}`)
      .then((r) => r.json())
      .then((d) => {
        setVersionContent(d.content ?? "");
        setLoadingContent(false);
      })
      .catch(() => setLoadingContent(false));
  };

  const doRestore = () => {
    onRestore(versionContent);
    onClose();
  };

  return (
    <div
      className="modal-overlay visible history-modal-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal modal-history">
        <h3>Version history</h3>
        <div className="history-layout">
          <div className="history-list">
            {versions === null && <p className="history-empty">Loading…</p>}
            {versions?.length === 0 && (
              <p className="history-empty">No saved versions yet.</p>
            )}
            {versions?.map((v) => (
              <button
                key={v.id}
                className={`history-item${
                  selected?.id === v.id ? " active" : ""
                }`}
                onClick={() => selectVersion(v)}
              >
                {v.label}
              </button>
            ))}
          </div>
          <div className="history-diff">
            {!selected && (
              <p className="history-empty">Select a version to compare.</p>
            )}
            {selected && loadingContent && (
              <p className="history-empty">Loading…</p>
            )}
            {selected && !loadingContent && versionContent !== null && (
              <SideBySideDiff mine={currentContent} theirs={versionContent} />
            )}
          </div>
        </div>
        {confirmRestore ? (
          <div className="modal-actions">
            <span
              style={{ marginRight: "auto", color: "var(--text-secondary)" }}
            >
              Restore this version? Your current content will be overwritten.
            </span>
            <button className="btn" onClick={() => setConfirmRestore(false)}>
              Cancel
            </button>
            <button className="btn btn-primary" onClick={doRestore}>
              Restore
            </button>
          </div>
        ) : (
          <div className="modal-actions">
            <button className="btn" onClick={onClose}>
              Close
            </button>
            <button
              className="btn btn-primary"
              onClick={() => setConfirmRestore(true)}
              disabled={!versionContent}
            >
              Restore this version
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
