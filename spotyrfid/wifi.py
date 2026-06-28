"""Wi-Fi management via NetworkManager (nmcli).

Strategy:
  * On boot, check connectivity. If we have full internet, do nothing.
  * Otherwise raise an access point ("SpotyBox") so the user can join with a
    phone and submit home Wi-Fi credentials (served by the captive web module).
  * NetworkManager persists the connection profile itself and auto-reconnects
    on subsequent boots — we don't keep our own list of known networks.

All calls shell out to nmcli; nothing here is Pi-specific beyond assuming a
NetworkManager-managed wlan interface.
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)

AP_CON_NAME = "spotybox-ap"


async def _nmcli(*args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "nmcli", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode().strip()


async def has_internet() -> bool:
    rc, out = await _nmcli("-t", "-f", "CONNECTIVITY", "general")
    return out == "full"


async def wait_for_internet(timeout: float = 30.0, interval: float = 3.0) -> bool:
    elapsed = 0.0
    while elapsed < timeout:
        if await has_internet():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return False


async def start_ap(ssid: str, password: str, ifname: str = "wlan0") -> bool:
    """Bring up an open-internet-less hotspot for credential entry."""
    rc, out = await _nmcli(
        "device", "wifi", "hotspot",
        "ifname", ifname, "con-name", AP_CON_NAME,
        "ssid", ssid, "password", password,
    )
    if rc != 0:
        log.error("failed to start AP: %s", out)
    return rc == 0


async def stop_ap() -> None:
    await _nmcli("connection", "down", AP_CON_NAME)


async def connect(ssid: str, password: str, ifname: str = "wlan0") -> bool:
    """Join a network; NM stores the profile for auto-reconnect."""
    rc, out = await _nmcli(
        "device", "wifi", "connect", ssid,
        "password", password, "ifname", ifname,
    )
    if rc != 0:
        log.error("failed to connect to %s: %s", ssid, out)
    return rc == 0


async def scan() -> list[str]:
    await _nmcli("device", "wifi", "rescan")
    rc, out = await _nmcli("-t", "-f", "SSID", "device", "wifi", "list")
    seen, ssids = set(), []
    for line in out.splitlines():
        s = line.strip()
        if s and s not in seen:
            seen.add(s)
            ssids.append(s)
    return ssids
