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

const sampleEditions = [
  {
    slug: "spring-art",
    title: "Spring Art Gallery",
    date: "2026-03-01",
    draft: false,
    sent: "full",
  },
  {
    slug: "summer-notes",
    title: "Summer Notes",
    date: "2026-06-01",
    draft: false,
    sent: "partial",
  },
  {
    slug: "autumn-draft",
    title: "Autumn Draft Edition",
    date: "2026-09-01",
    draft: true,
    sent: null,
  },
  {
    slug: "winter-plans",
    title: "Winter Plans",
    date: "2026-12-01",
    draft: true,
    sent: null,
  },
];

describe("Sidebar search and status filter", () => {
  it("has no clear button when the search is empty", () => {
    render(<Sidebar {...baseProps} editions={sampleEditions} />);
    expect(screen.queryByLabelText(/clear search/i)).not.toBeInTheDocument();
  });

  it("shows a clear button once text is typed, and clicking it resets the search", () => {
    render(<Sidebar {...baseProps} editions={sampleEditions} />);
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.change(input, { target: { value: "spring" } });
    expect(screen.queryByText("Winter Plans")).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/clear search/i));
    expect(input).toHaveValue("");
    expect(screen.getByText("Winter Plans")).toBeInTheDocument();
  });

  it("filters editions by title as you type", () => {
    render(<Sidebar {...baseProps} editions={sampleEditions} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: "spring" },
    });
    expect(screen.getByText("Spring Art Gallery")).toBeInTheDocument();
    expect(screen.queryByText("Summer Notes")).not.toBeInTheDocument();
    expect(screen.queryByText("Autumn Draft Edition")).not.toBeInTheDocument();
  });

  it("search is case-insensitive", () => {
    render(<Sidebar {...baseProps} editions={sampleEditions} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: "WINTER" },
    });
    expect(screen.getByText("Winter Plans")).toBeInTheDocument();
  });

  it("shows all editions again when the search is cleared", () => {
    render(<Sidebar {...baseProps} editions={sampleEditions} />);
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.change(input, { target: { value: "spring" } });
    fireEvent.change(input, { target: { value: "" } });
    for (const e of sampleEditions) {
      expect(screen.getByText(e.title)).toBeInTheDocument();
    }
  });

  it("filters by lifecycle status: drafts only", () => {
    render(<Sidebar {...baseProps} editions={sampleEditions} />);
    fireEvent.change(screen.getByLabelText(/^status/i), {
      target: { value: "draft" },
    });
    expect(screen.getByText("Autumn Draft Edition")).toBeInTheDocument();
    expect(screen.getByText("Winter Plans")).toBeInTheDocument();
    expect(screen.queryByText("Spring Art Gallery")).not.toBeInTheDocument();
    expect(screen.queryByText("Summer Notes")).not.toBeInTheDocument();
  });

  it("filters by lifecycle status: published only", () => {
    render(<Sidebar {...baseProps} editions={sampleEditions} />);
    fireEvent.change(screen.getByLabelText(/^status/i), {
      target: { value: "published" },
    });
    expect(screen.getByText("Spring Art Gallery")).toBeInTheDocument();
    expect(screen.getByText("Summer Notes")).toBeInTheDocument();
    expect(screen.queryByText("Autumn Draft Edition")).not.toBeInTheDocument();
    expect(screen.queryByText("Winter Plans")).not.toBeInTheDocument();
  });

  it("filters by sent axis: sent only", () => {
    render(<Sidebar {...baseProps} editions={sampleEditions} />);
    fireEvent.change(screen.getByLabelText(/^sent/i), {
      target: { value: "sent" },
    });
    expect(screen.getByText("Spring Art Gallery")).toBeInTheDocument();
    expect(screen.queryByText("Summer Notes")).not.toBeInTheDocument();
    expect(screen.queryByText("Autumn Draft Edition")).not.toBeInTheDocument();
  });

  it("filters by sent axis: partially sent only", () => {
    render(<Sidebar {...baseProps} editions={sampleEditions} />);
    fireEvent.change(screen.getByLabelText(/^sent/i), {
      target: { value: "partial" },
    });
    expect(screen.getByText("Summer Notes")).toBeInTheDocument();
    expect(screen.queryByText("Spring Art Gallery")).not.toBeInTheDocument();
  });

  it("filters by sent axis: not sent only", () => {
    render(<Sidebar {...baseProps} editions={sampleEditions} />);
    fireEvent.change(screen.getByLabelText(/^sent/i), {
      target: { value: "unsent" },
    });
    expect(screen.getByText("Autumn Draft Edition")).toBeInTheDocument();
    expect(screen.getByText("Winter Plans")).toBeInTheDocument();
    expect(screen.queryByText("Spring Art Gallery")).not.toBeInTheDocument();
    expect(screen.queryByText("Summer Notes")).not.toBeInTheDocument();
  });

  it("combines lifecycle and sent axes: published + not sent", () => {
    const mixed = [
      ...sampleEditions,
      {
        slug: "ready-to-send",
        title: "Ready To Send",
        date: "2027-01-01",
        draft: false,
        sent: null,
      },
    ];
    render(<Sidebar {...baseProps} editions={mixed} />);
    fireEvent.change(screen.getByLabelText(/^status/i), {
      target: { value: "published" },
    });
    fireEvent.change(screen.getByLabelText(/^sent/i), {
      target: { value: "unsent" },
    });
    expect(screen.getByText("Ready To Send")).toBeInTheDocument();
    expect(screen.queryByText("Spring Art Gallery")).not.toBeInTheDocument();
    expect(screen.queryByText("Winter Plans")).not.toBeInTheDocument();
  });

  it("combines search and status filter", () => {
    render(<Sidebar {...baseProps} editions={sampleEditions} />);
    fireEvent.change(screen.getByLabelText(/^status/i), {
      target: { value: "draft" },
    });
    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: "winter" },
    });
    expect(screen.getByText("Winter Plans")).toBeInTheDocument();
    expect(screen.queryByText("Autumn Draft Edition")).not.toBeInTheDocument();
  });

  it("shows a no-match message when filters exclude everything", () => {
    render(<Sidebar {...baseProps} editions={sampleEditions} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: "nonexistent" },
    });
    expect(screen.getByText(/no editions match/i)).toBeInTheDocument();
  });
});

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

  it("shows git pull instructions for an editable checkout install", () => {
    render(
      <Sidebar
        {...baseProps}
        updateAvailable={true}
        updateSafe={false}
        installMethod="editable"
      />,
    );
    expect(screen.getByText(/git pull --ff-only/)).toBeInTheDocument();
    expect(screen.getByText(/uv sync/)).toBeInTheDocument();
  });

  it("shows uv tool upgrade instructions for a vcs install", () => {
    render(
      <Sidebar
        {...baseProps}
        updateAvailable={true}
        updateSafe={false}
        installMethod="vcs"
      />,
    );
    expect(screen.getByText(/uv tool upgrade patr/)).toBeInTheDocument();
    expect(screen.queryByText(/git pull/)).not.toBeInTheDocument();
  });

  it("falls back to a generic message when the install method is unknown", () => {
    render(
      <Sidebar
        {...baseProps}
        updateAvailable={true}
        updateSafe={false}
        installMethod="unknown"
      />,
    );
    expect(screen.getByText(/ask.*maintainer/i)).toBeInTheDocument();
    expect(screen.queryByText(/git pull/)).not.toBeInTheDocument();
    expect(screen.queryByText(/uv tool upgrade/)).not.toBeInTheDocument();
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
      await vi.advanceTimersByTimeAsync(2000); // initial delay elapses, first poll: fails
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000); // second poll: succeeds
    });

    expect(reload).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("gives up and shows an error after repeated failed retries", async () => {
    global.fetch = vi.fn((url) => {
      if (url === "/api/apply-update") {
        return Promise.resolve({ json: () => Promise.resolve({ ok: true }) });
      }
      return Promise.reject(new Error("still down"));
    });

    render(<Sidebar {...baseProps} updateAvailable={true} updateSafe={true} />);
    fireEvent.click(screen.getByRole("button", { name: /update now/i }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0); // apply-update resolves
    });
    await act(async () => {
      // initial delay + enough retry intervals to exhaust all attempts
      await vi.advanceTimersByTimeAsync(2000 + 1000 * 10);
    });

    expect(screen.getByText(/did not come back/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /update now/i }),
    ).toBeInTheDocument();
  });
});
