# SpotyBox (spoty-rfid v2)

An RFID-triggered Spotify player, controlled entirely through a Telegram bot.
Tap a tag → a playlist/album/track plays on your chosen Spotify device. Unknown
tags, Spotify linking, and Wi-Fi setup are all handled conversationally via the
bot — no screen or keyboard needed on the box.

This is a rewrite of the original `spoty-rfid`, motivated by Spotify's
2025–2026 developer changes and the recurring re-authentication problem.

> See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full design rationale,
> research findings, and the reasoning behind each decision.

## Why the rewrite — and why auth was breaking

Spotify tightened developer access considerably:

- **Feb 2025:** the implicit grant was deprecated, and plain-HTTP redirect URIs
  were dropped — **except loopback literals** like `http://127.0.0.1`.
  `http://localhost` is no longer valid.
- **Apr/May 2025:** extended quota now needs a registered business + 250k MAU.
  Irrelevant for personal use, but it means you stay in **Development Mode**.
- **Feb 2026:** Development Mode now **requires Spotify Premium**, allows **one
  Client ID** and **up to 5 authorized users**, and exposes a reduced endpoint
  set. Crucially, **all Player endpoints we use survived** (play, pause,
  next/prev, volume, shuffle, repeat, devices, playback state).

**The actual cause of "frequent reauth":** the Authorization Code flow issues a
`refresh_token` that does not expire. The original box relied on spotipy's
`.cache` file, which is easily lost or invalidated — and on `localhost`, which
is now rejected. v2 fixes both:

1. Redirect URI is `http://127.0.0.1:8080/callback` (loopback literal).
2. The token (incl. refresh token) is persisted in **SQLite**, not a cache file.

You authorize **once**. spotipy refreshes the access token transparently
forever after, unless you revoke the grant in your Spotify account.

> ⚠️ Spotify says Development Mode "should not be relied on as a foundation for
> building or scaling a business" and continues to evolve the model. For a
> household box that's fine, but the tag→URI store is plain SQLite so you can
> swap the playback backend (e.g. to go-librespot) later if needed.

## Architecture

```
spotyrfid/
  main.py      orchestrator — owns the asyncio loop directly (not PTB)
  bot.py       Telegram control plane (commands + conversational flows)
  spotify.py   playback control + SQLiteCacheHandler (the reauth fix)
  rfid.py      USB-HID reader thread -> asyncio queue
  probe.py     standalone RFID diagnostic (python -m spotyrfid.probe)
  wifi.py      NetworkManager (nmcli) helpers + AP fallback
  web.py       aiohttp: portal (Wi-Fi + setup) + OAuth callback catcher
  store.py     SQLite: tag bindings, token, config — source of truth
  config.py    config loader (SQLite-primary, env as first-boot seed)
  i18n.py      translation catalog (English + German) + Translator
```

The four requested capabilities:

1. **Wi-Fi bootstrap / AP fallback** — on boot, if there's no internet within
   30 s, the box raises a `SpotyBox` hotspot. Join it with a phone, open any
   page (captive), submit your home SSID + password. NetworkManager stores the
   profile and auto-reconnects on future boots.
2. **Spotify auth via bot** — `/auth` sends an authorize URL. Open it, click
   **Agree**, then paste back the URL you're redirected to — the one containing
   `?code=...`, **not** the authorize link itself (the bot warns you if you paste
   the wrong one). Token saved to SQLite.
3. **Unknown tag → name + URI** — scanning an unbound tag DMs you. It first asks
   for a **name/alias** (or send `-` to skip), then for a `spotify:` URI or an
   `open.spotify.com` link (incl. `intl-xx` links) to bind.
4. **Reset/rebind a tag** — `/rebind <uid>` asks for a new name (send `-` to keep
   the current one), then a new URI; `/unbind <uid>` to remove.

You can test playback at any time with **`/play <uri|link>`** (or bare `/play`
to resume) — it triggers the exact path a tag uses and reports the precise
Spotify error if something's wrong, so it's the fastest way to tell an RFID
problem apart from a Spotify/device one.

### Control tags (kept from the original)

Bind a tag's value to one of these reserved keywords instead of a URI:
`play`, `pause`, `playpause`, `next`, `prev`, `volup`, `voldown`. To make a
control tag, `/rebind <uid>` then send e.g. `next` — or insert directly into the
`tags` table. Everything else is treated as a Spotify URI.

## Setup

### 1. Spotify app
1. https://developer.spotify.com/dashboard → **Create app**.
2. Add redirect URI **exactly**: `http://127.0.0.1:8080/callback`.
3. Note the Client ID and Client Secret.
4. Under the app's user-management, add each household member's Spotify account
   (max 5). All must be **Premium**.

### 2. Telegram bot
Message **@BotFather** → `/newbot` → copy the token.

### 3. Install on the box (automated)

Copy this repo to the box and run the installer as root:

```bash
sudo ./install.sh
```

