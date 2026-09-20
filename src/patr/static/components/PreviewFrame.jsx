import React from "react";
import { previewFrameWidth, previewUrl } from "./previewDevices";

/**
 * The preview iframe. At a fixed device width it sits centred in the pane, so
 * the page inside sees a phone- or tablet-sized viewport and applies its
 * mobile media queries, as it would on a real device.
 */
export default function PreviewFrame({ slug, viewMode, previewKey, device }) {
  const framed = previewFrameWidth(device) !== "100%";
  return (
    <div className="preview-stage">
      <iframe
        key={`${slug}-${viewMode}-${previewKey}`}
        title={`${viewMode} preview`}
        className={`preview-frame${framed ? " framed" : ""}`}
        style={{ width: previewFrameWidth(device) }}
        src={previewUrl(slug, viewMode)}
      />
    </div>
  );
}
