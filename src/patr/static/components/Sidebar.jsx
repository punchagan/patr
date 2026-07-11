import React, { useState, useRef, useCallback, useEffect } from "react";

const SIDEBAR_WIDTH_KEY = "patr-sidebar-width";
const MIN_WIDTH = 160;
const MAX_WIDTH = 500;

function EditionItem({ e, isSelected, onSelect, onEditionUpdated }) {
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDate, setEditDate] = useState("");
  const titleRef = useRef(null);
  const formRef = useRef(null);

  const startEdit = (ev) => {
    ev.stopPropagation();
    setEditTitle(e.title);
    setEditDate(e.date);
    setEditing(true);
  };

  useEffect(() => {
    if (editing) titleRef.current?.focus();
  }, [editing]);

  const save = () => {
    const patch = {};
    if (editTitle.trim() && editTitle.trim() !== e.title)
      patch.title = editTitle.trim();
    if (editDate && editDate !== e.date) patch.date = editDate;
    if (Object.keys(patch).length) {
      fetch(`/api/edition/${e.slug}/content`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }).then(() => onEditionUpdated(e.slug));
    }
    setEditing(false);
  };

  // Only save+close when focus leaves the entire form, not when moving between fields.
  const onBlur = (ev) => {
    if (formRef.current?.contains(ev.relatedTarget)) return;
    save();
  };

  const onKeyDown = (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      save();
    }
    if (ev.key === "Escape") setEditing(false);
  };

  if (editing) {
    return (
      <div
        className={`edition-item${isSelected ? " active" : ""}`}
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="edition-inline-edit" ref={formRef}>
          <input
            ref={titleRef}
            value={editTitle}
            onChange={(ev) => setEditTitle(ev.target.value)}
            onBlur={onBlur}
            onKeyDown={onKeyDown}
            placeholder="Title"
          />
          <input
            type="date"
            value={editDate}
            onChange={(ev) => setEditDate(ev.target.value)}
            onBlur={onBlur}
            onKeyDown={onKeyDown}
          />
        </div>
      </div>
    );
  }

  return (
    <div
      className={`edition-item${isSelected ? " active" : ""}`}
      onClick={() => onSelect(e)}
    >
      <div className="edition-title">{e.title}</div>
      <div className="edition-meta">
        <span>{e.date}</span>
        {!e.draft && <span className="badge badge-live">Published</span>}
        <button
          className="edition-edit-btn"
          onClick={startEdit}
          title="Edit title / date"
        >
          ✎
        </button>
      </div>
    </div>
  );
}

