import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import ConfirmModal from "./ConfirmModal";

/** Stub the three endpoints the modal fetches on mount. */
function mockFetch(deployment) {
  global.fetch = vi.fn((url) => {
    let body = {};
    if (url.includes("/api/contacts/count")) body = { count: 3 };
    else if (url.includes("check-images")) body = { missing: [] };
    else if (url.includes("check-deployment")) body = deployment;
    return Promise.resolve({ json: () => Promise.resolve(body) });
  });
}

function renderModal() {
  render(
    <ConfirmModal
      slug="my-ed"
      title="My Edition"
      onClose={vi.fn()}
      onConfirm={vi.fn()}
    />,
  );
}

const sendButton = () => screen.getByRole("button", { name: "Send" });

describe("ConfirmModal deployment warnings", () => {
  afterEach(() => vi.restoreAllMocks());

  it("blocks sending when the site isn't live (normal setup)", async () => {
    mockFetch({
      live: false,
      git_available: true,
      url: "https://x/newsletter/a/",
    });
    renderModal();
    await waitFor(() =>
      expect(screen.getByText(/isn't live yet/i)).toBeInTheDocument(),
    );
    expect(sendButton()).toBeDisabled();
  });

  it("subscribers-only: doesn't claim the edition isn't live, and can send", async () => {
    mockFetch({
      live: null,
      subscribers_only: true,
      git_available: true,
      uncommitted: false,
      unpushed: false,
      url: "https://x/newsletter/a/",
    });
    renderModal();
    await waitFor(() => expect(sendButton()).not.toBeDisabled());
    expect(screen.queryByText(/isn't live yet/i)).not.toBeInTheDocument();
  });

  it("subscribers-only: reminds the user to check the deploy manually", async () => {
    mockFetch({
      live: null,
      subscribers_only: true,
      git_available: true,
      uncommitted: false,
      unpushed: false,
    });
    renderModal();
    await waitFor(() =>
      expect(screen.getByText(/subscribers-only/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/confirm|manual/i)).toBeInTheDocument();
  });

  it("subscribers-only: the reminder links to the edition's page", async () => {
    mockFetch({
      live: null,
      subscribers_only: true,
      git_available: true,
      uncommitted: false,
      unpushed: false,
      url: "https://x/newsletter/a/",
    });
    renderModal();
    const link = await screen.findByRole("link", { name: /open|view/i });
    expect(link).toHaveAttribute("href", "https://x/newsletter/a/");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("subscribers-only: still blocks on unpushed changes", async () => {
    mockFetch({
      live: null,
      subscribers_only: true,
      git_available: true,
      uncommitted: false,
      unpushed: true,
    });
    renderModal();
    await waitFor(() =>
      expect(screen.getByText(/haven't been published/i)).toBeInTheDocument(),
    );
    expect(sendButton()).toBeDisabled();
  });
});
