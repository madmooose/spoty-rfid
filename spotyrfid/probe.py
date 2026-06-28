"""Standalone RFID probe — debug a reader that isn't registering taps.

Run on the box:

    python -m spotyrfid.probe                # list candidate hidraw devices
    python -m spotyrfid.probe /dev/hidraw0   # watch one device, decode taps

It uses the SAME decoding as the live reader (rfid.py), so what you see here
is what the app would see. Only one process can read a hidraw device at a
time, so stop the service first if you want to probe the same device:
    sudo systemctl stop spoty-rfid
Use sudo if you hit a permission error (the udev rule may not match your reader).
"""
from __future__ import annotations

import sys
from pathlib import Path

from .rfid import _HID_DIGITS, _HID_ENTER, _first_keycode


def _list() -> None:
    devs = sorted(Path("/dev").glob("hidraw*"))
    if not devs:
        print("No /dev/hidraw* devices found. Is the reader plugged in? Try `lsusb`.")
        return
    print("Candidate HID devices:\n")
    for d in devs:
        name = vid = pid = "?"
        uevent = Path(f"/sys/class/hidraw/{d.name}/device/uevent")
        if uevent.exists():
            for line in uevent.read_text().splitlines():
                if line.startswith("HID_NAME="):
                    name = line.split("=", 1)[1]
                elif line.startswith("HID_ID="):
                    # HID_ID=BUS:VENDOR:PRODUCT (zero-padded hex)
                    parts = line.split(":")
                    if len(parts) == 3:
                        vid, pid = parts[1][-4:].lower(), parts[2][-4:].lower()
        print(f"  {d}   vid={vid} pid={pid}   {name}")
    print("\nWatch the reader with:  python -m spotyrfid.probe /dev/hidrawN")
    print("Then set RFID_DEVICE=/dev/hidrawN (or fix the udev rule) if it's not hidraw0.")


def _watch(device: str) -> None:
    print(f"Reading {device} — tap a chip now (Ctrl-C to stop)…\n")
    buf: list[str] = []
    # buffering=0 so each read() is one HID report (see rfid.py for why).
    with open(device, "rb", buffering=0) as fh:
        while True:
            report = fh.read(64)
            if not report:
                continue
            print(f"raw[{len(report)}]:", report.hex())
            keycode = _first_keycode(report)
            if keycode == _HID_ENTER:
                print("  -> decoded UID:", "".join(buf) or "(empty)")
                buf.clear()
            elif keycode in _HID_DIGITS:
                buf.append(_HID_DIGITS[keycode])


def main() -> None:
    if len(sys.argv) > 1:
        _watch(sys.argv[1])
    else:
        _list()


if __name__ == "__main__":
    main()
