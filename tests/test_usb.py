"""USB transport: replies are matched to requests through the real byte-stream reader."""

import pytest

from scio import protocol
from scio.protocol import Cmd, ScioProtocolError, ScioTimeout
from scio.usb import ScioUSB

TEMP = bytes.fromhex("940100004D0A000000000000")
BATTERY = bytes.fromhex("6400" "5b02" "0000" "e40f")


def frame(cmd, data, seq=1):
    return protocol.build_command(cmd, data, seq=seq)


class ByteSerial:
    """A serial port as a byte stream: writes trigger replies, reads drain the buffer."""

    def __init__(self, replies):
        self.replies = replies      # cmd -> list of raw reply frames to append on write
        self.buffer = bytearray()
        self.writes = []
        self.before_reply = []      # raw bytes appended after a write, before its reply

    def reset_input_buffer(self):
        self.buffer.clear()

    def write(self, data):
        self.writes.append(bytes(data))
        for chunk in self.before_reply:
            self.buffer += chunk
        self.before_reply = []
        for reply in self.replies.get(data[2], []):
            self.buffer += reply

    def flush(self):
        pass

    def read(self, n):
        out = bytes(self.buffer[:n])
        del self.buffer[:n]
        return out


def device(replies):
    d = ScioUSB("unused")
    d.ser = ByteSerial(replies)
    d.SLEEP_BETWEEN_COMMANDS = 0
    return d


def test_late_reply_landing_after_the_buffer_was_cleared_is_skipped():
    d = device({Cmd.READ_BATTERY_STATE: [frame(Cmd.READ_BATTERY_STATE, BATTERY)]})
    # the temperature reply of an earlier, timed-out request lands after our write
    d.ser.before_reply = [frame(Cmd.READ_TEMPERATURE, TEMP)]
    assert d.read_battery()["charge_percent"] == 100
    assert d.stale_replies == 1


def test_scan_messages_are_kept_and_a_stale_frame_before_them_is_dropped():
    blobs = [bytes([1]) * 1800, bytes([2]) * 1800, bytes([3]) * 1656]
    d = device({Cmd.SAMPLE_SPECTRUM: [frame(Cmd.SAMPLE_SPECTRUM, b) for b in blobs]})
    d.ser.before_reply = [frame(Cmd.READ_TEMPERATURE, TEMP)]
    scan = d.sample_spectrum(147)
    assert [scan["blobs"][k] for k in ("sample_dark", "sample", "sample_gradient")] == blobs
    assert d.stale_replies == 1


def test_only_stale_frames_is_a_protocol_error_not_a_wrong_answer():
    d = device({})
    d.ser.before_reply = [frame(Cmd.READ_TEMPERATURE, TEMP)] * (ScioUSB.MAX_STALE_REPLIES + 1)
    with pytest.raises(ScioProtocolError, match="stale"):
        d.read_battery()


def test_matching_reply_and_timeout_are_unchanged():
    d = device({Cmd.READ_TEMPERATURE: [frame(Cmd.READ_TEMPERATURE, TEMP)]})
    assert round(d.read_temperature()["cmos_t"], 2) == 20.42
    assert d.stale_replies == 0
    with pytest.raises(ScioTimeout):
        d.read_battery()            # nothing comes back: still a plain timeout


def test_marker_resync_still_works():
    d = device({Cmd.READ_TEMPERATURE: [b"\x00\x13\x37" + frame(Cmd.READ_TEMPERATURE, TEMP)]})
    assert round(d.read_temperature()["cmos_t"], 2) == 20.42
