"""USB (CDC serial) transport for the SCiO, read-only / capture use.

Ported from the ``scio_usb`` class in ``01_scio_usb.ipynb`` with the bugs fixed:

* a real serial read timeout (a missing response no longer hangs the kernel);
* :meth:`ScioUSB._read_response` hunts for the ``0xBA`` marker and resyncs
  instead of asserting on the first byte;
* only read-only / capture commands are exposed; write/state commands
  (parameter set, LED, file download, reset, rename) are intentionally absent.

The SCiO enumerates as a Texas Instruments CDC device, VID:PID ``0451:16AA``.
"""

from __future__ import annotations

import struct
import time

import serial
import serial.tools.list_ports as list_ports

from . import protocol
from .protocol import Cmd

SCIO_VID_PID = "0451:16AA"


class ScioTimeout(Exception):
    pass


class ScioProtocolError(Exception):
    def __init__(self, message, partial=b""):
        super().__init__(message)
        self.partial = partial


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


class ScioUSB:
    """Read-only SCiO USB session.

    Use as a context manager::

        with ScioUSB(port) as dev:
            info = dev.read_device_info()
            scan = dev.sample_spectrum(info["firmware_version"])
    """

    SLEEP_BETWEEN_COMMANDS = 0.05

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 5.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self._seq = 1

    # -- connection -------------------------------------------------------
    def open(self):
        self.ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=self.timeout)
        self.ser.reset_input_buffer()
        return self

    def close(self):
        if self.ser is not None:
            self.ser.close()
            self.ser = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    # -- framing ----------------------------------------------------------
    def _next_seq(self) -> int:
        s = self._seq
        self._seq = 1 + (self._seq % 255)
        return s

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

    def _command(self, cmd: int, payload: bytes = b"", allow_write: bool = False) -> protocol.Response:
        if cmd not in protocol.READ_ONLY_COMMANDS and not allow_write:
            raise PermissionError(
                f"command 0x{cmd:02X} is not read-only; pass allow_write=True to send it"
            )
        frame = protocol.build_command(cmd, payload, seq=self._next_seq())
        self.ser.reset_input_buffer()
        self.ser.write(frame)
        self.ser.flush()
        resp = self._read_response()
        time.sleep(self.SLEEP_BETWEEN_COMMANDS)
        return resp

    def raw_command(self, cmd: int, payload: bytes = b"", n_responses: int = 1,
                    allow_write: bool = False) -> list[protocol.Response]:
        """Send a command and collect ``n_responses`` frames (advanced use)."""
        first = self._command(cmd, payload, allow_write=allow_write)
        out = [first]
        for _ in range(n_responses - 1):
            out.append(self._read_response())
        return out

    # -- read-only queries ------------------------------------------------
    def read_device_info(self, ble_attempts: int = 2) -> dict:
        """Device + BLE identifiers.

        The BLE-ID response carries ``i2s_tag_config``, which the server *requires*
        (an empty tag is rejected with ``InvalidUsage``). A single dropped read used
        to leave it blank and silently produce unusable scans, so retry, and flag it
        when it is still missing.
        """
        dev = protocol.parse_device_id(self._command(Cmd.READ_DEVICE_ID).data)
        ble = {}
        for _ in range(max(1, ble_attempts)):
            try:
                ble = protocol.parse_ble_id(self._command(Cmd.READ_BLE_ID).data)
            except (ScioTimeout, ScioProtocolError, IndexError):
                ble = {}
            if ble.get("i2s_tag_config"):
                break
        info = {**dev, **ble}
        if not info.get("i2s_tag_config"):
            info["i2s_tag_missing"] = True
        return info

    def read_temperature(self) -> dict:
        return protocol.parse_temperature(self._command(Cmd.READ_TEMPERATURE).data)

    def read_battery(self) -> dict:
        return protocol.parse_battery(self._command(Cmd.READ_BATTERY_STATE).data)

    def read_file_list(self) -> list[dict]:
        return protocol.parse_file_list(self._command(Cmd.READ_FILE_LIST).data)

    def read_file_header(self, file_id: int) -> dict:
        resp = self._command(Cmd.READ_FILE_HEADER, struct.pack("<I", int(file_id)))
        out = protocol.parse_file_header(resp.data)
        out["file_id"] = int(file_id)
        return out

    def read_all_file_headers(self, ids=(87, 89, 90, 91, 92, 99, 100, 101, 102, 103)) -> dict:
        return {fid: self.read_file_header(fid) for fid in ids}

    # -- capture ----------------------------------------------------------
    def sample_spectrum(self, firmware_version: int = 0, disable_gradient: bool = False) -> dict:
        """Trigger a scan and collect its blobs.

        Returns raw ``bytes`` under the standard keys plus ``status_word`` (the
        first u32 of the sample blob).  Response order on the wire is
        dark, sample, (gradient).
        """
        n = protocol.num_responses_for_firmware(firmware_version, disable_gradient)
        responses = self.raw_command(Cmd.SAMPLE_SPECTRUM, n_responses=n)
        blobs = {"sample_dark": responses[0].data, "sample": responses[1].data}
        status = struct.unpack_from("<I", responses[1].data, 0)[0] if len(responses[1].data) >= 4 else None
        if n > 2:
            blobs["sample_gradient"] = responses[2].data
        return {"blobs": blobs, "status_word": status, "n_responses": n}

    def white_reference(self, firmware_version: int = 0, disable_gradient: bool = False) -> dict:
        """Same command as a scan; the caller stores it as the white reference."""
        scan = self.sample_spectrum(firmware_version, disable_gradient)
        return {
            "sample_white_dark": scan["blobs"]["sample_dark"],
            "sample_white": scan["blobs"]["sample"],
            **({"sample_white_gradient": scan["blobs"]["sample_gradient"]}
               if "sample_gradient" in scan["blobs"] else {}),
        }
