"""SCiO wire protocol: command framing and response parsing.

Everything in this module is pure (no I/O), so it can be unit-tested without
hardware.  All facts here were verified against the decompiled Consumer Physics
app (``com.consumerphysics.android.scioconnection.protocol``) and against real
captures in ``01_rawdata``.

Frame layout (both directions)::

    [seq, 0xBA, cmd, len_lo, len_hi, payload...]

* ``seq``      one-byte sequence counter (1 for a first/only packet).
* ``0xBA``     protocol marker (signed ``-70`` in the Java sources).
* ``cmd``      command id (see :class:`Cmd`).
* ``len``      little-endian uint16 payload length.
* ``payload``  ``len`` bytes.

Over BLE the payload is split across 20-byte notifications, each prefixed with
the sequence byte; over USB CDC the whole frame arrives on the serial stream.
This project uses USB, so the framing helpers below assume a contiguous stream.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

PROTOCOL_MARKER = 0xBA


class Cmd:
    """Command ids (unsigned).  Signed Java bytes are shown in comments."""

    READ_DEVICE_STATUS = 0x00      # 0   read-only
    READ_DEVICE_ID = 0x01          # 1   dsp id, aptina id, firmware version
    SAMPLE_SPECTRUM = 0x02         # 2   dark, sample, (gradient) blobs
    SET_SAMPLE_SETTINGS = 0x03     # 3   (unused by the app)
    READ_TEMPERATURE = 0x04        # 4   3x u32 temperature words
    READ_BATTERY_STATE = 0x05      # 5   battery fields
    READ_EVENT_LOG = 0x06          # 6   (experimental)
    PARAMETER_SET = 0x07           # 7   WRITE - never sent by this project
    PARAMETER_GET = 0x08           # 8   (unused by the app)
    BIST = 0x09                    # 9   built-in self test
    SET_INDICATION_LED = 0x0B      # 11  9-byte payload
    READY_FOR_WR = 0x0E            # 14  state change - opt-in only
    CLEAR_READY_FOR_WR = 0x11      # 17  state change - opt-in only
    FILE_DOWNLOAD = 0x81           # -127 host->device WRITE - never sent
    RESET_DEVICE = 0x83            # -125 disruptive - never sent
    READ_BLE_ID = 0x84             # -124 ble id, ble fw, name, i2s tag
    READ_BLE_STATUS = 0x85         # -123 ble status
    READ_FILE_HEADER = 0x87        # -121 payload <I file_id ; returns 4x u32
    WRITE_USER_DEVICE_NAME = 0x91  # -111 WRITE - never sent
    READ_FILE_LIST = 0x94          # -108 8-byte (type, version) entries
    WRITE_BLE = 0x9A               # -102 WRITE
    READ_BLE = 0x9B                # -101 ble config


# Commands this project is allowed to send: strictly read-only / capture.
READ_ONLY_COMMANDS = frozenset(
    {
        Cmd.READ_DEVICE_STATUS,
        Cmd.READ_DEVICE_ID,
        Cmd.SAMPLE_SPECTRUM,          # capture; does not persist device state
        Cmd.READ_TEMPERATURE,
        Cmd.READ_BATTERY_STATE,
        Cmd.READ_EVENT_LOG,
        Cmd.PARAMETER_GET,
        Cmd.READ_BLE_ID,
        Cmd.READ_BLE_STATUS,
        Cmd.READ_BLE,
        Cmd.READ_FILE_HEADER,
        Cmd.READ_FILE_LIST,
    }
)

# Commands that change device state or write to it - never sent automatically.
WRITE_COMMANDS = frozenset(
    {
        Cmd.PARAMETER_SET,
        Cmd.SET_INDICATION_LED,
        Cmd.READY_FOR_WR,
        Cmd.CLEAR_READY_FOR_WR,
        Cmd.FILE_DOWNLOAD,
        Cmd.RESET_DEVICE,
        Cmd.WRITE_USER_DEVICE_NAME,
        Cmd.WRITE_BLE,
    }
)


# Firmware / calibration file ids (FirmwareFiles.java).
FIRMWARE_FILES = {
    "no_file": 0,
    # This fw147 device reports type 87 as a 119233-byte BLE image, while the
    # 2017 Android enum calls BLE type 89. Keep both observations explicit.
    "ble_runtime": 87,
    "ble": 89,
    "dsp_boot": 90,
    "dsp_dec": 91,
    "dsp_op": 92,
    "deadPixelsIndices": 100,
    "centers": 101,
    "bins": 102,
    "nPixelsPerBin": 103,
}
FIRMWARE_FILE_NAMES = {v: k for k, v in FIRMWARE_FILES.items()}

# Scan blob header type words (first u32, little-endian).
BLOB_TYPE_SAMPLE = 0x00      # sample and dark
BLOB_TYPE_GRADIENT = 0x6E    # gradient (== 110)


def to_u8(value: int) -> int:
    """Java bytes are signed; the serial wire carries 0..255."""
    return value & 0xFF


def build_command(cmd: int, payload: bytes = b"", seq: int = 1) -> bytes:
    """Build one contiguous SCiO command frame (USB).

    >>> build_command(Cmd.SAMPLE_SPECTRUM).hex()
    '01ba020000'
    >>> build_command(Cmd.SET_INDICATION_LED, b'\\x00' * 9).hex()
    '01ba0b0900000000000000000000'
    >>> build_command(Cmd.READ_FILE_HEADER, struct.pack('<I', 100)).hex()
    '01ba87040064000000'
    """
    if payload is None:
        payload = b""
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes-like")
    if len(payload) > 0xFFFF:
        raise ValueError("payload too large for 16-bit SCiO length")
    header = bytes(
        [
            to_u8(seq),
            PROTOCOL_MARKER,
            to_u8(cmd),
            len(payload) & 0xFF,
            (len(payload) >> 8) & 0xFF,
        ]
    )
    return header + bytes(payload)


@dataclass
class Response:
    """A parsed response frame."""

    command: int
    length: int
    data: bytes

    def u8(self, i: int) -> int:
        return self.data[i]

    def u16(self, i: int) -> int:
        return (self.data[i + 1] << 8) | (self.data[i] & 0xFF)

    def u32(self, i: int) -> int:
        return struct.unpack_from("<I", self.data, i)[0]

    def hex(self, i: int, n: int) -> str:
        return self.data[i : i + n].hex().upper()

    def string(self, i: int, n: int) -> str:
        chunk = self.data[i : i + n]
        nul = chunk.find(0)
        if nul >= 0:
            chunk = chunk[:nul]
        return chunk.decode("latin-1").strip()


def _word_swap_hex(hex_str: str) -> str:
    """Swap 16-bit words within a hex string (DeviceIdResponseCommandHandler).

    For each group of 4 hex chars ``abcd`` emit ``cdab``.

    >>> _word_swap_hex('12345678')
    '34127856'
    """
    out = []
    for i in range(0, len(hex_str) - 3, 4):
        out.append(hex_str[i + 2])
        out.append(hex_str[i + 3])
        out.append(hex_str[i])
        out.append(hex_str[i + 1])
    return "".join(out)


def parse_device_id(data: bytes) -> dict:
    """Parse a READ_DEVICE_ID (0x01) response.

    Layout (from DeviceIdResponseCommandHandler):
        [0:8]   DSP id
        [16:24] Aptina id, stored with 16-bit words byte-swapped
        [24:26] firmware version (u16 LE)

    ``device_id`` is the word-swapped Aptina id, uppercase - this is the value
    the app sent to the server as ``device_id``.
    """
    r = Response(Cmd.READ_DEVICE_ID, len(data), data)
    dsp_id = r.hex(0, 8)
    aptina_field = r.hex(16, 8)
    device_id = _word_swap_hex(aptina_field).upper()
    return {
        "dsp_id": dsp_id.lower(),
        "aptina_field": aptina_field.lower(),
        "device_id": device_id,
        "firmware_version": r.u16(24),
    }


def parse_ble_id(data: bytes) -> dict:
    """Parse a READ_BLE_ID (0x84) response (BleIDResponseCommandHandler)."""
    r = Response(Cmd.READ_BLE_ID, len(data), data)
    return {
        "ble_id": r.hex(0, 8).lower(),
        "ble_fw_version": r.u16(8),
        "device_serial_fragment": r.string(40, 10),
        "device_name": r.string(50, 16),
        "i2s_tag_config": r.string(66, 64).replace("\x00", "").strip(),
    }


def parse_temperature(data: bytes) -> dict:
    """Parse a READ_TEMPERATURE (0x04) response: 3 x u32 LE.

    >>> t = parse_temperature(bytes.fromhex('940100004D0A000000000000'))
    >>> round(t['cmos_t'], 2), t['chip_t'], t['obj_t']
    (20.42, 26.37, 0.0)
    """
    words = struct.unpack_from("<3I", data, 0)
    return {
        "cmos_t": (words[0] - 375.22) / 1.4092,
        "chip_t": words[1] / 100.0,
        "obj_t": words[2] / 100.0,
        # The Android app truncates to int twice: trunc(trunc(raw - 375.22) / 1.4092),
        # so its Aptina/CMOS value is always a whole number. The calibration decision
        # compares *this* value, so keep it alongside the exact float.
        "cmos_t_app": float(int(int(words[0] - 375.22) / 1.4092)),
        # raw words kept for completeness (chip/obj are unused by the WR decision)
        "raw_u32": list(words),
    }


def parse_battery(data: bytes) -> dict:
    """Parse a READ_BATTERY_STATE (0x05) response (handleReadBattery)."""
    r = Response(Cmd.READ_BATTERY_STATE, len(data), data)
    return {
        "charge_percent": r.u16(0),
        "health_percent": r.u8(2),
        "health_status": r.u8(3),
        "charging_status": r.u16(4),
        "voltage_v": r.u16(6) / 1000.0,
    }


def parse_file_list(data: bytes) -> list[dict]:
    """Parse a READ_FILE_LIST (0x94) response: (u32 type, u32 version) pairs."""
    entries = []
    for off in range(0, len(data) - 7, 8):
        ftype, fver = struct.unpack_from("<II", data, off)
        entries.append(
            {
                "file_type": ftype,
                "file_version": fver,
                "name": FIRMWARE_FILE_NAMES.get(ftype),
            }
        )
    return entries


def parse_file_header(data: bytes) -> dict:
    """Parse a READ_FILE_HEADER (0x87) response: 4 x u32; word 3 is the checksum."""
    words = list(struct.unpack_from("<%dI" % (len(data) // 4), data)) if len(data) >= 4 else []
    out = {"words": words}
    if len(words) >= 4:
        out["checksum"] = words[3]
    return out


def parse_blob_header(blob: bytes) -> dict:
    """Describe the first eight bytes and the remaining scan payload.

    The first word behaves as a type marker (0 for sample/dark and 0x6E for
    gradient).  The meaning of the second word, and whether the remaining
    bytes are encrypted, compressed or packed, are unknown. ``nonce`` is
    retained as a compatibility alias; new code should use ``second_word``.
    """
    if len(blob) < 8:
        raise ValueError("blob shorter than 8-byte header")
    btype, second_word = struct.unpack_from("<II", blob, 0)
    body = blob[8:]
    return {
        "type": btype,
        "second_word": second_word,
        "nonce": second_word,
        "body": body,
        "body_len": len(body),
        "body_blocks": len(body) / 16.0,
    }


# Expected raw blob sizes by i2s ("compression") generation.  The suffix after
# the date encodes the image-to-spectrum table version; "-e" and "-o" are the
# two we have evidence for.  Unknown generations accept any size.
def expected_blob_sizes(i2s_tag: str | None) -> dict | None:
    if not i2s_tag:
        return None
    if "-e" in i2s_tag:
        return {"sample": 1800, "sample_dark": 1800, "sample_gradient": 1656}
    if "-o" in i2s_tag:
        return {"sample": 1800, "sample_dark": 1800, "sample_gradient": 1416}
    return None


def num_responses_for_firmware(firmware_version: int, disable_gradient: bool = False) -> int:
    """How many response commands a SAMPLE_SPECTRUM returns (DeviceInfo.java).

    fw < 136 -> 2 (dark, sample); fw >= 153 with gradient disabled -> 2; else 3.
    """
    if firmware_version and firmware_version > 0:
        if firmware_version < 136:
            return 2
        if firmware_version >= 153 and disable_gradient:
            return 2
    return 3
