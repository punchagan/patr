import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import StatusMessage from "./StatusMessage";

describe("StatusMessage", () => {
  it("shows the text with its severity class", () => {
    render(
      <StatusMessage status={{ cls: "warn", text: "Not published yet" }} />,
    );
    const el = screen.getByText("Not published yet");
    expect(el).toHaveClass("status-msg", "warn");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("adds a link that opens in a new tab, safely, when there's an href", () => {
    render(
      <StatusMessage
        status={{ cls: "ok", text: "Live ✓", href: "https://site.example/a/" }}
      />,
    );
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "https://site.example/a/");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toMatch(/noopener/);
    expect(link.getAttribute("rel")).toMatch(/noreferrer/);
  });

  it("renders nothing without a status", () => {
    const { container } = render(<StatusMessage status={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
