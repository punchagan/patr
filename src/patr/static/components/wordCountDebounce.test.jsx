import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { markdown } from "@codemirror/lang-markdown";
import { forceParsing } from "@codemirror/language";
import EditorPanel from "./EditorPanel";

// Real CodeMirror needs browser APIs jsdom doesn't provide. We only need
// EditorPanel's own onChange/onCreateEditor wiring, so stub it and drive
// those callbacks ourselves with a real (detached) EditorView backing the
// `view` ref that countWordsFromView reads from.
let latestOnChange;
let latestOnCreateEditor;

vi.mock("@uiw/react-codemirror", () => ({
  default: (props) => {
    latestOnChange = props.onChange;
    latestOnCreateEditor = props.onCreateEditor;
    return null;
  },
}));

function fullyParsedView(text) {
  const view = new EditorView({
    state: EditorState.create({ doc: text, extensions: [markdown()] }),
  });
  forceParsing(view, text.length, 5000);
  return view;
}

describe("EditorPanel word count", () => {
  beforeEach(() => {
    latestOnChange = undefined;
    latestOnCreateEditor = undefined;
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ intro: "", body: "hello", mtime: 1 }),
      }),
    );
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("debounces word-count recomputation instead of scanning the whole document on every keystroke", async () => {
    const onWordCountChange = vi.fn();

    render(
      <EditorPanel slug="test-edition" onWordCountChange={onWordCountChange} />,
    );

    // Let the initial content-load fetch resolve.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    const fakeView = fullyParsedView("hello");
    act(() => {
      latestOnCreateEditor(fakeView);
    });

    onWordCountChange.mockClear();

    // Simulate three rapid keystrokes.
    for (const text of [
      "hello world",
      "hello world one",
      "hello world one two",
    ]) {
      fakeView.setState(
        EditorState.create({ doc: text, extensions: [markdown()] }),
      );
      forceParsing(fakeView, text.length, 5000);
      act(() => {
        latestOnChange(text);
      });
    }

    // Regression guard: recomputing the word count via a full syntax-tree
    // walk + full-document string rebuild synchronously on every keystroke
    // is O(document size) per keystroke — part of the slowdown behind
    // patr#4 ("Memory leak in the UI?"). A debounced recompute should not
    // have fired yet for any of the 3 simulated keystrokes above.
    expect(onWordCountChange).not.toHaveBeenCalled();

    // After the debounce window elapses, it should fire (once).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(onWordCountChange).toHaveBeenCalled();
  });
});
