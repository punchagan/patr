import React, { useState, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import MainPanel from "./components/MainPanel";
import SettingsModal from "./components/modals/SettingsModal";
import NewEditionModal from "./components/modals/NewEditionModal";
import HelpModal from "./components/modals/HelpModal";

function DuplicateTabWarning() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        gap: "1rem",
        fontFamily: "sans-serif",
        color: "var(--text, #333)",
      }}
    >
      <h2 style={{ margin: 0 }}>Patr is already open</h2>
      <p style={{ margin: 0, color: "var(--text-secondary, #666)" }}>
        Please switch to the existing tab to avoid conflicts.
      </p>
    </div>
  );
}

export default function App() {
  const [isDuplicateTab, setIsDuplicateTab] = useState(false);

  useEffect(() => {
    if (!navigator.locks) return;
    navigator.locks.request(
      "patr_single_instance",
      { ifAvailable: true },
      async (lock) => {
        if (!lock) {
          setIsDuplicateTab(true);
          return;
        }
        // Hold the lock for the lifetime of this tab.
        await new Promise(() => {});
      },
    );
  }, []);

  const [editions, setEditions] = useState([]);
  const [editionWarnings, setEditionWarnings] = useState([]);
  const [selectedEdition, setSelectedEdition] = useState(null);
  const [theme, setTheme] = useState(
    () => localStorage.getItem("theme") || "light",
  );
  const [hasSheetId, setHasSheetId] = useState(false);
  const [gmailConnected, setGmailConnected] = useState(false);
  const [editingFooter, setEditingFooter] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showNewEdition, setShowNewEdition] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [focusMode, setFocusMode] = useState(false);

  useEffect(() => {
    document.body.classList.toggle("dark", theme === "dark");
  }, [theme]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") setFocusMode(false);
      if (
        e.key === "f" &&
        !e.ctrlKey &&
        !e.metaKey &&
        e.target.tagName !== "INPUT" &&
        e.target.tagName !== "TEXTAREA" &&
        !e.target.isContentEditable
      )
        setFocusMode((f) => !f);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const loadEditions = (selectSlug) => {
    return fetch("/api/editions")
      .then((r) => r.json())
      .then(({ editions: list, warnings }) => {
        setEditions(list);
        setEditionWarnings(warnings || []);
        if (selectSlug) {
          const match = list.find((e) => e.slug === selectSlug);
          if (match) setSelectedEdition(match);
        }
        return list;
      });
  };

  const [initialEditorMode] = useState(() => {
    const mode = location.hash.slice(1).split("/")[1] || "";
    return mode === "split"
      ? "split"
      : mode === "email" || mode === "web"
      ? "preview"
      : "write";
  });
  const [initialViewMode] = useState(() => {
    const mode = location.hash.slice(1).split("/")[1] || "";
    return mode === "web" ? "web" : "email";
  });

  useEffect(() => {
    fetch("/api/settings")
      .then((r) => r.json())
      .then((d) => setHasSheetId(!!d.has_sheet_id));
    fetch("/api/auth-status")
      .then((r) => r.json())
      .then((d) => setGmailConnected(!!d.connected));
    if (document.body.dataset.unconfigured) setShowSettings(true);

    const hashSlug = location.hash.slice(1).split("/")[0];
    loadEditions().then((list) => {
      if (hashSlug) {
        const match = list.find((e) => e.slug === hashSlug);
        if (match) setSelectedEdition(match);
      }
    });
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("theme", next);
  };

  const onEditionUpdated = (slug) => {
    loadEditions(slug).then((list) => {
      const updated = list.find(
        (e) => e.slug === (slug || selectedEdition?.slug),
      );
      if (updated) setSelectedEdition(updated);
    });
  };

  if (isDuplicateTab) return <DuplicateTabWarning />;

  return (
    <div className="layout">
      <Sidebar
        editions={editions}
        warnings={editionWarnings}
        selectedSlug={editingFooter ? null : selectedEdition?.slug}
        editingFooter={editingFooter}
        hidden={focusMode}
        onSelect={(e) => {
          setSelectedEdition(e);
          setEditingFooter(false);
        }}
        onFooter={() => {
          setSelectedEdition(null);
          setEditingFooter(true);
        }}
        onNewEdition={() => setShowNewEdition(true)}
        onSettings={() => setShowSettings(true)}
        onHelp={() => setShowHelp(true)}
        onEditionUpdated={onEditionUpdated}
      />
      <MainPanel
        edition={selectedEdition}
        editingFooter={editingFooter}
        theme={theme}
        hasSheetId={hasSheetId}
        gmailConnected={gmailConnected}
        focusMode={focusMode}
        onToggleFocus={() => setFocusMode((f) => !f)}
        onToggleTheme={toggleTheme}
        initialEditorMode={initialEditorMode}
        initialViewMode={initialViewMode}
        onEditionUpdated={onEditionUpdated}
        onEditionDeleted={() => {
          setSelectedEdition(null);
          loadEditions();
        }}
      />
      {showSettings && (
        <SettingsModal
          unconfigured={!!document.body.dataset.unconfigured}
          gmailConnected={gmailConnected}
          onGmailConnected={setGmailConnected}
          onClose={() => setShowSettings(false)}
        />
      )}
      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
      {showNewEdition && (
        <NewEditionModal
          onClose={() => setShowNewEdition(false)}
          onCreate={(slug) => {
            setShowNewEdition(false);
            loadEditions(slug);
          }}
        />
      )}
    </div>
  );
}
