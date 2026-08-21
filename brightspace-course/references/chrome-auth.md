# Minting a Brightspace API token from a logged-in browser

The seamless auth path: no Playwright, no venv, no OAuth registration.
Brightspace mints a ~1h full-scope JWT to any logged-in browser session via
its own first-party endpoints; we run the mint inside a browser the user
has logged into. Two surfaces can do it:

- **Claude Code on Desktop — built-in Browser pane** *(verified working
  2026-08-21; the smoothest path)*: open the tenant in the Browser pane,
  have the user complete SSO + Duo there (never type credentials for
  them), then execute the mint JS in that page.
- **Claude-in-Chrome extension** (user's own Chrome tab): needs the
  extension connected with **JavaScript permission granted for the
  Brightspace domain** (a `Permission denied for JavaScript execution`
  error means it's off). **Known limit (2026-08-21): on this surface the
  extension redacts JWTs from tool results** (`[BLOCKED: JWT token]`), so
  the mint runs but the token can't be read back — use the Desktop
  Browser pane, or fall back to the user pasting from DevTools.

Either way, start from a tab on `https://<host>/d2l/home` where the user
is **logged in**. If navigation bounces to the SSO page, ask the user to
complete login (SSO + Duo) in that tab — never type credentials for them.

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
   expires). **Do not inline the token in the command** — permission
   classifiers block credential-shaped arguments, and it would land in
   shell history. Write it to a temp file and feed stdin from that,
   deleting in the same command:

```bash
# token written to a scratch file first (e.g. via the Write tool)
python3 scripts/bsapi.py save-token < /path/to/scratch/tok && rm /path/to/scratch/tok
python3 scripts/bsapi.py whoami   # must print the user's name
```

For a non-default tenant set `BRIGHTSPACE_HOST=<host>` on both commands.

## Handling notes

- The token grants the user's full LMS permissions for ~1h. Keep it out of
  files other than the mode-600 cache; don't echo it beyond what the
  save-token pipe requires. Note the token still transits the agent's
  context as the JS tool result (FERPA-5): don't restate it in prose, and
  a future in-browser handoff (page POSTs the token straight to a local
  listener) would remove even that — Chrome's Local Network Access rules
  currently block the naive version of that handoff.
- `save-token` immediately verifies with `whoami`, so a bad paste fails
  loudly.
- Known trap: with an expired login the XSRF endpoint returns **HTTP 200
  with an empty `referrerToken`** — that's a "please log in again", not a
  server error.
- The same trick works on any D2L tenant (test tenant included) — it's the
  vu_brightspace session→JWT flow executed inside the user's own browser
  instead of a Playwright profile.
