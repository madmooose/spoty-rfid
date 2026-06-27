#!/usr/bin/env bash
#
# SpotyBox installer. Run as root on the target box (Raspberry Pi / Debian).
#
#   sudo ./install.sh
#
# Idempotent: safe to re-run to update code. It will NOT overwrite an existing
# secrets file or the runtime database.
#
set -euo pipefail

# ---- config (override via env) -------------------------------------------
APP_USER="${APP_USER:-spotybox}"
APP_DIR="${APP_DIR:-/opt/spoty-rfid}"
CONF_DIR="${CONF_DIR:-/etc/spoty-rfid}"
DATA_DIR="${DATA_DIR:-/var/lib/spotybox}"
LIBRESPOT_CACHE="${LIBRESPOT_CACHE:-$DATA_DIR/librespot}"
DEVICE_NAME="${DEVICE_NAME:-SpotyBox}"

say() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run as root (sudo ./install.sh)."

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -d "$SRC_DIR/spotyrfid" ] || die "spotyrfid/ package not found next to install.sh."

# ---- 1. system dependencies ----------------------------------------------
say "Installing system packages…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip network-manager \
    libasound2 curl ca-certificates >/dev/null
# librespot: prefer distro package, fall back to a note.
if ! command -v librespot >/dev/null 2>&1; then
    if apt-get install -y -qq librespot >/dev/null 2>&1; then
        say "Installed librespot from apt."
    else
        warn "librespot not available via apt. Install it manually (cargo install"
        warn "librespot, or Raspotify: https://github.com/dtcooper/raspotify),"
        warn "then re-run. Continuing with the control plane setup."
    fi
fi

# ---- 2. service user ------------------------------------------------------
if ! id "$APP_USER" >/dev/null 2>&1; then
    say "Creating service user '$APP_USER'…"
    useradd -r -s /usr/sbin/nologin -m -d "$DATA_DIR" "$APP_USER"
else
    say "User '$APP_USER' already exists."
fi
# groups: plugdev for hidraw access, netdev + audio for nmcli/playback
usermod -aG plugdev,netdev,audio "$APP_USER" 2>/dev/null || true

# ---- 3. directories -------------------------------------------------------
say "Creating directories…"
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR" "$DATA_DIR" "$LIBRESPOT_CACHE"
install -d -m 0750 -o "$APP_USER" -g "$APP_USER" "$CONF_DIR"

# ---- 4. application code --------------------------------------------------
say "Copying application code…"
rm -rf "$APP_DIR/spotyrfid"
cp -r "$SRC_DIR/spotyrfid" "$APP_DIR/spotyrfid"
cp "$SRC_DIR/requirements.txt" "$APP_DIR/requirements.txt"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ---- 5. python venv -------------------------------------------------------
say "Setting up Python virtualenv…"
if [ ! -d "$APP_DIR/.venv" ]; then
    sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
fi
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# ---- 6. secrets file (optional seed; do not clobber) ----------------------
if [ ! -f "$CONF_DIR/spoty-rfid.env" ]; then
    say "Installing env template (optional first-boot seed)…"
    cp "$SRC_DIR/spoty-rfid.env.example" "$CONF_DIR/spoty-rfid.env"
    chmod 600 "$CONF_DIR/spoty-rfid.env"
    chown "$APP_USER:$APP_USER" "$CONF_DIR/spoty-rfid.env"
    warn "Secrets are OPTIONAL here — the box can be configured via the portal."
    warn "Edit $CONF_DIR/spoty-rfid.env only if you want to pre-seed values."
else
    say "Keeping existing secrets file."
fi

# ---- 7. udev rule for the RFID reader -------------------------------------
say "Installing udev rule template for the RFID reader…"
cp "$SRC_DIR/50-spotybox-rfid.rules" /etc/udev/rules.d/50-spotybox-rfid.rules
warn "Edit /etc/udev/rules.d/50-spotybox-rfid.rules with your reader's"
warn "VENDOR/PRODUCT (from 'lsusb'), then: udevadm control --reload-rules && udevadm trigger"

# ---- 8. systemd unit: control plane ---------------------------------------
say "Installing systemd unit: spoty-rfid…"
cat > /etc/systemd/system/spoty-rfid.service <<UNIT
[Unit]
Description=SpotyBox - RFID Spotify player controlled via Telegram
After=network-online.target NetworkManager.service
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
EnvironmentFile=-$CONF_DIR/spoty-rfid.env
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m spotyrfid.main
Restart=on-failure
RestartSec=5
SupplementaryGroups=netdev plugdev audio

[Install]
WantedBy=multi-user.target
UNIT

# ---- 9. systemd unit: librespot speaker -----------------------------------
if command -v librespot >/dev/null 2>&1; then
    LIBRESPOT_BIN="$(command -v librespot)"
    say "Installing systemd unit: librespot…"
    cat > /etc/systemd/system/librespot.service <<UNIT
[Unit]
Description=librespot Spotify Connect speaker for SpotyBox
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
ExecStart=$LIBRESPOT_BIN \\
  --name "$DEVICE_NAME" \\
  --cache $LIBRESPOT_CACHE \\
  --enable-oauth --oauth-port 0 \\
  --bitrate 320 --device-type speaker --backend alsa
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
    warn "librespot needs a ONE-TIME interactive OAuth login before the service"
    warn "can run unattended. Run this once as $APP_USER and follow the URL:"
    warn "  sudo -u $APP_USER $LIBRESPOT_BIN --name \"$DEVICE_NAME\" \\"
    warn "    --cache $LIBRESPOT_CACHE --enable-oauth --oauth-port 0 --backend alsa"
    warn "Then: systemctl enable --now librespot"
else
    warn "Skipping librespot.service (binary not found). Install librespot and"
    warn "re-run this script to generate the unit."
fi

# ---- 10. enable & finish --------------------------------------------------
say "Reloading systemd…"
systemctl daemon-reload
systemctl enable spoty-rfid.service >/dev/null

cat <<DONE

$(say "Install complete.")

Next steps:
  1. Set your RFID reader IDs in /etc/udev/rules.d/50-spotybox-rfid.rules
     (lsusb to find them), then:
       udevadm control --reload-rules && udevadm trigger
  2. (If using librespot) do the one-time OAuth login shown above.
  3. Start the box:
       systemctl start spoty-rfid
  4. On first boot with no config, the box raises a setup portal:
       - no network  -> joins via the 'SpotyBox' Wi-Fi access point
       - otherwise   -> reachable on the box's LAN IP, port 8080
     Enter Wi-Fi, the Telegram bot token, and Spotify app credentials there.
  5. Message your Telegram bot /start to claim ownership, then /auth for Spotify.

Logs:
   journalctl -u spoty-rfid -f
   journalctl -u librespot -f
DONE
