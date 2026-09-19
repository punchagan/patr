import React from "react";

/**
 * The action bar's status pill. If the status has an `href` (the edition's
 * page on the site), append a link that opens it in a new tab, so the writer
 * can go and check the published page.
 */
export default function StatusMessage({ status }) {
  if (!status) return null;
  return (
    <span className={`status-msg ${status.cls}`}>
      {status.text}
      {status.href && (
        <>
          {" "}
          <a href={status.href} target="_blank" rel="noopener noreferrer">
            View page ↗
          </a>
        </>
      )}
    </span>
  );
}
