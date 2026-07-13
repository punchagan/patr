import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import DeleteEditionModal from "./DeleteEditionModal";

describe("DeleteEditionModal", () => {
  beforeEach(() => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        json: () =>
          Promise.resolve({
            path: "/home/user/.local/share/patr/backups/my-repo",
          }),
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("warns that images are not backed up, unlike the written text", () => {
    render(
      <DeleteEditionModal
        title="My Edition"
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByText(/images are not/i)).toBeInTheDocument();
  });

  it("fetches and shows the real backups directory path, not a hardcoded one", async () => {
    render(
      <DeleteEditionModal
        title="My Edition"
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    await waitFor(() =>
      expect(
        screen.getByText("/home/user/.local/share/patr/backups/my-repo"),
      ).toBeInTheDocument(),
    );
    expect(global.fetch).toHaveBeenCalledWith("/api/backups-dir");
  });
});
