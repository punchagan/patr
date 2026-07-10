import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
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