It creates the service user, directories, Python venv, both systemd units
(`spoty-rfid` and, if librespot is present, `librespot`), the udev rule
template, and an optional env seed file. It's idempotent — re-run to update code
without clobbering your secrets or database. See the script's final output for
the remaining manual steps (RFID reader IDs, one-time librespot OAuth).

The sections below document what the installer does, for reference or manual
setup.

### 4. RFID reader permissions & stable device path

Find your reader and grant the service user access. The probe tool lists every
HID device with its vendor/product IDs:

```bash
python -m spotyrfid.probe            # list candidate /dev/hidraw* + vid/pid/name
python -m spotyrfid.probe /dev/hidrawN   # watch one; tap a chip to see decoded UID
```

Then install the udev rule with your reader's real IDs. The rule both grants the
`plugdev` group read access **and** creates a stable `/dev/rfid` symlink, so you
don't depend on the `hidrawN` number (which can change across reboots/replugs):

```bash
lsusb   # find your reader's ID, e.g. 16c0:27db
sudo cp 50-spotybox-rfid.rules /etc/udev/rules.d/
sudo nano /etc/udev/rules.d/50-spotybox-rfid.rules   # set idVendor/idProduct
sudo udevadm control --reload-rules && sudo udevadm trigger
```

The shipped rule adds `SYMLINK+="rfid"`; set `RFID_DEVICE=/dev/rfid` in the env
file so the box always finds the reader regardless of enumeration order.

### 5. Service
```bash
sudo cp spoty-rfid.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now spoty-rfid
```

### 6. First run
1. Set up and authenticate the librespot speaker (see "The playback backend"
   below) — do this first so the box has a device to play to.
2. Message your bot `/start` (first chat to do so becomes the owner).
3. `/auth` → open the URL, approve, paste the **redirected** URL back (the one
   with `?code=...`).
4. `/devices` → confirm **SpotyBox** appears, then `/setdevice <id>` to pin it.
5. `/play <uri|link>` → confirm audio actually plays before involving tags.
6. `/status` to confirm everything's linked.
7. Tap a new tag → give it a name, then a Spotify link to bind it. Done.

## Startup behavior & the setup portal

The box supervises itself. On every boot it walks this decision tree:

1. **No internet** → raises the `SpotyBox` access point *and* the setup portal
   (with the Wi-Fi form). Join the AP, submit your home Wi-Fi, and it
   re-evaluates.
2. **Not configured** (missing Telegram token or Spotify credentials) → setup
   portal on the box's LAN IP, no AP. Enter what's missing.
3. **No owner yet** → portal stays up with instructions to message the bot and
   send `/start` to claim ownership.
4. **Configured & healthy** → the box sends a Telegram hello with an inline
   **"✅ I'm here"** button and waits `ACK_TIMEOUT` seconds (default 60).
   - You tap it → portal goes down, box runs normally.
   - The send **fails** (bot token revoked, bot deleted, Telegram unreachable)
     **or** you don't tap in time → the box treats the **bot connection as
     lost** and brings the setup portal back up on the LAN so you can fix the
     token. (No AP in this case — the network itself is fine.)

This matches the intended failure mode: **losing the bot connection** drops the
box into recovery without needing a screen or SSH. A healthy box always gets
your tap, so it never lingers in the portal.

### Language

The setup portal has a language selector (English and German) at the top. The
choice is saved to SQLite and applies to **both** the portal and every Telegram
bot message immediately — no restart needed. Adding a language is a single block
in `spotyrfid/i18n.py`; missing keys fall back to English, so partial
translations are safe.

> The 60s no-tap trigger is deliberately literal per the design. If you're
> often away from your phone at boot, raise `ACK_TIMEOUT`, or remember that the
> portal here only binds the LAN (it does not broadcast an AP), so it's not
> externally exposed.

### Where secrets live

**SQLite (`store.db`) is the source of truth.** Configuration is read
**SQLite-first, env as a first-boot seed**:

- The portal writes the Telegram token and Spotify credentials into the SQLite
  `config` table. These are authoritative — once saved, they always win.
- Environment variables in the systemd `EnvironmentFile` (`.env`) are read only
  when SQLite has no value yet, so you *can* pre-seed a fresh box. Placeholder
  values (e.g. the ones in `spoty-rfid.env.example`) are ignored.

This precedence is deliberate: an env value that outranked the portal would let a
stale `.env` shadow the token you just saved and trap the box in setup mode. The
portal also **validates** what you enter before saving — the Telegram token via
`getMe` and the Spotify client ID/secret via the Client Credentials grant — so a
typo is rejected immediately instead of failing later. After a save, the
supervisor re-reads config and restarts the bot automatically — no manual
restart.



This is the part that confuses everyone, so read carefully: **there are two
completely separate Spotify logins in this system, with two separate caches.**

