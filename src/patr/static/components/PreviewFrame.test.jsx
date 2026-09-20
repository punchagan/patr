import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import PreviewFrame from "./PreviewFrame";

function renderFrame(device) {
  render(
    <PreviewFrame slug="my-ed" viewMode="web" previewKey={0} device={device} />,
  );
  return screen.getByTitle(/preview/i);
}

describe("PreviewFrame", () => {
  it("shows the edition's preview route", () => {
    expect(renderFrame("desktop")).toHaveAttribute("src", "/preview/my-ed/web");
  });

  it("desktop fills the pane", () => {
    expect(renderFrame("desktop").style.width).toBe("100%");
  });

  it("phone is a fixed narrow frame, so the site renders its mobile layout", () => {
    expect(renderFrame("phone").style.width).toBe("390px");
  });

  it("tablet is a fixed frame too", () => {
    expect(renderFrame("tablet").style.width).toBe("768px");
  });
});
