import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import EditorPanel from "./EditorPanel";

vi.mock("@uiw/react-codemirror", () => ({
  default: () => null,
}));

describe("EditorPanel GIF toolbar button", () => {
  beforeEach(() => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ intro: "", body: "", mtime: 1 }),
      }),
    );
  });

  it("opens Tenor in a new tab", () => {
    const windowOpen = vi.spyOn(window, "open").mockImplementation(() => {});
    render(<EditorPanel slug="test-edition" />);
    fireEvent.mouseDown(screen.getByTitle(/insert gif/i));
    expect(windowOpen).toHaveBeenCalledWith("https://tenor.com", "_blank");
    windowOpen.mockRestore();
  });
});
