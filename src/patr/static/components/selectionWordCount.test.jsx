import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { markdown } from "@codemirror/lang-markdown";
import { forceParsing } from "@codemirror/language";
import EditorPanel from "./EditorPanel";

// Real CodeMirror needs browser APIs jsdom doesn't provide. We only need
// EditorPanel's own onCreateEditor/onUpdate wiring, so stub it and drive
// those callbacks ourselves with a real (detached) EditorView.
let latestOnCreateEditor;
let latestOnUpdate;

vi.mock("@uiw/react-codemirror", () => ({
  default: (props) => {
    latestOnCreateEditor = props.onCreateEditor;
    latestOnUpdate = props.onUpdate;
    return null;
  },
}));

function fullyParsedView(text, selection) {
  const view = new EditorView({
    state: EditorState.create({
      doc: text,
      selection,
      extensions: [markdown()],
    }),
  });
  forceParsing(view, text.length, 5000);
  return view;
}

describe("EditorPanel selection word count", () => {
  beforeEach(() => {
    latestOnCreateEditor = undefined;
    latestOnUpdate = undefined;
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            intro: "",
            body: "hello world one two three",
            mtime: 1,
          }),
      }),
    );
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("reports a selection word count via onWordCountChange when text is selected", async () => {
    const onWordCountChange = vi.fn();

    render(
      <EditorPanel slug="test-edition" onWordCountChange={onWordCountChange} />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    const text = "hello world one two three";
    const fakeView = fullyParsedView(text, { anchor: 0 });
    act(() => {
      latestOnCreateEditor(fakeView);
    });

    onWordCountChange.mockClear();

    // Select "world one two" (3 words) with no doc change.
    const from = text.indexOf("world");
    const to = text.indexOf("three") - 1;
    fakeView.setState(
      EditorState.create({
        doc: text,
        selection: { anchor: from, head: to },
        extensions: [markdown()],
      }),
    );
    forceParsing(fakeView, text.length, 5000);

    act(() => {
      latestOnUpdate({ selectionSet: true, docChanged: false, view: fakeView });
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    // Regression guard for patr#1: EditorPanel must surface a selection
    // word count, not just the whole-document total.
    const lastCall = onWordCountChange.mock.calls.at(-1);
    expect(lastCall[1]).toBe(3);
  });
});
