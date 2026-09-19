/** Shown when the site is login-gated, so Patr can't verify it's live. */
export const SUBSCRIBERS_ONLY_NOTE =
  "Subscribers-only site: Patr can't check that this edition is live — confirm it's deployed before sending.";

/** `status` with an `href` added, if there's a url to link to. */
function withLink(status, url) {
  return url ? { ...status, href: url } : status;
}

/**
 * Status-bar message confirming a publish. Carries a link to the edition's
 * page (when the url is known) so the writer can go and look at it.
 */
export function publishedStatus(url) {
  return withLink({ cls: "ok", text: "Published ✓" }, url);
}

/**
 * Turn a /api/check-deployment response into the UI's deploy state.
 *
 * email_only: no site, so nothing to check. subscribers_only: the site is
 * behind a login, so liveness can't be checked (live is null, not false) and
 * the user has to confirm the deploy themselves. Otherwise live is the result
 * of an anonymous fetch of the edition's URL. The status carries the
 * edition's url as `href` wherever there's something to look at (live, or
 * unverifiable), and not when it's known to be missing. `siteUrl` is the
 * edition's page url, kept for messages built later (e.g. after Publish).
 */
export function deployStateFromCheck(d) {
  const gitAvailable = d.git_available ?? true;
  if (d.email_only) {
    return {
      emailOnly: true,
      subscribersOnly: false,
      deploymentLive: false,
      gitAvailable,
      siteUrl: null,
      status: null,
    };
  }
  if (d.subscribers_only) {
    return {
      emailOnly: false,
      subscribersOnly: true,
      deploymentLive: false,
      gitAvailable,
      siteUrl: d.url ?? null,
      status: withLink({ cls: "info", text: SUBSCRIBERS_ONLY_NOTE }, d.url),
    };
  }
  return {
    emailOnly: false,
    subscribersOnly: false,
    deploymentLive: d.live,
    gitAvailable,
    siteUrl: d.url ?? null,
    status: d.live
      ? withLink({ cls: "ok", text: "Live ✓" }, d.url)
      : {
          cls: "warn",
          text: d.reason ? `Not published: ${d.reason}` : "Not published yet",
        },
  };
}

/**
 * Whether "Send All" is enabled. A live site is required on a normal setup;
 * email-only has no site, and subscribers-only can't be verified (the user is
 * reminded to check), so neither needs deploymentLive. Sending always needs a
 * contacts sheet and a connected Gmail.
 */
export function canSend({
  emailOnly,
  subscribersOnly,
  deploymentLive,
  hasSheetId,
  gmailConnected,
}) {
  return Boolean(
    (emailOnly || subscribersOnly || deploymentLive) &&
    hasSheetId &&
    gmailConnected,
  );
}
