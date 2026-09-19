/** Shown when the site is login-gated, so Patr can't verify it's live. */
export const SUBSCRIBERS_ONLY_NOTE =
  "Subscribers-only site: Patr can't check that this edition is live — confirm it's deployed before sending.";

/**
 * Turn a /api/check-deployment response into the UI's deploy state.
 *
 * email_only: no site, so nothing to check. subscribers_only: the site is
 * behind a login, so liveness can't be checked (live is null, not false) and
 * the user has to confirm the deploy themselves. Otherwise live is the result
 * of an anonymous fetch of the edition's URL.
 */
export function deployStateFromCheck(d) {
  const gitAvailable = d.git_available ?? true;
  if (d.email_only) {
    return {
      emailOnly: true,
      subscribersOnly: false,
      deploymentLive: false,
      gitAvailable,
      status: null,
    };
  }
  if (d.subscribers_only) {
    return {
      emailOnly: false,
      subscribersOnly: true,
      deploymentLive: false,
      gitAvailable,
      status: { cls: "info", text: SUBSCRIBERS_ONLY_NOTE },
    };
  }
  return {
    emailOnly: false,
    subscribersOnly: false,
    deploymentLive: d.live,
    gitAvailable,
    status: d.live
      ? null
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
