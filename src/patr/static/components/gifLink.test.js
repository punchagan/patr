import { describe, it, expect } from "vitest";
import { isGifLink } from "./EditorPanel";

describe("isGifLink", () => {
  it("recognizes a Tenor share-page link", () => {
    expect(isGifLink("https://tenor.com/view/cat-gif-12345")).toBe(true);
  });

  it("recognizes a Tenor media subdomain link", () => {
    expect(isGifLink("https://media.tenor.com/abc.gif")).toBe(true);
  });

  it("recognizes a Giphy link", () => {
    expect(isGifLink("https://giphy.com/gifs/cat-12345")).toBe(true);
  });

  it("rejects an unrelated URL", () => {
    expect(isGifLink("https://example.com/cat.gif")).toBe(false);
  });

  it("rejects a lookalike domain", () => {
    expect(isGifLink("https://eviltenor.com/cat.gif")).toBe(false);
  });

  it("rejects plain (non-URL) pasted text", () => {
    expect(isGifLink("just some regular pasted text")).toBe(false);
  });

  it("rejects a non-http(s) URL", () => {
    expect(isGifLink("javascript:alert(1)")).toBe(false);
  });
});
