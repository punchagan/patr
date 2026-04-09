import React, { useState, useEffect } from "react";
import Modal from "./Modal";

export default function TestSendModal({ slug, onClose, onSent }) {
  const [contacts, setContacts] = useState(null);
  const [error, setError] = useState(null);
  const [checked, setChecked] = useState({ __self__: true });
  const [sending, setSending] = useState(false);
  const [emailOnly, setEmailOnly] = useState(false);
  const [senderEmail, setSenderEmail] = useState(null);

  useEffect(() => {
    fetch("/api/contacts")
      .then((r) => r.json())
      .then((d) => {
        if (d.error) {
          setError(d.error);
          return;
        }
        setContacts(d.contacts);
      });
    fetch("/api/settings")
      .then((r) => r.json())
      .then((d) => setEmailOnly(!!d.email_only));
    fetch("/api/auth-status")
      .then((r) => r.json())
      .then((d) => setSenderEmail(d.sender_email || null));
  }, []);

  const toggle = (key) =>
    setChecked((prev) => ({ ...prev, [key]: !prev[key] }));

  const selectedCount = Object.values(checked).filter(Boolean).length;

  const send = () => {
    const recipients = [];
    if (checked.__self__) recipients.push({ name: "You", email: "__self__" });
    contacts?.forEach((c) => {
      if (checked[c.email]) recipients.push({ name: c.name, email: c.email });
    });
    setSending(true);
    fetch(`/api/test-send/${slug}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recipients }),
    })
      .then((r) => r.json())
      .then((d) => {
        onClose();
        onSent(d);
      });
  };

  return (
    <Modal onClose={onClose}>
      <h3>Test Send</h3>
      {!emailOnly && (
        <div className="info-box" style={{ marginBottom: 12 }}>
          Images in the email point to your live site. They won't display unless
          the edition has been published.
        </div>
      )}
      <p
        style={{
          marginBottom: 10,
          fontSize: 13,
          color: "var(--text-secondary)",
        }}
      >
        Select recipients:{" "}
        <strong style={{ color: "var(--text-primary)" }}>
          ({selectedCount} selected)
        </strong>
      </p>
      <div
        style={{
          maxHeight: 260,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 6,
          marginBottom: 16,
          fontSize: 13,
        }}
      >
        {error ? (
          <span style={{ color: "#f08080" }}>{error}</span>
        ) : contacts === null ? (
          <span style={{ color: "var(--text-secondary)" }}>Loading…</span>
        ) : (
          <>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={!!checked.__self__}
                onChange={() => toggle("__self__")}
              />
              <span>
                Myself
                {senderEmail && (
                  <span
                    style={{ color: "var(--text-secondary)", fontSize: 11 }}
                  >
                    {" "}
                    &lt;{senderEmail}&gt;
                  </span>
                )}
              </span>
            </label>
            {contacts.map((c) => (
              <label
                key={c.email}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={!!checked[c.email]}
                  onChange={() => toggle(c.email)}
                />
                <span>
                  {c.name || c.email}
                  {c.name && (
                    <span
                      style={{ color: "var(--text-secondary)", fontSize: 11 }}
                    >
                      {" "}
                      &lt;{c.email}&gt;
                    </span>
                  )}
                </span>
              </label>
            ))}
          </>
        )}
      </div>
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>
          Cancel
        </button>
        <button
          className="btn btn-primary"
          onClick={send}
          disabled={sending || selectedCount === 0}
        >
          {sending ? "Sending…" : "Send"}
        </button>
      </div>
    </Modal>
  );
}
