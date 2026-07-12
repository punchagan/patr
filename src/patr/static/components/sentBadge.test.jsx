import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import Sidebar from "./Sidebar";

// Scoped to .edition-list, since the sidebar's status/sent filter dropdowns
// also contain "Sent"/"Partially Sent" option text outside that container.
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
    sent: null,
    ...overrides,
  };
}

describe("Sidebar sent badge", () => {
  it("shows a Sent badge for a fully-sent edition", () => {
    render(<Sidebar {...baseProps} editions={[edition({ sent: "full" })]} />);
    expect(editionList().getByText("Sent")).toBeInTheDocument();
  });

  it("shows a Partially sent badge for a partially-sent edition", () => {
    render(
      <Sidebar {...baseProps} editions={[edition({ sent: "partial" })]} />,
    );
    expect(editionList().getByText("Partially sent")).toBeInTheDocument();
  });

  it("shows no sent badge for an edition that hasn't been sent", () => {
    render(<Sidebar {...baseProps} editions={[edition({ sent: null })]} />);
    expect(editionList().queryByText("Sent")).not.toBeInTheDocument();
    expect(editionList().queryByText("Partially sent")).not.toBeInTheDocument();
  });
});
