import React from "react";

export default function Modal({ onClose, extraClass, children }) {
  return (
    <div
      className={`modal-overlay visible${extraClass ? ` ${extraClass}` : ""}`}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal">{children}</div>
    </div>
  );
}
