import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, act } from "@testing-library/react";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import EditorPanel, { insertImageAtPos } from "./EditorPanel";

// Real CodeMirror needs browser APIs jsdom doesn't provide (measurement,
// ranges, etc). We only care about what props EditorPanel hands it, so
// replace it with a stub that records the `extensions` prop on every render.
const extensionsPerRender = [];

vi.mock("@uiw/react-codemirror", () => ({
  default: (props) => {
    extensionsPerRender.push(props.extensions);
    return null;
  },
}));

describe("EditorPanel", () => {
  beforeEach(() => {
    extensionsPerRender.length = 0;
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ intro: "", body: "hello world", mtime: 1 }),
      }),
    );
  });

  it("passes CodeMirror the same extensions array reference across re-renders", async () => {
    const { rerender } = render(<EditorPanel slug="test-edition" />);

    // Let the initial content-load fetch resolve and the resulting render flush.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    const before = extensionsPerRender[extensionsPerRender.length - 1];
    expect(before).toBeDefined();

    // Re-render EditorPanel the way its own state updates do on every
    // keystroke (setWordCount, setSaveStatus, etc. all live inside this
    // component and re-render it with the same `slug`/`focusMode` props).
    rerender(<EditorPanel slug="test-edition" />);

    const after = extensionsPerRender[extensionsPerRender.length - 1];

    // Regression guard: if `extensions` is a fresh array literal on every
    // render, react-codemirror reconfigures (and rebuilds every plugin in)
    // the whole editor state on every re-render — the cause of patr#4
    // ("Memory leak in the UI?" — app slows to a crawl / tab crashes after
    // ~1000-1500 words, since a re-render happens on every keystroke).
    expect(after).toBe(before);
  });
});

describe("insertImageAtPos", () => {
  it("inserts image markdown with the placeholder alt text selected", () => {
    const state = EditorState.create({ doc: "" });
    const view = new EditorView({ state, parent: document.body });

    insertImageAtPos(view, "photo.jpg");

    expect(view.state.doc.toString()).toBe("![Title](photo.jpg)");
    const sel = view.state.selection.main;
    // Selected (not just cursor-positioned) so typing immediately replaces
    // the placeholder with a real caption.
    expect(view.state.sliceDoc(sel.from, sel.to)).toBe("Title");

    view.destroy();
  });

  it("inserts at the cursor position, not always at the start", () => {
    const state = EditorState.create({
      doc: "before after",
      selection: { anchor: 6 }, // right after "before"
    });
    const view = new EditorView({ state, parent: document.body });

    insertImageAtPos(view, "photo.jpg");

    expect(view.state.doc.toString()).toBe("before![Title](photo.jpg) after");

    view.destroy();
  });
});
