/**
 * Markdown link to an edition, for pasting into another edition's intro or
 * body. The path is root-relative, with no domain, so the link keeps working
 * on the site if its domain ever changes; Patr makes it absolute when the
 * email is built. Brackets and backslashes in the title are escaped so they
 * can't end the link text early.
 */
export function editionLinkMarkdown({ title, slug }) {
  const text = title.replace(/[\\[\]]/g, "\\$&");
  return `[${text}](/newsletter/${slug}/)`;
}
