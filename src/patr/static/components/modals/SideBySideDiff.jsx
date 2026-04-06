import React, { useMemo } from "react";
import { diffLines } from "diff";

function buildRows(mine, theirs) {
  const parts = diffLines(theirs, mine);
  const rows = [];
  let i = 0;
  while (i < parts.length) {
    const part = parts[i];
    if (!part.added && !part.removed) {
      rows.push({ left: part.value, right: part.value, type: "same" });
      i++;
    } else if (part.removed) {
      if (i + 1 < parts.length && parts[i + 1].added) {
        rows.push({
          left: parts[i + 1].value,
          right: part.value,
          type: "changed",
        });
        i += 2;
      } else {
        rows.push({ left: "", right: part.value, type: "removed" });
        i++;
      }
    } else {
      rows.push({ left: part.value, right: "", type: "added" });
      i++;
    }
  }
  return rows;
}

export default function SideBySideDiff({ mine, theirs }) {
  const rows = useMemo(() => buildRows(mine, theirs), [mine, theirs]);
  return (
    <div className="conflict-diff-side">
      <div className="conflict-diff-header">
        <div>Mine</div>
        <div>Disk</div>
      </div>
      <div className="conflict-diff-body">
        {rows.map((row, i) => (
          <div key={i} className={`diff-row diff-row-${row.type}`}>
            <pre className="diff-cell diff-cell-left">{row.left}</pre>
            <pre className="diff-cell diff-cell-right">{row.right}</pre>
          </div>
        ))}
      </div>
    </div>
  );
}
