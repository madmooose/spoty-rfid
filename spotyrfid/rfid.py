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
            with open(self.device, "rb") as fh:
                while not self._stop.is_set():
                    report = fh.read(8)  # standard 8-byte keyboard report
                    if not report or len(report) < 3:
                        continue
                    keycode = report[2]
                    if keycode == 0:
                        continue
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
