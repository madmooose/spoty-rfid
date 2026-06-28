"""USB-HID RFID reader -> asyncio queue.

Most cheap USB RFID readers act as a keyboard ("keyboard wedge"): they type the
tag's decimal number followed by Enter. The original spoty-rfid read the raw
hidraw device; this keeps that approach but pushes decoded UIDs onto an asyncio
queue so the rest of the app stays single-threaded async.

The blocking read runs in a dedicated thread; it hands UIDs back to the event
loop via loop.call_soon_threadsafe.
"""
from __future__ import annotations

import asyncio
import logging
import threading

log = logging.getLogger(__name__)

# HID usage-id -> character, for standard US-layout keyboard scancodes.
# 0x1e..0x27 are 1,2,3,4,5,6,7,8,9,0 ; 0x28 is Enter.
_HID_DIGITS = {
    0x1E: "1", 0x1F: "2", 0x20: "3", 0x21: "4", 0x22: "5",
    0x23: "6", 0x24: "7", 0x25: "8", 0x26: "9", 0x27: "0",
}
_HID_ENTER = 0x28


def _first_keycode(report: bytes) -> int:
    """First digit/Enter keycode in a HID report, or 0 if none.

    Scans from byte 2 onward (skipping the modifier + reserved bytes, or a
    report-id + modifier prefix) so it works whether or not the reader prefixes
    a report ID. Key-release reports carry zeros in the key slots, so they
    naturally yield 0 and are ignored.
    """
    for b in report[2:]:
        if b == _HID_ENTER or b in _HID_DIGITS:
            return b
    return 0


class RfidReader:
    def __init__(self, loop: asyncio.AbstractEventLoop, device: str = "/dev/hidraw0"):
        self.loop = loop
        self.device = device
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _emit(self, uid: str) -> None:
        if uid:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, uid)

    def _run(self) -> None:
        buf: list[str] = []
        try:
            # buffering=0 is essential: each read() then maps to one os.read,
            # i.e. exactly one HID report aligned to its start. A buffered
            # reader concatenates reports in an 8 KiB buffer and hands back
            # arbitrary 8-byte slices, which straddles report boundaries and
            # scrambles the keycode positions when reports aren't exactly the
            # requested size.
            with open(self.device, "rb", buffering=0) as fh:
                log.info("RFID reader thread reading %s", self.device)
                while not self._stop.is_set():
                    report = fh.read(64)  # one report; size varies by device
                    if not report:
                        continue
                    # Set LOG_LEVEL=DEBUG to see every raw report.
                    log.debug("hid report: %s", report.hex())
                    keycode = _first_keycode(report)
                    if keycode == _HID_ENTER:
                        uid = "".join(buf)
                        buf.clear()
                        log.info("scanned tag uid=%s", uid)
                        self._emit(uid)
                    elif keycode in _HID_DIGITS:
                        buf.append(_HID_DIGITS[keycode])
        except FileNotFoundError:
            log.error("RFID device %s not found", self.device)
        except PermissionError:
            log.error("No permission for %s (check udev rule)", self.device)
        except Exception:
            log.exception("RFID reader crashed")
