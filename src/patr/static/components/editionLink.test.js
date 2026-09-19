import { describe, it, expect } from "vitest";
import { editionLinkMarkdown } from "./editionLink";

describe("editionLinkMarkdown", () => {
  it("is a markdown link to the edition's root-relative path, with no domain", () => {
    expect(
      editionLinkMarkdown({ title: "Spring Art Gallery", slug: "spring-art" }),
    ).toBe("[Spring Art Gallery](/newsletter/spring-art/)");
  });

  it("escapes brackets and backslashes so the title can't break the link", () => {
    expect(
      editionLinkMarkdown({ title: "Notes [draft] a\\b", slug: "notes" }),
    ).toBe("[Notes \\[draft\\] a\\\\b](/newsletter/notes/)");
  });

  it("leaves other punctuation, including quotes and unicode, alone", () => {
    expect(
      editionLinkMarkdown({ title: "It's “quoted” — नमस्ते", slug: "q" }),
    ).toBe("[It's “quoted” — नमस्ते](/newsletter/q/)");
  });
});
