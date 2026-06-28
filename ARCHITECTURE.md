# SpotyBox Architecture

Design rationale, research findings, and decisions for the spoty-rfid v2 rewrite.
This document exists so the project can be picked up later without re-deriving
the "why" behind each choice.

## What this is

A standalone, single-purpose appliance: an RFID-triggered Spotify player for
one non-technical user ("granny box"). Tap a tag → a playlist/album/track plays
on a Spotify Connect speaker the box itself hosts. All runtime control is via a
Telegram bot. A minimal web portal exists only for build-time setup and
connectivity recovery.

This is **not** infrastructure. There is no GitOps, no fleet, no declarative
provisioning. It is one box, configured through interfaces a remote helper can
use over the phone. Every design choice below follows from that.

## The core problem being solved

The original spoty-rfid suffered "frequent re-authentication." Root causes,
confirmed against current Spotify behavior:

1. It used `http://localhost` as the OAuth redirect. Spotify deprecated plain
   HTTP redirects in Feb 2025, allowing only loopback **literals** like
   `http://127.0.0.1`. `localhost` is rejected.
2. It relied on spotipy's default `.cache` file, which is easily lost or
   invalidated. Losing it forces a full re-auth.

The fix: Authorization Code flow with the redirect URI `http://127.0.0.1:8080/callback`,
and the token (including the non-expiring refresh token) persisted in SQLite via
a custom cache handler. Authorize once; spotipy refreshes transparently forever
after unless the grant is revoked.

## Spotify developer landscape (findings)

Researched because the platform changed substantially and the box's viability
depends on it.

- **Feb 2025:** Implicit grant deprecated; plain-HTTP redirect URIs dropped
  except loopback literals. → We use Auth Code + `http://127.0.0.1:8080/callback`.
- **Apr/May 2025:** Extended quota now requires a registered business + 250k
  MAU. Irrelevant for personal use, but it means the box lives permanently in
  **Development Mode**.
- **Feb 2026:** Development Mode now requires **Spotify Premium**, allows **one
  Client ID** and **up to 5 authorized users**, and exposes a reduced endpoint
  set. Crucially, **all Player endpoints we use survived**: play, pause,
  next/previous, volume, shuffle, repeat, devices, playback state, transfer.

Implication: the box works fine as a personal-use Development Mode app on
Premium, with up to 5 household accounts added in the dashboard. Spotify warns
Development Mode "should not be relied on as a foundation for a business" and
keeps evolving the model — so the tag→URI store is kept portable (plain SQLite)
in case the playback backend must change later.

## Two separate Spotify logins (critical to understand)

There are **two independent Spotify authentications**, with **two separate
caches**. Conflating them causes confusion about the `.cache` file.

| | Control plane (this app) | Playback device (librespot) |
|---|---|---|
| Role | Sends play/pause/etc via Web API | Is the actual speaker |
| Auth | Our app's Client ID, Auth Code flow | Spotify's desktop Client ID, OAuth |
| Redirect | `http://127.0.0.1:8080/callback` | `http://127.0.0.1`, `--oauth-port 0` |
| Token store | SQLite (`store.db`) | librespot's own cache dir |

They do not share state. Moving the spotipy token into SQLite has no effect on
librespot.

### librespot specifics (findings)

- Username/password login was **removed in v0.5** and no longer works. Only
  OAuth, access token, or zeroconf discovery remain. Premium required.
- A raw OAuth access token expires after ~1h. With caching enabled, librespot
  upgrades it into reusable credentials so it does not re-auth hourly. **Caching
  must be enabled.**
- Headless OAuth: `librespot --cache DIR --enable-oauth --oauth-port 0`. It
  prints a URL; approve in any browser; when the final redirect to
  `http://127.0.0.1/login?code=...` fails to load, paste that whole URL back
  into the waiting prompt. One time; the credentials blob is then cached.
- Why librespot gets its own OAuth (not just zeroconf): zeroconf needs an
  already-authenticated client on the same broadcast domain and won't cross
  VLANs; a box with no cached creds won't appear in `/me/player/devices` for the
  control plane to target. Direct OAuth makes the box a self-authenticating
  Connect device on every boot. Zeroconf stays enabled as a convenience.

## Configuration model

**SQLite is the source of truth.** This is a granny box with no SSH/env-file
access in the field; everything must be configurable through an interface.
Environment variables are an optional first-boot *seed* only — the portal's
saved values are authoritative.

(Note: an earlier iteration used env-first/SQLite-fallback for a GitOps context.
That was explicitly reversed once the project was scoped as a standalone box.
Do not reintroduce env-priority.)

### What lives where

- **SQLite (`store.db`), source of truth:**
  - Spotify token (refresh + access) — written at runtime by `/auth`
  - Tag → URI bindings — the core data, edited constantly at runtime
  - Owner chat IDs — set by trust-on-first-use `/start`
  - Preferred device ID — set by `/setdevice`
  - Telegram token, Spotify client ID/secret — written by the portal
  - UI language (`language`, default English) — chosen in the portal; drives
    both the portal and the Telegram bot via `i18n.Translator`
  - Tunables (ack timeout, etc.)
- **Env vars (optional seed):** same keys, read only if SQLite lacks them.

`store.db` runs as a dedicated user, chmod 600. Not encrypted at rest, which is
acceptable for a single-purpose home device. (A passphrase would reintroduce a
"how does granny enter it at boot" problem and is deliberately avoided.)

