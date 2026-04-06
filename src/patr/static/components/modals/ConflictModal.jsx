import React from "react";
import SideBySideDiff from "./SideBySideDiff";

export default function ConflictModal({
  mine,
  theirs,
  onKeepMine,
  onKeepTheirs,
  onDismiss,
}) {
  return (
    <div
      className="conflict-modal modal-overlay visible"
      onClick={(e) => e.target === e.currentTarget && onDismiss()}
    >
      <div className="modal modal-conflict">
        <h3>File changed on disk</h3>
        <p>
          The file was modified outside Patr while you were editing. What do you
          want to do?
        </p>
        <SideBySideDiff mine={mine} theirs={theirs} />
        <div className="modal-actions">
          <button className="btn" onClick={onDismiss}>
            Dismiss
          </button>
          <button className="btn" onClick={onKeepTheirs}>
            Use disk version
          </button>
          <button className="btn btn-primary" onClick={onKeepMine}>
            Keep mine
          </button>
        </div>
      </div>
    </div>
  );
}
