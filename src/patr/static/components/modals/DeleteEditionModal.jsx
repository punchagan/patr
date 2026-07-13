import React, { useEffect, useState } from "react";
import Modal from "./Modal";

export default function DeleteEditionModal({ title, onClose, onConfirm }) {
  const [backupsDir, setBackupsDir] = useState(null);

  useEffect(() => {
    fetch("/api/backups-dir")
      .then((r) => r.json())
      .then((d) => setBackupsDir(d.path))
      .catch(() => {});
  }, []);

  return (
    <Modal onClose={onClose} extraClass="modal-delete">
      <h3>Delete "{title}"?</h3>
      <p>
        This will permanently delete the edition, including any uploaded images.
        It cannot be undone from within the app.
      </p>
      <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
        Only the written text is backed up
        {backupsDir ? (
          <>
            {" "}
            (in <code>{backupsDir}</code>)
          </>
        ) : (
          ""
        )}{" "}
        — images are not, so they will be gone for good.
      </p>
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>
          Cancel
        </button>
        <button className="btn btn-danger" onClick={onConfirm}>
          Delete
        </button>
      </div>
    </Modal>
  );
}
