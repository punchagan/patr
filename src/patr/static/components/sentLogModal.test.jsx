import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import Sidebar from "./Sidebar";

// Scoped to .edition-list, since the sidebar's status/sent filter dropdowns
// also contain "Sent" option text outside that container.
function editionList() {
  return within(document.querySelector(".edition-list"));
}

const baseProps = {
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

function edition(overrides) {
  return {
    slug: "my-ed",
    title: "My Edition",
    date: "2024-01-01",
    draft: false,
    sent: "full",
    ...overrides,
  };
}

describe("Sent log modal", () => {
  beforeEach(() => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        json: () =>
          Promise.resolve({
            entries: [{ email: "alice@example.com", sent_at: "2024-01-01" }],
          }),
      }),
    );
  });

  it("opens the sent log modal and fetches entries when the badge is clicked", async () => {
    render(<Sidebar {...baseProps} editions={[edition()]} />);
    fireEvent.click(editionList().getByText("Sent"));

    expect(global.fetch).toHaveBeenCalledWith("/api/edition/my-ed/sent-log");
    await waitFor(() =>
      expect(screen.getByText("alice@example.com")).toBeInTheDocument(),
    );
  });

  it("closes the modal", async () => {
    render(<Sidebar {...baseProps} editions={[edition()]} />);
    fireEvent.click(editionList().getByText("Sent"));
    await waitFor(() =>
      expect(screen.getByText("alice@example.com")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText("Close"));
    expect(screen.queryByText("alice@example.com")).not.toBeInTheDocument();
  });
});
