const PREVIEW_DEVICE_KEY = "patr-preview-device";
const FULL_WIDTH = "100%";

/**
 * Widths the preview can be shown at. Desktop fills the pane; the others are
 * fixed, phone-/tablet-like widths, so the site's own media queries fire and
 * you see the layout a reader on that device would.
 */
export const PREVIEW_DEVICES = [
  { id: "desktop", label: "Desktop", width: null },
  { id: "tablet", label: "Tablet", width: 768 },
  { id: "phone", label: "Phone", width: 390 },
];

/** CSS width for the preview frame at a device (the full pane if unknown). */
export function previewFrameWidth(deviceId) {
  const device = PREVIEW_DEVICES.find((d) => d.id === deviceId);
  return device?.width ? `${device.width}px` : FULL_WIDTH;
}

/** The server route that renders an edition's email or web preview. */
export function previewUrl(slug, viewMode) {
  return `/preview/${slug}/${viewMode}`;
}

/** The device last chosen (remembered across editions), else desktop. */
export function loadPreviewDevice() {
  const stored = localStorage.getItem(PREVIEW_DEVICE_KEY);
  return PREVIEW_DEVICES.some((d) => d.id === stored) ? stored : "desktop";
}

/** Remember the chosen device for next time. */
export function savePreviewDevice(deviceId) {
  localStorage.setItem(PREVIEW_DEVICE_KEY, deviceId);
}
