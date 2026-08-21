# Install footprint & auth — what's actually required

Short version: **Python 3 + one pip package (`requests`, auto-installed).
No Playwright required. No OAuth app. No admin.** Everything that talks to
Brightspace is plain Python over HTTPS; a browser is needed only to
*obtain a session*, and only occasionally for the handful of UI-only
operations.

## Dependency footprint

| Component | Needed for | Notes |
|---|---|---|
| Python 3.9+ | everything | ships on macOS; the runtime Cowork/Claude Code already has |
| `requests` | all API calls | auto-installed on first run (PEP-668-aware) |
| stdlib only otherwise | qti/rubric/manifest/grading | json, zipfile, argparse, uuid, re, xml — no third-party |
| a logged-in browser | getting a token | ANY browser; see auth paths below |
| Claude-in-Chrome extension | UI-only tail + easiest token mint | optional; only for rubric creation, quiz pools, announcements-while-the-API-bug-lasts |
| Playwright | **optional** headless/scheduled auth only | not needed for interactive use — see "Do we need Playwright?" |

That's it. No Node, no browser drivers for the normal path, nothing to
compile.

## Auth paths, best first (all produce the same ~1h JWT)

Brightspace mints a full-scope token to any logged-in session via its own
first-party endpoints; we just need the session. Four ways to hand it
over — pick by environment:

### 1. Paste a token (zero extra tooling, works everywhere)
The user opens their logged-in Brightspace tab → DevTools Console → runs:
```js
const x = await fetch('/d2l/lp/auth/xsrf-tokens',{credentials:'same-origin'}).then(r=>r.json());
(await fetch('/d2l/lp/auth/oauth2/token',{method:'POST',credentials:'same-origin',
  headers:{'X-Csrf-Token':x.referrerToken,'Content-Type':'application/x-www-form-urlencoded'},
  body:'scope=*:*:*'}).then(r=>r.json())).access_token
```
Claude then writes that token to a scratch file and feeds it in via stdin —
`python3 bsapi.py save-token < /path/to/tok && rm /path/to/tok`. **Never
inline the token as a shell argument** (`printf '%s' '<token>' | ...`): it
lands in shell history and argv, and permission classifiers block
credential-shaped arguments outright.
No Playwright, no extension, no cookie decryption. Token lasts ~1h; repeat
when it expires. **This is the universal fallback.**

### 2. Claude-in-Chrome mints it (best in Cowork / when the extension is on)
Claude runs the same fetch in the user's tab and caches the result — fully
automated, nothing for the user to paste. Steps: `references/chrome-auth.md`.
Needs the extension with JS permission on the Brightspace domain.

In Claude Code auto-mode the classifier may block the scripted fetch —
**non-deterministically**, so a clean run is no guarantee. Fix it with an
`ask` permission rule (`mcp__Claude_Browser__javascript_tool`), which
overrides the classifier and turns the silent denial into a prompt; see the
**Failure modes** section of `references/chrome-auth.md`. Never route the
mint through a different browser surface to dodge a denial. Otherwise use
path 1.

### 3. Import cookies from the browser profile (`import-cookies`)
`python3 bsapi.py import-cookies safari|firefox|edge|brave` reads the
session cookie straight from the browser profile — pure code, durable for
days. **Caveat:** Google **Chrome v127+ uses App-Bound Encryption**, which
blocks profile cookie reads (fails with "Unable to get key"), so this path
only works in a browser *without* ABE where the user is logged in to
Brightspace. Safari and Firefox work; Chrome generally does not. Installs
`browser_cookie3` on demand. The command refuses to overwrite an existing
session unless it actually captured `d2lSessionVal`.

### 4. Playwright login (headless/scheduled only)
`approaches/playwright-skill/scripts/login.py` opens a window, the user
does SSO+Duo once, and the saved `storage_state.json` mints tokens for
days–weeks unattended. The only path that survives with **no human and no
browser open** — so it's the right tool for cron/scheduled runs, and
nothing else.

All four write to the same place; the scripts try env token → cached token
→ `storage_state.json` cookies automatically.

## Do we REALLY need Playwright?

**No — not for interactive use.** Paths 1–3 cover a person working with
Claude (Cowork, Claude Code, or the web), with path 1 needing literally
nothing beyond a browser the user already has open. Playwright earns its
place in exactly one scenario: **unattended/scheduled** runs (e.g. a
nightly "who hasn't submitted" job) where no one is present to paste a
token or approve a mint, and a saved cookie jar must refresh itself. If
you never run headless, you can delete Playwright from the picture.

## Can this run in Claude Cowork (Desktop app)?

**Generally no — and the failure is network, not auth.** Group testing
(issue #1) plus Anthropic's architecture docs settle it: Cowork executes
skill code in a **cloud VM**, and all of that VM's outbound traffic must
pass an egress-allowlist proxy. The Brightspace tenant is on the public
internet, but it is not on the allowlist, so every API call fails at the
network level no matter how valid the token is. (Cowork's in-app browser
is exempt from the egress rules — it can log in to Brightspace fine —
which is why auth *looks* like it works right up until the first script
API call.) There is no user-level unblock; an Enterprise org admin can
allowlist the tenant host (Admin Console → Organization Settings →
Capabilities → Code Execution → Allow Network Egress, mode "All domains" —
a known bug ignores the extra-domains list in "Package managers only"
mode; new sessions only).

Run `python3 scripts/bsapi.py doctor` to prove which case you're in
(exit 2 = egress blocked, exit 3 = just stale auth). The reliable surface
is **Claude Code** — the terminal, or Claude Code inside the same Desktop
app — which executes on the user's machine with normal network access.
Everything in this skill is verified working there.
