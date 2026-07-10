import { describe, it, expect } from "vitest";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { markdown } from "@codemirror/lang-markdown";
import { forceParsing } from "@codemirror/language";
import { countSelectionWords } from "./EditorPanel";

function fullyParsedState(text, selection) {
  const view = new EditorView({
    state: EditorState.create({
      doc: text,
      selection,
      extensions: [markdown()],
    }),
  });
  forceParsing(view, text.length, 5000);
  const state = view.state;
  view.destroy();
  return state;
}

describe("countSelectionWords", () => {
  it("returns 0 when the selection is empty (just a cursor)", () => {
    const state = fullyParsedState("hello world", { anchor: 3 });
    expect(countSelectionWords({ state })).toBe(0);
  });

  it("counts only the words inside the selected range", () => {
    const text = "hello world one two three";
    // Select "world one two" (indices 6-19).
    const from = text.indexOf("world");
    const to = text.indexOf("three") - 1;
    const state = fullyParsedState(text, { anchor: from, head: to });
    expect(countSelectionWords({ state })).toBe(3);
  });

  it("excludes markdown syntax markers from the selection count, like the whole-document count does", () => {
    const text = "plain **bold** word";
    const from = 0;
    const to = text.length;
    const state = fullyParsedState(text, { anchor: from, head: to });
    // "plain", "bold", "word" — the ** marks shouldn't count as words.
    expect(countSelectionWords({ state })).toBe(3);
  });
});
