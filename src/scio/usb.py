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

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 5.0):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None

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
