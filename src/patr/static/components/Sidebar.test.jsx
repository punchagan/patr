import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import Sidebar from "./Sidebar";

const baseProps = {
  editions: [],
  warnings: [],
  selectedSlug: null,
  editingFooter: false,
  hidden: false,
  onSelect: vi.fn(),
  onFooter: vi.fn(),
  onNewEdition: vi.fn(),
  onSettings: vi.fn(),
  onHelp: vi.fn(),
  onEditionUpdated: vi.fn(),
};

describe("Sidebar update banner", () => {
  it("shows a nudge when a newer version is available", () => {
    render(<Sidebar {...baseProps} updateAvailable={true} />);
    expect(screen.getByText(/newer version/i)).toBeInTheDocument();
  });

  it("shows nothing when patr is up to date", () => {
    render(<Sidebar {...baseProps} updateAvailable={false} />);
    expect(screen.queryByText(/newer version/i)).not.toBeInTheDocument();
  });

  it("can be dismissed", () => {
    render(<Sidebar {...baseProps} updateAvailable={true} />);
    fireEvent.click(screen.getByLabelText(/dismiss/i));
    expect(screen.queryByText(/newer version/i)).not.toBeInTheDocument();
  });
});

describe("Sidebar self-update button", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    global.confirm = vi.fn(() => true);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("is not shown when the update isn't safe to apply automatically", () => {
    render(
      <Sidebar {...baseProps} updateAvailable={true} updateSafe={false} />,
    );
    expect(
      screen.queryByRole("button", { name: /update now/i }),
    ).not.toBeInTheDocument();
  });

  it("shows manual update instructions when the update isn't safe to apply automatically", () => {
    render(
      <Sidebar {...baseProps} updateAvailable={true} updateSafe={false} />,
    );
    expect(screen.getByText(/git pull --ff-only/)).toBeInTheDocument();
    expect(screen.getByText(/uv sync/)).toBeInTheDocument();
  });

  it("does not show manual update instructions when it's safe to auto-update", () => {
    render(<Sidebar {...baseProps} updateAvailable={true} updateSafe={true} />);
    expect(screen.queryByText(/git pull --ff-only/)).not.toBeInTheDocument();
  });

  it("is shown when the update is safe to apply automatically", () => {
    render(<Sidebar {...baseProps} updateAvailable={true} updateSafe={true} />);
    expect(
      screen.getByRole("button", { name: /update now/i }),
    ).toBeInTheDocument();
  });

  it("does nothing if the user cancels the confirmation", () => {
    global.confirm = vi.fn(() => false);
    global.fetch = vi.fn();
    render(<Sidebar {...baseProps} updateAvailable={true} updateSafe={true} />);
    fireEvent.click(screen.getByRole("button", { name: /update now/i }));
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("posts to /api/apply-update after confirmation", () => {
    global.fetch = vi.fn(() => new Promise(() => {})); // never resolves in this test
    render(<Sidebar {...baseProps} updateAvailable={true} updateSafe={true} />);
    fireEvent.click(screen.getByRole("button", { name: /update now/i }));
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/apply-update",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows an error and re-enables the button when the update can't be applied", async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        json: () => Promise.resolve({ ok: false, error: "tree is dirty" }),
      }),
    );
    render(<Sidebar {...baseProps} updateAvailable={true} updateSafe={true} />);
    fireEvent.click(screen.getByRole("button", { name: /update now/i }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText(/tree is dirty/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /update now/i }),
    ).toBeInTheDocument();
  });

  it("polls until the server comes back, then reloads the page", async () => {
    let editionsCallCount = 0;
    global.fetch = vi.fn((url) => {
      if (url === "/api/apply-update") {
        return Promise.resolve({ json: () => Promise.resolve({ ok: true }) });
      }
      // Simulate the server being down for the first poll, then back up.
      editionsCallCount += 1;
      if (editionsCallCount === 1) return Promise.reject(new Error("down"));
      return Promise.resolve({ ok: true });
    });
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });

    render(<Sidebar {...baseProps} updateAvailable={true} updateSafe={true} />);
    fireEvent.click(screen.getByRole("button", { name: /update now/i }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0); // apply-update resolves
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000); // first poll: fails
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000); // second poll: succeeds
    });

    expect(reload).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
