import React from "react";
import Modal from "./Modal";

export default function DeleteEditionModal({ title, onClose, onConfirm }) {
  return (
    <Modal onClose={onClose} extraClass="modal-delete">
      <h3>Delete "{title}"?</h3>
      <p>
        This will permanently delete the edition. It cannot be undone from
        within the app.
      </p>
      <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
        If you have backups enabled, previous versions are still recoverable
        from <code>~/.local/share/patr/backups/</code>.
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