## Two interfaces, clear boundary

### Telegram bot — the native runtime interface
Everything for running the box: `/auth` (Spotify account authorization — open the
link, approve, paste back the `?code=...` redirect URL; a wrong paste is caught
and explained), tag bind/rebind/unbind (binding is a two-step prompt: name then
URI; rebind offers the current name as default), `/list`, `/play` (test playback
directly), `/devices`, `/setdevice`, `/status`. Telegram authenticates implicitly
(only allowlisted chats control the box), so no additional auth is needed.

### Web portal — build-time setup + connectivity recovery only
Carries exactly the things that either bootstrap connectivity or are awkward
build-time credentials:
- Wi-Fi (SSID/password)
- Telegram bot token
- Spotify client ID + secret, with a link to the Spotify dashboard and the exact
  loopback redirect URI to register

Both credentials are **validated before saving** — the Telegram token via the
`getMe` API, the Spotify ID/secret via the Client Credentials grant. A value
Telegram/Spotify actively rejects is refused with a clear message; if the check
can't reach the network (offline AP setup) it's saved anyway rather than block
configuration. Saved fields are pre-filled when the portal reloads.

The portal is **not** up during normal operation. Spotify *account* auth is NOT
in the portal — that's `/auth` in the bot (a click, no secret pasted). Spotify
*app credentials* ARE in the portal, so someone other than the original builder
can rebuild the box without re-imaging.

## Startup & recovery decision tree

The supervisor (`main.py`) owns the asyncio loop directly — **not**
python-telegram-bot — because the bot may be the very thing that's broken, so it
cannot be what bootstraps everything else. On every boot, and again whenever the
portal saves a value:

1. **No internet** → raise AP + portal (Wi-Fi form). Re-evaluate on connect.
2. **No Telegram token** → portal on LAN (can't start the bot; nothing to greet).
3. **Token present** → start the bot (the bot starts on the **token alone** —
   missing Spotify is a normal, recoverable state, not a setup blocker).
   - **No owner yet** → portal up; instruct to `/start` to claim ownership.
   - **Spotify creds missing** → portal auto-raises **and** the bot (which is up)
     messages the portal link. Both surfaces, so remote help works regardless of
     where you're looking.
   - **Configured & healthy** → send a Telegram hello with an inline "✅ I'm
     here" button; wait `ACK_TIMEOUT` (default 60s).
     - Tapped → portal down, run normally.
     - Send **fails** (token revoked/bot deleted/Telegram unreachable) **or** no
       tap in time → treat the **bot connection as lost** → portal on LAN (no AP;
       the network itself is fine).

Rationale for the health probe: the user's actual failure mode is *losing the
bot connection*. A healthy box always gets the tap, so it never lingers in the
portal. "No tap → portal" is deliberately literal per the owner's instruction;
the portal binds the LAN only (no broadcast), so it isn't externally exposed.

## Module map

```
spotyrfid/
  main.py      Supervisor: owns the loop, runs the decision tree, lifecycle.
  bot.py       Telegram control plane: commands, conversational binding flows,
               owner allowlist (trust-on-first-use), startup hello + ack.
  spotify.py   Web API playback control + SQLiteCacheHandler (the reauth fix);
               credential + auth-code validation helpers.
  rfid.py      USB-HID keyboard-wedge reader in a thread -> asyncio queue.
  probe.py     Standalone RFID diagnostic (python -m spotyrfid.probe).
  wifi.py      NetworkManager (nmcli) helpers + AP fallback.
  web.py       Portal: Wi-Fi + token + Spotify-creds forms; OAuth callback;
               language selector.
  store.py     SQLite: tags, token, config, owners. Source of truth.
  config.py    Config dataclass; SQLite-primary, env-seed loader.
  i18n.py      Translation catalog + Translator (reads `language` from SQLite).
```

### Control tags
Besides URI tags, a tag's value may be a reserved keyword: `play`, `pause`,
`playpause`, `next`, `prev`, `volup`, `voldown`. Anything else is treated as a
Spotify URI. Bind via `/rebind <uid>` then send the keyword.

### RFID reader assumption
Assumes a keyboard-wedge USB reader (types digits + Enter). The device is opened
**unbuffered** so each read is one HID report — buffering concatenates reports
and corrupts the keycode positions — and the keycode is found by scanning from
byte 2 (tolerating an optional report-ID prefix). `python -m spotyrfid.probe`
identifies the device and shows decoded UIDs; a udev `SYMLINK+="rfid"` pins a
stable path. For a GPIO module (e.g. MFRC522), only `RfidReader._run` needs
replacing — it just pushes a UID string onto the queue; everything downstream is
reader-agnostic.

## Open items / future
- `librespot.service` shipped as a real unit file (see install script + README).
- Optional `/health` command to flag when the pinned device disappears.
- Possible MFRC522/SPI reader variant.
- If Spotify ever pulls personal playback control, swap the backend (the
  tag→URI store is intentionally backend-agnostic).

## Hard constraints to remember
- Spotify redirect URI must be a loopback literal (`http://127.0.0.1:8080/callback`),
  never `localhost`.
- Spotify Premium required (both for the Web API control and for librespot).
- Max 5 authorized users per Client ID; add each in the dashboard.
- librespot caching must be enabled or it re-auths constantly.
- Do not reintroduce env-priority config — SQLite is source of truth here.
