import { describe, it, expect, beforeEach } from "vitest";
import {
  PREVIEW_DEVICES,
  previewFrameWidth,
  previewUrl,
  loadPreviewDevice,
  savePreviewDevice,
} from "./previewDevices";

describe("previewFrameWidth", () => {
  it("desktop fills the pane", () => {
    expect(previewFrameWidth("desktop")).toBe("100%");
  });

  it("tablet and phone are fixed widths, so the site's media queries fire", () => {
    expect(previewFrameWidth("tablet")).toBe("768px");
    expect(previewFrameWidth("phone")).toBe("390px");
  });

  it("falls back to the full pane for an unknown device", () => {
    expect(previewFrameWidth("watch")).toBe("100%");
  });
});

describe("PREVIEW_DEVICES", () => {
  it("lists desktop first, then the narrower ones", () => {
    expect(PREVIEW_DEVICES.map((d) => d.id)).toEqual([
      "desktop",
      "tablet",
      "phone",
    ]);
  });
});

describe("previewUrl", () => {
  it("is the edition's email or web preview route", () => {
    expect(previewUrl("my-ed", "web")).toBe("/preview/my-ed/web");
    expect(previewUrl("my-ed", "email")).toBe("/preview/my-ed/email");
  });
});

describe("remembering the chosen device", () => {
  beforeEach(() => localStorage.clear());

  it("defaults to desktop", () => {
    expect(loadPreviewDevice()).toBe("desktop");
  });

  it("returns what was saved", () => {
    savePreviewDevice("phone");
    expect(loadPreviewDevice()).toBe("phone");
  });

  it("ignores a stored value that isn't a known device", () => {
    localStorage.setItem("patr-preview-device", "watch");
    expect(loadPreviewDevice()).toBe("desktop");
  });
});
