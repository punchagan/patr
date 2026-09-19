import { describe, it, expect } from "vitest";
import { deployStateFromCheck, canSend, publishedStatus } from "./deployStatus";

describe("deployStateFromCheck", () => {
  it("email-only: no deploy check applies", () => {
    const s = deployStateFromCheck({ email_only: true, live: null });
    expect(s.emailOnly).toBe(true);
    expect(s.subscribersOnly).toBe(false);
    expect(s.status).toBeNull();
  });

  it("subscribers-only: liveness is unknown, so tell the user to check manually", () => {
    const s = deployStateFromCheck({
      subscribers_only: true,
      live: null,
      git_available: true,
    });
    expect(s.subscribersOnly).toBe(true);
    expect(s.emailOnly).toBe(false);
    expect(s.deploymentLive).toBe(false);
    expect(s.status.cls).toBe("info");
    expect(s.status.text).toMatch(/subscribers-only/i);
    expect(s.status.text).toMatch(/confirm|manual|check/i);
    // Not the "Not published" warning, which would be wrong here.
    expect(s.status.text).not.toMatch(/not published/i);
  });

  it("normal site, live: says so, with a link so the writer can go look", () => {
    const s = deployStateFromCheck({
      live: true,
      url: "https://site.example/newsletter/my-ed/",
    });
    expect(s.deploymentLive).toBe(true);
    expect(s.subscribersOnly).toBe(false);
    expect(s.status.cls).toBe("ok");
    expect(s.status.text).toMatch(/live/i);
    expect(s.status.href).toBe("https://site.example/newsletter/my-ed/");
  });

  it("normal site, live but no url known: no link", () => {
    expect(deployStateFromCheck({ live: true }).status.href).toBeUndefined();
  });

  it("subscribers-only note links to the edition's page too", () => {
    const s = deployStateFromCheck({
      subscribers_only: true,
      live: null,
      url: "https://site.example/newsletter/my-ed/",
    });
    expect(s.status.href).toBe("https://site.example/newsletter/my-ed/");
  });

  it("not-live warning has no link (there's nothing there to look at)", () => {
    const s = deployStateFromCheck({
      live: false,
      url: "https://site.example/newsletter/my-ed/",
    });
    expect(s.status.href).toBeUndefined();
  });

  it("email-only has no site to link to", () => {
    expect(deployStateFromCheck({ email_only: true }).status).toBeNull();
  });

  it("normal site, not live: warns, with the reason if there is one", () => {
    const s = deployStateFromCheck({ live: false, reason: "HTTP Error 404" });
    expect(s.deploymentLive).toBe(false);
    expect(s.status.cls).toBe("warn");
    expect(s.status.text).toBe("Not published: HTTP Error 404");
    expect(deployStateFromCheck({ live: false }).status.text).toBe(
      "Not published yet",
    );
  });

  it("defaults gitAvailable to true when the server doesn't say", () => {
    expect(deployStateFromCheck({ live: true }).gitAvailable).toBe(true);
    expect(
      deployStateFromCheck({ live: true, git_available: false }).gitAvailable,
    ).toBe(false);
  });
});

describe("canSend", () => {
  const ready = { hasSheetId: true, gmailConnected: true };

  it("needs a live site on a normal setup", () => {
    expect(canSend({ ...ready, deploymentLive: true })).toBe(true);
    expect(canSend({ ...ready, deploymentLive: false })).toBe(false);
  });

  it("doesn't need a live site for email-only or subscribers-only", () => {
    expect(canSend({ ...ready, emailOnly: true })).toBe(true);
    expect(canSend({ ...ready, subscribersOnly: true })).toBe(true);
  });

  it("always needs a contacts sheet and Gmail", () => {
    expect(
      canSend({
        subscribersOnly: true,
        hasSheetId: false,
        gmailConnected: true,
      }),
    ).toBe(false);
    expect(
      canSend({
        subscribersOnly: true,
        hasSheetId: true,
        gmailConnected: false,
      }),
    ).toBe(false);
  });
});

describe("publishedStatus", () => {
  it("confirms the publish and links to the page when the url is known", () => {
    const st = publishedStatus("https://site.example/newsletter/my-ed/");
    expect(st.cls).toBe("ok");
    expect(st.text).toBe("Published ✓");
    expect(st.href).toBe("https://site.example/newsletter/my-ed/");
  });

  it("has no link when the url isn't known", () => {
    expect(publishedStatus(null).href).toBeUndefined();
  });
});
