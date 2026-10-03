"""App-supported automatic-off timer encoding; not a remote power-on protocol.

Derived from PowerSaverActivity and SCiOBLeService. USB timer reads were observed
on firmware 147; writes, reset and physical shutdown timing remain unvalidated.
See dev/DEVICE_FUNCTION_REFERENCE.md for evidence.
"""
import struct


def _signed_byte(value: int) -> int:
    return (value + 128) % 256 - 128


def power_saver_seconds(minutes: int) -> int:
    """Reproduce the Android app's signed-byte adjustment for its 1..30 UI.

    This is deliberately NOT simply minutes * 60. For example, 3 minutes encodes
    271 seconds and 15 minutes encodes 783 seconds. No physical timing claimed.
    """
    if isinstance(minutes, bool) or not isinstance(minutes, int):
        raise TypeError('minutes must be an integer')
    if not 1 <= minutes <= 30:
        raise ValueError('minutes must be within the observed app range 1..30')
    seconds = minutes * 60
    low_byte = _signed_byte(seconds & 255)
    if low_byte < 15:
        seconds += _signed_byte(15 - low_byte)
    return seconds


def power_saver_payload(minutes: int) -> bytes:
    """WRITE_BLE payload: two zero bytes, then adjusted seconds as U16 LE."""
    return b'\x00\x00' + struct.pack('<H', power_saver_seconds(minutes))


def parse_power_saver(data: bytes) -> dict:
    """READ_BLE timer is U16 LE at offset 2; other bytes remain uninterpreted."""
    if len(data) < 4:
        raise ValueError('READ_BLE response too short for power-saver timer')
    seconds = struct.unpack_from('<H', data, 2)[0]
    return {'timeout_seconds': seconds, 'app_display_minutes': seconds // 60,
            'raw_hex': data.hex()}
