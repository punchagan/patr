import React, { useState, useEffect } from "react";
import Modal from "./Modal";

export default function SentLogModal({ slug, onClose }) {
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`/api/edition/${slug}/sent-log`)
      .then((r) => r.json())
      .then((d) => {
        if (d.error) setError(d.error);
        else setEntries(d.entries ?? []);
      })
      .catch(() => setError("Could not load sent log"));
  }, [slug]);

  return (
    <Modal onClose={onClose} extraClass="sent-log-modal-overlay">
      <h3>Sent log</h3>
      {error && <p className="history-empty">{error}</p>}
      {!error && entries === null && <p className="history-empty">Loading…</p>}
      {!error && entries?.length === 0 && (
        <p className="history-empty">
          No sent log entries found for this edition.
        </p>
      )}
      {!error && entries?.length > 0 && (
        <table className="sent-log-table">
          <thead>
            <tr>
              <th>Email</th>
              <th>Sent at</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e, i) => (
              <tr key={i}>
                <td>{e.email}</td>
                <td>{e.sent_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>
          Close
        </button>
      </div>
    </Modal>
  );
}
