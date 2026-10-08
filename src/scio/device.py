"""Transport-independent SCiO session: read-only guard and high-level queries.

:class:`ScioDevice` holds everything that is the same over USB and BLE. A
transport subclass supplies only the connection and the byte-level framing:

* ``open()`` / ``close()``
* ``_discard_input()``   drop anything unread before a new command
* ``send_frame(frame)``  send one complete ``[seq, 0xBA, cmd, len, payload]`` frame
* ``_read_response()``   return the next complete :class:`protocol.Response`

and sets ``transport_name`` (stored in each scan record).
"""

from __future__ import annotations

import struct
import time

from . import protocol
from .protocol import Cmd, ScioProtocolError, ScioTimeout

__all__ = ["ScioDevice", "ScioTimeout", "ScioProtocolError"]


def _ask_console(warning: str) -> bool:
    """Default confirmation for device writes: print the warning, require ``yes``."""
    print(warning)
    try:
        answer = input("Type 'yes' to write it: ")
    except EOFError:
        return False
    return answer.strip().lower() == "yes"


class ScioDevice:
    """SCiO session, read-only unless a write is explicitly authorized."""

    transport_name = "unknown"
    SLEEP_BETWEEN_COMMANDS = 0.05

    def __init__(self):
        self._seq = 1

    # -- transport hooks --------------------------------------------------
    def open(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def _discard_input(self):
        raise NotImplementedError

    def send_frame(self, frame: bytes):
        raise NotImplementedError

    def _read_response(self) -> protocol.Response:
        raise NotImplementedError

    def read_response(self) -> protocol.Response:
        """Read the next complete response frame."""
        return self._read_response()

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    # -- framing ----------------------------------------------------------
    def _next_seq(self) -> int:
        s = self._seq
        self._seq = 1 + (self._seq % 255)
        return s

    def _command(self, cmd: int, payload: bytes = b"", allow_write: bool = False) -> protocol.Response:
        if cmd not in protocol.READ_ONLY_COMMANDS and not allow_write:
            raise PermissionError(
                f"command 0x{cmd:02X} is not read-only; pass allow_write=True to send it"
            )
        frame = protocol.build_command(cmd, payload, seq=self._next_seq())
        self._discard_input()
        self.send_frame(frame)
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
    def read_power_saver(self) -> dict:
        """Read the automatic-off timer; does not wake a powered-off device."""
        from .power import parse_power_saver
        return parse_power_saver(self._command(Cmd.READ_BLE).data)

    def set_power_saver(self, minutes: int, *, allow_write: bool = False) -> dict:
        """Send the app-compatible automatic-off setting (USB hardware-unverified).

        State-changing, opt-in only. Does NOT reset automatically. The app resets
        after success; use reset_device explicitly if appropriate. A returned
        response is not proof that the timer persisted or that shutdown occurred.
        The signed-byte adjustment can change the requested duration; inspect
        encoded_seconds. Zero/immediate-off and remote power-on are unsupported.
        """
        from .power import power_saver_payload, power_saver_seconds
        if allow_write is not True:
            raise PermissionError('set_power_saver requires allow_write=True')
        payload = power_saver_payload(minutes)
        response = self._command(Cmd.WRITE_BLE, payload, allow_write=True)
        return {'requested_minutes': minutes,
                'encoded_seconds': power_saver_seconds(minutes),
                'response': response, 'reset_sent': False,
                'hardware_verified': False}

    def reset_device(self, *, allow_write: bool = False) -> protocol.Response:
        """Explicit disruptive reset, NOT power-off/on; USB behavior unverified.

        No retries. The connection can disappear before a response; a timeout
        therefore does not prove the reset failed. Reconnect manually.
        App usage suggests restart, but preservation of every device setting
        is not established. Do not use when that preservation is a prerequisite.
        """
        if allow_write is not True:
            raise PermissionError('reset_device requires allow_write=True')
        return self._command(Cmd.RESET_DEVICE, allow_write=True)

    def _ble_id_field(self, field: str) -> str:
        _cmd, offset, size = protocol.BLE_ID_FIELDS[field]
        record = self._command(Cmd.READ_BLE_ID).data
        return record[offset:offset + size].split(b"\0", 1)[0].decode("latin-1")

    def write_ble_id_field(self, field: str, value: str, *, allow_write: bool = False,
                           confirm=None) -> dict:
        """Overwrite one text field of the BLE-ID record, after a warning, and read it back.

        *field* is ``"i2s_tag_config"`` (0x93), ``"serial_prefix"`` (0x89) or
        ``"device_name"`` (0x91); see :data:`protocol.BLE_ID_FIELDS`.

        **Only for repairing a wiped field.** The device reports these values
        itself; a wrong i2s tag or serial is stored permanently and the vendor
        server then rejects every scan from this device until it is rewritten.
        So the current value is read first and the user is warned and asked:
        *confirm* is called with the warning text and must return ``True`` (the
        default asks on the console and needs the answer ``yes``). Nothing is
        sent unless it does. Requires ``allow_write=True`` as well; never called
        automatically. The value is sent as raw ASCII (no padding); empty values
        are refused because an empty write clears the field. Does not reset.
        """
        if allow_write is not True:
            raise PermissionError("write_ble_id_field requires allow_write=True")
        if field not in protocol.BLE_ID_FIELDS:
            raise ValueError(f"unknown BLE-ID field {field!r}; one of {sorted(protocol.BLE_ID_FIELDS)}")
        cmd, offset, size = protocol.BLE_ID_FIELDS[field]
        payload = value.encode("ascii")
        if not 0 < len(payload) <= size:
            raise ValueError(f"{field} must be 1..{size} ASCII bytes, got {len(payload)}")
        current = self._ble_id_field(field)
        out = {"field": field, "command": cmd, "previous": current, "written": None,
               "response": None, "readback": current, "verified": current == value}
        if current == value:
            return out  # already correct: nothing to write
        warning = (
            f"WARNING: this permanently overwrites the device's {field} "
            f"(BLE-ID bytes {offset}-{offset + size}, command 0x{cmd:02X}).\n"
            f"  current: {current!r}\n  new:     {value!r}\n"
            "The vendor server checks these values exactly: a wrong value is rejected and\n"
            "every scan from this device fails until it is rewritten. Only do this to\n"
            "restore a wiped field with its known original value."
        )
        if confirm is None:
            confirm = _ask_console
        if confirm(warning) is not True:
            raise PermissionError(f"{field} write not confirmed; nothing was written")
        out["response"] = self._command(cmd, payload, allow_write=True)
        out["written"] = value
        out["readback"] = self._ble_id_field(field)
        out["verified"] = out["readback"] == value
        return out

    def write_i2s_tag(self, tag: str, *, allow_write: bool = False, confirm=None) -> dict:
        """Restore a wiped i2s tag (0x93), e.g. ``"20150812-e:PRODUCTION"``; warns and asks first."""
        return self.write_ble_id_field("i2s_tag_config", tag, allow_write=allow_write,
                                       confirm=confirm)

    def write_serial_prefix(self, prefix: str, *, allow_write: bool = False, confirm=None) -> dict:
        """Restore a wiped serial prefix (0x89, first 30 characters); warns and asks first."""
        return self.write_ble_id_field("serial_prefix", prefix, allow_write=allow_write,
                                       confirm=confirm)

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

    def read_object_temperature(self) -> float:
        """Object/surface temperature in degC (READ_TEMPERATURE word 2, ``w2/100``).

        This is the uncalibrated reading of whatever the sensor window is against.
        It is **0.0 on some units** (observed 0 on the firmware-147 reference unit),
        but a live surface temperature on at least one firmware-138 unit (a hand
        read ~32.6 degC versus ~20 degC for room-temperature targets). Read-only.
        """
        return self.read_temperature()["obj_t"]

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
