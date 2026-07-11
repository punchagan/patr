import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
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
  let createdViews;

  beforeEach(() => {
    createdViews = [];
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

  afterEach(() => {
    // Destroy every real EditorView we created so CodeMirror cancels its
    // scheduled rAF measurement — otherwise it fires after the test ends
    // and throws (jsdom doesn't implement getClientRects), which is just
    // noise but worth avoiding.
    for (const view of createdViews) view.destroy();
  });

  async function setUpEditor() {
    const { rerender } = render(<EditorPanel slug="test-edition" />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const fakeView = detachedView("hello");
    createdViews.push(fakeView);
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

    // Dispatch on contentDOM, matching a real paste's event target — this
    // is what makes CodeMirror's own internal paste handler (which runs
    // before our listener on the ancestor view.dom sees the bubbled event)
    // actually fire, exercising the real race the fix accounts for.
    await act(async () => {
      dispatchPaste(fakeView.contentDOM, "https://tenor.com/view/cat-gif-123");
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/edition/test-edition/download-gif",
      expect.objectContaining({ method: "POST" }),
    );
    // The raw link must not remain alongside the inserted image.
    expect(fakeView.state.doc.toString()).toBe("![](abc123.gif)hello");
  });

  it("shows a placeholder while the GIF is being fetched, then swaps it in", async () => {
    let resolveFetch;
    global.fetch = vi.fn((url) => {
      const u = typeof url === "string" ? url : "";
      if (u.includes("/content")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ intro: "", body: "hello", mtime: 1 }),
        });
      }
      if (u.includes("/download-gif")) {
        return new Promise((resolve) => {
          resolveFetch = resolve;
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    const fakeView = await setUpEditor();

    act(() => {
      dispatchPaste(fakeView.contentDOM, "https://tenor.com/view/cat-gif-123");
    });
    await act(async () => {
      await Promise.resolve();
    });

    // While the download is still pending, a placeholder replaces the raw
    // link — the user shouldn't see the bare URL sitting there mid-fetch.
    expect(fakeView.state.doc.toString()).toContain("Fetching GIF");
    expect(fakeView.state.doc.toString()).not.toContain("tenor.com");

    await act(async () => {
      resolveFetch({
        ok: true,
        json: () => Promise.resolve({ path: "abc123.gif" }),
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fakeView.state.doc.toString()).toBe("![](abc123.gif)hello");
  });

  it("restores the original link if the GIF download fails", async () => {
    let resolveFetch;
    global.fetch = vi.fn((url) => {
      const u = typeof url === "string" ? url : "";
      if (u.includes("/content")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ intro: "", body: "hello", mtime: 1 }),
        });
      }
      if (u.includes("/download-gif")) {
        return new Promise((resolve) => {
          resolveFetch = resolve;
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    const fakeView = await setUpEditor();

    act(() => {
      dispatchPaste(fakeView.contentDOM, "https://tenor.com/view/cat-gif-123");
    });
    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      resolveFetch({ ok: false, json: () => Promise.resolve({}) });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fakeView.state.doc.toString()).toBe(
      "https://tenor.com/view/cat-gif-123hello",
    );
  });

  it("does not intercept a normal text paste", async () => {
    const fakeView = await setUpEditor();

    await act(async () => {
      dispatchPaste(fakeView.contentDOM, "just some regular text");
      await Promise.resolve();
    });

    const gifCalls = global.fetch.mock.calls.filter(([url]) =>
      String(url).includes("download-gif"),
    );
    expect(gifCalls).toHaveLength(0);
    expect(fakeView.state.doc.toString()).toBe("just some regular texthello");
  });
});