| | Control plane (this app) | Playback device (librespot) |
|---|---|---|
| What it does | Sends play/pause/next via Web API | Is the actual speaker |
| Auth | Your app's Client ID (Auth Code flow) | Spotify's desktop Client ID (OAuth) |
| Redirect | `http://127.0.0.1:8080/callback` | `http://127.0.0.1` (port 0, headless) |
| Token store | SQLite (`store.db`) | librespot's own cache dir |

They do **not** share a cache. Moving this app's token into SQLite has no effect
on librespot, and vice versa. You authenticate each one once.

### Why librespot needs its own OAuth (not just zeroconf)

Zeroconf discovery is convenient — an authenticated phone on the LAN can hand
credentials to the box. But it has two failure modes that matter for an
appliance:

1. If no authenticated client has *ever* connected to the box, it has no cached
   credentials and won't appear in `/me/player/devices` — so the control plane
   has nothing to transfer playback to.
2. Zeroconf only works within one broadcast domain. If the box sits on an
   isolated VLAN, discovery won't reach it.

So we authenticate librespot **directly** with its own OAuth + cache. The box
becomes a self-authenticating Spotify Connect device that appears in
`/me/player/devices` on every boot, regardless of what else is on the network.
Keep zeroconf enabled too — it's a harmless convenience on top.

> Note: librespot username/password login was removed in v0.5 and no longer
> works. OAuth, access token, or zeroconf are the only options. Premium is
> required (librespot will not work on free accounts).

### One-time librespot OAuth (headless)

Caching MUST be enabled or you'll re-auth constantly. Run once, interactively:

```bash
sudo install -d -o spotybox -g spotybox /var/lib/spotybox/librespot
sudo -u spotybox librespot \
  --name "SpotyBox" \
  --cache /var/lib/spotybox/librespot \
  --enable-oauth \
  --oauth-port 0 \
  --bitrate 320 \
  --device-type speaker \
  --backend alsa
```

`--oauth-port 0` disables the local redirect server (right choice for a headless
box). librespot prints a URL — open it in a browser on your laptop/phone,
approve, and when the final redirect to `http://127.0.0.1/login?code=...` fails
to load (it will — nothing is listening), copy that **entire URL** from the
address bar back into the waiting librespot prompt. Done. The credentials blob
is now cached in `/var/lib/spotybox/librespot` and reused on every future start.

### Run librespot as a service

Either use **Raspotify** (Debian package that wraps librespot) or a unit:

```ini
# /etc/systemd/system/librespot.service
[Unit]
Description=librespot Spotify Connect speaker
After=network-online.target
Wants=network-online.target

[Service]
User=spotybox
ExecStart=/usr/bin/librespot \
  --name "SpotyBox" \
  --cache /var/lib/spotybox/librespot \
  --enable-oauth --oauth-port 0 \
  --bitrate 320 --device-type speaker --backend alsa
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

After the one-time auth, the cached blob means it starts non-interactively.

**Raspotify equivalent** — edit `/etc/raspotify/conf`:
```
LIBRESPOT_NAME="SpotyBox"
LIBRESPOT_CACHE="/var/lib/spotybox/librespot"
LIBRESPOT_ENABLE_OAUTH=on
LIBRESPOT_OAUTH_PORT=0
# Do NOT set LIBRESPOT_USERNAME / LIBRESPOT_PASSWORD — removed since v0.5.
# Leave discovery enabled (don't set LIBRESPOT_DISABLE_DISCOVERY).
```

### Wiring it to the control plane

1. Start librespot (above). It logs in via its cached OAuth blob.
2. In the bot: `/devices` → you should see **SpotyBox** in the list.
3. `/setdevice <its-id>` to pin playback to it (persists across reboots).
4. Now tapping a tag plays to your box even if no phone is around.

If `/devices` shows nothing, librespot isn't logged in — check its journal
(`journalctl -u librespot -f`) and re-run the one-time OAuth.

## Notes on the RFID reader

`rfid.py` assumes a "keyboard-wedge" USB reader (types digits + Enter). It opens
the device **unbuffered** (`buffering=0`) so each read returns exactly one HID
report — a buffered reader concatenates reports and scrambles the keycode
positions — and locates the keycode by scanning from byte 2, which tolerates an
optional report-ID prefix. Set `LOG_LEVEL=DEBUG` to log every raw report.

Debugging a reader that registers no taps:

```bash
sudo systemctl stop spoty-rfid                 # free the device
python -m spotyrfid.probe                       # which /dev/hidrawN is it?
python -m spotyrfid.probe /dev/hidrawN          # tap a chip; confirm a stable UID
```

If the decoded UID differs from what `/list` shows for a tag, just `/rebind` it.
Pin the device with the udev symlink (see step 4) so the path is stable.

If your reader presents differently (raw bytes, serial, or a Pi GPIO module like
MFRC522), replace `RfidReader._run` — it only needs to push a stable UID string
onto `self.queue`. Everything downstream is reader-agnostic.

## License

GPL-3.0 (inherited from the original project).
