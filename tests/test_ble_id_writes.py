"""BLE-ID record writes (0x89 serial prefix, 0x93 i2s tag): opt-in, confirmed, exact bytes, readback."""

import pytest

from scio import protocol
from scio.usb import ScioUSB

TAG = "20150812-e:PRODUCTION"
PREFIX = "CPPCA0031C6PF0516009W6404386A1"
YES = lambda warning: True  # noqa: E731


class Serial:
    def __init__(self): self.writes = []
    def reset_input_buffer(self): pass
    def write(self, value): self.writes.append(bytes(value))
    def flush(self): pass


def _record(serial_prefix="", tag=""):
    data = bytearray(130)
    data[10:10 + len(serial_prefix)] = serial_prefix.encode()
    data[40:50] = b"DF1816004A"
    data[50:56] = b"myScio"
    data[66:66 + len(tag)] = tag.encode()
    return bytes(data)


def device(before, after=None, ack=0x93):
    """Replies: BLE-ID read (current value), write ack, BLE-ID read (readback)."""
    d = ScioUSB("unused")
    d.ser = Serial()
    d.SLEEP_BETWEEN_COMMANDS = 0
    replies = iter([protocol.Response(0x84, 130, before), protocol.Response(ack, 0, b""),
                    protocol.Response(0x84, 130, after if after is not None else before)])
    d._read_response = lambda: next(replies)
    return d


def _writes(d):
    """Frames other than BLE-ID reads."""
    return [w for w in d.ser.writes if w[2] != 0x84]


def test_write_i2s_tag_warns_then_sends_raw_ascii_and_verifies():
    d = device(_record(), _record(tag=TAG))
    seen = []
    result = d.write_i2s_tag(TAG, allow_write=True, confirm=lambda w: seen.append(w) or True)
    assert "rejected" in seen[0] and repr(TAG) in seen[0] and "current: ''" in seen[0]
    assert [w[1:] for w in _writes(d)] == [bytes.fromhex("ba931500") + TAG.encode()]
    assert result["verified"] is True and result["previous"] == "" and result["readback"] == TAG


def test_serial_prefix_write_and_full_serial_parse():
    d = device(_record(), _record(serial_prefix=PREFIX), ack=0x89)
    assert d.write_serial_prefix(PREFIX, allow_write=True, confirm=YES)["verified"]
    assert _writes(d)[0][1:] == bytes.fromhex("ba891e00") + PREFIX.encode()
    parsed = protocol.parse_ble_id(_record(serial_prefix=PREFIX))
    assert parsed["device_serial"] == PREFIX + "DF1816004A"


def test_declined_confirmation_writes_nothing():
    d = device(_record())
    with pytest.raises(PermissionError, match="nothing was written"):
        d.write_i2s_tag(TAG, allow_write=True, confirm=lambda w: False)
    assert _writes(d) == []


def test_default_confirmation_asks_on_the_console(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    d = device(_record())
    with pytest.raises(PermissionError):
        d.write_i2s_tag(TAG, allow_write=True)
    assert "WARNING" in capsys.readouterr().out and _writes(d) == []
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    d = device(_record(), _record(tag=TAG))
    assert d.write_i2s_tag(TAG, allow_write=True)["verified"]


def test_value_already_present_is_not_rewritten():
    d = device(_record(tag=TAG))
    result = d.write_i2s_tag(TAG, allow_write=True, confirm=lambda w: pytest.fail("asked"))
    assert result["verified"] and result["written"] is None and _writes(d) == []


def test_unverified_readback_is_reported():
    d = device(_record())
    assert d.write_i2s_tag(TAG, allow_write=True, confirm=YES)["verified"] is False


@pytest.mark.parametrize("field,value", [("i2s_tag_config", ""), ("serial_prefix", "x" * 31),
                                         ("i2s_tag_config", "x" * 65), ("i2s_tag_config", "é"),
                                         ("nonsense", "x")])
def test_bad_values_are_refused_before_anything_is_sent(field, value):
    d = device(_record())
    with pytest.raises((ValueError, UnicodeEncodeError)):
        d.write_ble_id_field(field, value, allow_write=True, confirm=YES)
    assert d.ser.writes == []


def test_writes_require_explicit_optin():
    d = device(_record())
    with pytest.raises(PermissionError):
        d.write_i2s_tag(TAG, confirm=YES)
    with pytest.raises(PermissionError):
        d.write_ble_id_field("serial_prefix", "abc", allow_write=1, confirm=YES)
    for cmd in (0x88, 0x89, 0x93, 0x95):
        assert cmd in protocol.WRITE_COMMANDS
        with pytest.raises(PermissionError):
            d._command(cmd, b"x")
    assert d.ser.writes == []
