# Minting a Brightspace API token with Claude-in-Chrome

The seamless auth path: no Playwright, no venv, no OAuth registration.
Brightspace mints a ~1h full-scope JWT to any logged-in browser session via
its own first-party endpoints; we ask the user's real Chrome tab for one.

## Prerequisites

- Claude Chrome extension connected, with **JavaScript permission granted
  for the Brightspace domain** (the user enables this in the extension's
  site settings — a `Permission denied for JavaScript execution` error
  means it's off).
- A tab on `https://<host>/d2l/home` where the user is **logged in**. If
  navigation bounces to the SSO page, ask the user to complete login
  (SSO + Duo) in that tab — never type credentials for them.

## Steps (for Claude)

1. `tabs_context_mcp` → navigate a tab to `https://<host>/d2l/home`.
   Confirm it stays on `/d2l/home` (logged in) rather than redirecting to
   SSO.
2. `javascript_tool` on that tab:

```js
const x = await fetch('/d2l/lp/auth/xsrf-tokens',
    {credentials: 'same-origin'}).then(r => r.json());
if (!x.referrerToken) throw new Error(
    'empty referrerToken — the user is not actually logged in');
const t = await fetch('/d2l/lp/auth/oauth2/token', {
  method: 'POST', credentials: 'same-origin',
  headers: {'X-Csrf-Token': x.referrerToken,
            'Content-Type': 'application/x-www-form-urlencoded'},
  body: 'scope=*:*:*'
}).then(r => r.json());
t.access_token
```

3. Cache it for the scripts (survives ~50 min; repeat the mint when it
   expires):

```bash
printf '%s' '<access_token>' | python3 scripts/bsapi.py save-token
python3 scripts/bsapi.py whoami   # must print the user's name
```

For a non-default tenant set `BRIGHTSPACE_HOST=<host>` on both commands.

## Handling notes

- The token grants the user's full LMS permissions for ~1h. Keep it out of
  files other than the mode-600 cache; don't echo it beyond what the
  save-token pipe requires.
- `save-token` immediately verifies with `whoami`, so a bad paste fails
  loudly.
- Known trap: with an expired login the XSRF endpoint returns **HTTP 200
  with an empty `referrerToken`** — that's a "please log in again", not a
  server error.
- The same trick works on any D2L tenant (test tenant included) — it's the
  vu_brightspace session→JWT flow executed inside the user's own browser
  instead of a Playwright profile.
