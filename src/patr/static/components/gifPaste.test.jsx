import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, act } from "@testing-library/react";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { markdown } from "@codemirror/lang-markdown";
import EditorPanel from "./EditorPanel";

// Real CodeMirror needs browser APIs jsdom doesn't provide. We only need
// EditorPanel's own onCreateEditor wiring plus a real (detached) EditorView
// so `view.dom` is a genuine element we can dispatch a paste event on.
let latestOnCreateEditor;

vi.mock("@uiw/react-codemirror", () => ({
  default: (props) => {
    latestOnCreateEditor = props.onCreateEditor;
    return null;
  },
}));

function detachedView(text) {
  return new EditorView({
    state: EditorState.create({ doc: text, extensions: [markdown()] }),
  });
}

function dispatchPaste(dom, text) {
  const event = new Event("paste", { bubbles: true, cancelable: true });
  event.clipboardData = {
    files: [],
    getData: (type) => (type === "text/plain" ? text : ""),
  };
  dom.dispatchEvent(event);
  return event;
}

describe("EditorPanel GIF paste", () => {
  beforeEach(() => {
    latestOnCreateEditor = undefined;
    global.fetch = vi.fn((url) => {
      const u = typeof url === "string" ? url : "";
      if (u.includes("/content")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ intro: "", body: "hello", mtime: 1 }),
        });
      }
      if (u.includes("/download-gif")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ path: "abc123.gif" }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
  });

  async function setUpEditor() {
    const { rerender } = render(<EditorPanel slug="test-edition" />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const fakeView = detachedView("hello");
    act(() => {
      latestOnCreateEditor(fakeView);
    });
    // Force a re-render so the paste/drop effect (keyed on viewRef.current)
    // notices the view and attaches its listeners.
    rerender(<EditorPanel slug="test-edition" />);
    return fakeView;
  }

  it("intercepts a pasted Tenor link, downloads it, and inserts a markdown image", async () => {
    const fakeView = await setUpEditor();

    let event;
    await act(async () => {
      event = dispatchPaste(fakeView.dom, "https://tenor.com/view/cat-gif-123");
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(event.defaultPrevented).toBe(true);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/edition/test-edition/download-gif",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fakeView.state.doc.toString()).toContain("![](abc123.gif)");
  });

  it("does not intercept a normal text paste", async () => {
    const fakeView = await setUpEditor();

    let event;
    await act(async () => {
      event = dispatchPaste(fakeView.dom, "just some regular text");
      await Promise.resolve();
    });

    expect(event.defaultPrevented).toBe(false);
    const gifCalls = global.fetch.mock.calls.filter(([url]) =>
      String(url).includes("download-gif"),
    );
    expect(gifCalls).toHaveLength(0);
  });
});
