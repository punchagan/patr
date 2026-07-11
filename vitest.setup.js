import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// jsdom doesn't implement layout, so Range has no getClientRects/
// getBoundingClientRect — CodeMirror calls these when measuring text during
// its internal input-handling pipeline (e.g. a real paste event dispatched
// on contentDOM), which otherwise throws inside a requestAnimationFrame
// callback. Empty rects are fine since tests never assert on layout.
if (typeof Range !== "undefined") {
  Range.prototype.getClientRects ??= () => [];
  Range.prototype.getBoundingClientRect ??= () => ({
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    width: 0,
    height: 0,
  });
}
