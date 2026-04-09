import React, { useState, useEffect } from "react";

export default function HelpModal({ onClose }) {
  const [html, setHtml] = useState("");

  useEffect(() => {
    fetch("/api/help")
      .then((r) => r.json())
      .then((d) => setHtml(d.html));
  }, []);

  return (
    <div
      className="modal-overlay visible"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal help-modal">
        <div className="help-modal-header">
          <h3>Help</h3>
          <button className="btn" onClick={onClose}>
            ✕
          </button>
        </div>
        <div
          className="help-modal-body"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </div>
    </div>
  );
}
