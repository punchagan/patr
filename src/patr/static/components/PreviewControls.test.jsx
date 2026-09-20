import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import PreviewControls from "./PreviewControls";

function renderControls(props = {}) {
  const onDeviceChange = vi.fn();
  render(
    <PreviewControls
      slug="my-ed"
      viewMode="web"
      device="desktop"
      onDeviceChange={onDeviceChange}
      {...props}
    />,
  );
  return { onDeviceChange };
}

describe("PreviewControls", () => {
  it("offers desktop, tablet and phone widths", () => {
    renderControls();
    for (const name of ["Desktop", "Tablet", "Phone"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
  });

  it("marks the current width as pressed", () => {
    renderControls({ device: "phone" });
    expect(screen.getByRole("button", { name: "Phone" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Desktop" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("reports the chosen width", () => {
    const { onDeviceChange } = renderControls();
    fireEvent.click(screen.getByRole("button", { name: "Tablet" }));
    expect(onDeviceChange).toHaveBeenCalledWith("tablet");
  });

  it("has a link that opens the preview in a new tab, safely", () => {
    renderControls({ viewMode: "web" });
    const link = screen.getByRole("link", { name: /open/i });
    expect(link).toHaveAttribute("href", "/preview/my-ed/web");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toMatch(/noopener/);
  });

  it("the new-tab link follows the email/web view", () => {
    renderControls({ viewMode: "email" });
    expect(screen.getByRole("link", { name: /open/i })).toHaveAttribute(
      "href",
      "/preview/my-ed/email",
    );
  });
});
