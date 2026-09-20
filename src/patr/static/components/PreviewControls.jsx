import React from "react";
import { PREVIEW_DEVICES, previewUrl } from "./previewDevices";

/**
 * Preview bar controls: pick the width to preview at (desktop / tablet /
 * phone), and open the preview in a full browser tab, where the browser's own
 * responsive mode and dev tools are available.
 */
export default function PreviewControls({
  slug,
  viewMode,
  device,
  onDeviceChange,
}) {
  return (
    <>
      <div
        className="preview-device-toggle"
        role="group"
        aria-label="Preview width"
      >
        {PREVIEW_DEVICES.map((d) => (
          <button
            key={d.id}
            className={`btn btn-toggle${device === d.id ? " active" : ""}`}
            aria-pressed={device === d.id}
            title={d.width ? `${d.label} (${d.width}px)` : "Full width"}
            onClick={() => onDeviceChange(d.id)}
          >
            {d.label}
          </button>
        ))}
      </div>
      <a
        className="btn"
        href={previewUrl(slug, viewMode)}
        target="_blank"
        rel="noopener noreferrer"
        title="Open this preview in a new browser tab"
      >
        Open ↗
      </a>
    </>
  );
}