export default function Sidebar({
  editions,
  warnings,
  selectedSlug,
  editingFooter,
  hidden,
  updateAvailable,
  updateSafe,
  onSelect,
  onFooter,
  onNewEdition,
  onSettings,
  onHelp,
  onEditionUpdated,
}) {
  const [updateDismissed, setUpdateDismissed] = useState(false);
  const [applyingUpdate, setApplyingUpdate] = useState(false);
  const [applyUpdateError, setApplyUpdateError] = useState(null);
  const pollTimer = useRef(null);

  useEffect(() => {
    return () => clearInterval(pollTimer.current);
  }, []);

  const pollUntilBackUp = useCallback(() => {
    pollTimer.current = setInterval(() => {
      fetch("/api/editions")
        .then(() => {
          clearInterval(pollTimer.current);
          location.reload();
        })
        .catch(() => {
          // Server is still restarting — keep polling.
        });
    }, 1000);
  }, []);

  const handleUpdateNow = () => {
    if (!confirm("Make sure your work is saved. Update now?")) return;
    setApplyingUpdate(true);
    setApplyUpdateError(null);
    fetch("/api/apply-update", { method: "POST" })
      .then((r) => r.json())
      .then((d) => {
        if (d.ok) {
          pollUntilBackUp();
        } else {
          setApplyingUpdate(false);
          setApplyUpdateError(d.error || "Update failed");
        }
      })
      .catch(() => {
        // The server may have restarted mid-response — assume it worked.
        pollUntilBackUp();
      });
  };

  const [width, setWidth] = useState(() => {
    const stored = parseInt(localStorage.getItem(SIDEBAR_WIDTH_KEY), 10);
    return stored >= MIN_WIDTH && stored <= MAX_WIDTH ? stored : 260;
  });
  const dragging = useRef(false);

  const onMouseDown = useCallback((e) => {
    e.preventDefault();
    dragging.current = true;
    const onMouseMove = (e) => {
      if (!dragging.current) return;
      // sidebar is on the right; handle is on its left edge
      const newWidth = Math.min(
        MAX_WIDTH,
        Math.max(MIN_WIDTH, window.innerWidth - e.clientX),
      );
      setWidth(newWidth);
    };
    const onMouseUp = (e) => {
      dragging.current = false;
      const newWidth = Math.min(
        MAX_WIDTH,
        Math.max(MIN_WIDTH, window.innerWidth - e.clientX),
      );
      localStorage.setItem(SIDEBAR_WIDTH_KEY, newWidth);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }, []);

  const style = hidden ? { display: "none" } : { width, minWidth: width };

  return (
    <aside className="sidebar" style={style}>
      <div className="sidebar-resize-handle" onMouseDown={onMouseDown} />
      <div className="sidebar-header">
        Editions
        <span style={{ float: "right", display: "flex", gap: 4 }}>
          <button
            className="btn"
            onClick={onNewEdition}
            style={{ fontSize: 11, padding: "2px 7px" }}
          >
            +
          </button>
          <button
            className="btn"
            onClick={onSettings}
            style={{ fontSize: 11, padding: "2px 7px" }}
          >
            ⚙
          </button>
          <button
            className="btn"
            onClick={onHelp}
            style={{ fontSize: 11, padding: "2px 7px" }}
          >
            ?
          </button>
        </span>
      </div>
      {updateAvailable && !updateDismissed && (
        <div className="update-banner">
          <span>
            {applyUpdateError ? (
              `Update failed: ${applyUpdateError}`
            ) : updateSafe ? (
              "A newer version of Patr is available."
            ) : (
              <>
                A newer version of Patr is available. To update: stop patr, then
                run <code>git pull --ff-only && uv sync</code> before
                restarting.
              </>
            )}
          </span>
          {updateSafe && (
            <button
              className="btn"
              onClick={handleUpdateNow}
              disabled={applyingUpdate}
              style={{ fontSize: 11, padding: "2px 7px" }}
            >
              {applyingUpdate ? "Updating…" : "Update now"}
            </button>
          )}
          <button
            className="update-banner-dismiss"
            aria-label="Dismiss"
            onClick={() => setUpdateDismissed(true)}
          >
            ×
          </button>
        </div>
      )}
      <div className="edition-list">
        {warnings?.map((w, i) => (
          <div
            key={i}
            style={{
              padding: "10px 14px",
              fontSize: 12,
              color: "var(--text-secondary)",
              background: "var(--warning-bg, #fffbe6)",
              borderBottom: "1px solid var(--border)",
            }}
          >
            ⚠ {w}
          </div>
        ))}
        {editions.length === 0 && !warnings?.length ? (
          <div
            style={{
              padding: 16,
              color: "var(--text-placeholder)",
              fontSize: 13,
            }}
          >
            Loading…
          </div>
        ) : editions.length === 0 ? null : (
          editions.map((e) => (
            <EditionItem
              key={e.slug}
              e={e}
              isSelected={e.slug === selectedSlug}
              onSelect={onSelect}
              onEditionUpdated={onEditionUpdated}
            />
          ))
        )}
      </div>
      <div
        className={`edition-item footer-item${editingFooter ? " active" : ""}`}
        onClick={onFooter}
      >
        Footer
      </div>
    </aside>
  );
}
