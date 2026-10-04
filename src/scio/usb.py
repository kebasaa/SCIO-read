"""USB (CDC serial) transport for the SCiO, read-only / capture by default.

Ported from the ``scio_usb`` class in ``archive/notebooks/01_scio_usb.ipynb``
with the bugs fixed:

* a real serial read timeout (a missing response no longer hangs the kernel);
* :meth:`ScioUSB._read_response` hunts for the ``0xBA`` marker and resyncs
  instead of asserting on the first byte;
* power-saver writes and reset require explicit allow_write=True; capture never
  invokes them. Parameter set, LED, file download and rename have no helpers.

The SCiO enumerates as a Texas Instruments CDC device, VID:PID ``0451:16AA``.
"""

from __future__ import annotations

import struct

import serial
import serial.tools.list_ports as list_ports

from . import protocol
from .device import ScioDevice
from .protocol import ScioProtocolError, ScioTimeout

__all__ = ["ScioUSB", "find_scio_ports", "ScioTimeout", "ScioProtocolError", "SCIO_VID_PID"]

SCIO_VID_PID = "0451:16AA"


def find_scio_ports() -> list[dict]:
    """Return candidate SCiO serial ports (VID:PID 0451:16AA first)."""
    ports = []
    for p in list_ports.comports():
        vidpid = None
        if p.vid is not None and p.pid is not None:
            vidpid = f"{p.vid:04X}:{p.pid:04X}"
        ports.append(
            {
                "device": p.device,
                "description": p.description,
                "hwid": p.hwid,
                "vidpid": vidpid,
                "is_scio": vidpid == SCIO_VID_PID,
            }
        )
    ports.sort(key=lambda d: not d["is_scio"])
    return ports


class ScioUSB(ScioDevice):
    """SCiO USB session, read-only unless a write is explicitly authorized.

    Use as a context manager::

        with ScioUSB(port) as dev:
            info = dev.read_device_info()
            scan = dev.sample_spectrum(info["firmware_version"])

    The queries (``read_device_info``, ``sample_spectrum``, ...) live in
    :class:`scio.device.ScioDevice` and are shared with :class:`scio.ble.ScioBLE`.
    """

    transport_name = "usb"
    MAX_STALE_REPLIES = 8  # stale frames skipped per read before giving up

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 5.0):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self._expect = None       # command id of the request in flight
        self.stale_replies = 0    # complete replies to an earlier, abandoned request

    # -- connection -------------------------------------------------------
    def open(self):
        self.ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=self.timeout)
        self.ser.reset_input_buffer()
        return self

    def close(self):
        if self.ser is not None:
            self.ser.close()
            self.ser = None

    # -- framing ----------------------------------------------------------
    def _discard_input(self):
        self.ser.reset_input_buffer()

    def send_frame(self, frame: bytes):
        if len(frame) >= 3 and frame[1] == protocol.PROTOCOL_MARKER:
            self._expect = frame[2]
        self.ser.write(frame)
        self.ser.flush()

    def _read_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.ser.read(n - len(buf))
            if not chunk:
                raise ScioTimeout(f"timed out reading {n} bytes (got {len(buf)})")
            buf += chunk
        return buf

    def _read_response(self, resync_limit: int = 4096) -> protocol.Response:
        """Next reply *to the request in flight*, resyncing to 0xBA if needed.

        Every reply echoes its request's command id. A frame with another id is a
        late answer to an earlier request that timed out (it can land after the
        input buffer was cleared); it is skipped and counted in ``stale_replies``
        so it is never returned as this request's answer.
        """
        for _ in range(self.MAX_STALE_REPLIES + 1):
            resp = self._read_frame(resync_limit)
            if self._expect is None or resp.command == self._expect:
                return resp
            self.stale_replies += 1
        raise ScioProtocolError(
            f"only stale replies while waiting for 0x{self._expect:02X}")

    def _read_frame(self, resync_limit: int = 4096) -> protocol.Response:
        """Read one response frame, resyncing to the 0xBA marker if needed."""
        scanned = 0
        while True:
            b = self.ser.read(1)
            if not b:
                raise ScioTimeout("timed out waiting for response marker 0xBA")
            if b[0] == protocol.PROTOCOL_MARKER:
                break
            scanned += 1
            if scanned > resync_limit:
                raise ScioProtocolError("no 0xBA marker within resync window")
        cmd = self._read_exact(1)[0]
        length = struct.unpack("<H", self._read_exact(2))[0]
        data = self._read_exact(length) if length else b""
        return protocol.Response(command=cmd, length=length, data=data)
