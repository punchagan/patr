import React, { useState, useEffect } from "react";
import Modal from "./Modal";

export default function ConfirmModal({ slug, title, onClose, onConfirm }) {
  const [count, setCount] = useState(null);
  const [missingImages, setMissingImages] = useState(null);
  const [deployment, setDeployment] = useState(null);

  useEffect(() => {
    fetch("/api/contacts/count")
      .then((r) => r.json())
      .then((d) => {
        if (d.count != null) setCount(d.count);
      });
    fetch(`/api/edition/${slug}/check-images`)
      .then((r) => r.json())
      .then((d) => setMissingImages(d.missing ?? []));
    fetch(`/api/check-deployment/${slug}`)
      .then((r) => r.json())
      .then(setDeployment);
  }, [slug]);

  const loading =
    count === null || missingImages === null || deployment === null;
  const emailOnly = deployment?.email_only;
  const gitAvailable = deployment?.git_available ?? true;
  const hasMissingImages = missingImages?.length > 0;
  const notLive = !emailOnly && gitAvailable && deployment && !deployment.live;
  const hasUncommitted = !emailOnly && gitAvailable && deployment?.uncommitted;
  const hasUnpushed = !emailOnly && gitAvailable && deployment?.unpushed;
  const blocked = hasMissingImages || notLive || hasUncommitted || hasUnpushed;

  const warnings = [];
  if (deployment && !emailOnly) {
    if (gitAvailable && !deployment.live)
      warnings.push(
        `The edition isn't live yet${
          deployment.url ? ` (checked ${deployment.url})` : ""
        } — publish it before sending so images load for recipients.`,
      );
    if (deployment.uncommitted)
      warnings.push(
        "You have changes that haven't been saved yet — wait a moment for auto-save to finish, then try again.",
      );
    if (deployment.unpushed)
      warnings.push(
        "The edition has local changes that haven't been published to your site yet — hit Publish first.",
      );
  }

  return (
    <Modal onClose={onClose}>
      <h3>Send to everyone?</h3>
      <p>
        This will send "{title}" to {count ?? "…"} recipient
        {count !== 1 ? "s" : ""}. This cannot be undone.
      </p>
      {hasMissingImages && (
        <div className="warning-box">
          <strong>Missing images</strong> — these files are referenced but don't
          exist in the edition folder:
          <ul style={{ margin: "6px 0 0", paddingLeft: 20, fontSize: 13 }}>
            {missingImages.map((f) => (
              <li key={f}>
                <code>{f}</code>
              </li>
            ))}
          </ul>
          <p style={{ margin: "8px 0 0", fontSize: 13 }}>
            Upload them before sending.
          </p>
        </div>
      )}
      {count > 400 && (
        <div className="warning-box">
          You have {count} recipients. Gmail limits personal accounts to ~500
          emails/day — if you're close to that limit today, some sends may fail.
        </div>
      )}
      {warnings.map((w, i) => (
        <div key={i} className="warning-box">
          {w}
        </div>
      ))}
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>
          Cancel
        </button>
        <button
          className="btn btn-primary"
          onClick={onConfirm}
          disabled={loading || blocked}
        >
          Send
        </button>
      </div>
    </Modal>
  );
}
