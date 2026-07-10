import { describe, it, expect } from "vitest";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { markdown } from "@codemirror/lang-markdown";
import { forceParsing } from "@codemirror/language";
import { buildMarkDecorations } from "./EditorPanel";

// 20 headings, one per line. Line 1 holds the cursor (its HeaderMark is
// never dimmed regardless of viewport), lines 2-20 are candidates for
// dimming.
const LINE_COUNT = 20;
const doc = Array.from(
  { length: LINE_COUNT },
  (_, i) => `# Heading ${i}`,
).join("\n");

// The lezer parser only parses as far as it's been asked to (real usage
// drives this incrementally via the live EditorView's idle-time
// scheduling). Use a detached EditorView + forceParsing to get a fully
// realized syntax tree without needing to render/measure anything.
function fullyParsedState() {
  const view = new EditorView({
    state: EditorState.create({
      doc,
      selection: { anchor: 0 },
      extensions: [markdown()],
    }),
  });
  forceParsing(view, doc.length, 5000);
  const state = view.state;
  view.destroy();
  return state;
}

describe("buildMarkDecorations", () => {
  it("only dims marks inside the given viewport, not the whole document", () => {
    const state = fullyParsedState();
    const line5End = state.doc.line(5).to;

    // A fake view exposing only what buildMarkDecorations reads: `state`
    // and `viewport`. Overriding viewport lets the test target a specific
    // window regardless of what a real (unmeasured, detached) view would
    // report.
    const view = { state, viewport: { from: 0, to: line5End } };

    const decorations = buildMarkDecorations(view);
    const positions = [];
    decorations.between(0, doc.length, (from) => positions.push(from));

    // Sanity check: the document really does have marks past the
    // viewport, so this test would catch a regression either way.
    expect(positions.length).toBeGreaterThan(0);

    // Regression guard: scanning the whole document (ignoring the
    // viewport) is O(document size) on every doc change/selection/viewport
    // event — cost that grows unbounded as the edition gets longer. This
    // was part of the slowdown behind patr#4 ("Memory leak in the UI?").
    // Fixing it means only marks inside [viewport.from, viewport.to] may
    // be dimmed.
    for (const from of positions) {
      expect(from).toBeLessThanOrEqual(line5End);
    }
  });
});
