import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from probe_power_readonly import run_probe
from scio.protocol import Cmd, Response
from scio.usb import ScioTimeout


class Fake:
    def __init__(self, fail=None, mismatch=False):
        self.calls = []
        self.fail = fail
        self.mismatch = mismatch
    def raw_command(self, command):
        self.calls.append(command)
        if self.fail == command:
            raise ScioTimeout('synthetic')
        raw = bytes(26) if command == Cmd.READ_DEVICE_ID else b'\0\0\x84\x03'
        return [Response(command if not self.mismatch else 0x0b, len(raw), raw)]


def test_only_three_reads_and_no_identity_export():
    dev = Fake()
    result = run_probe(dev)
    assert dev.calls == [Cmd.READ_DEVICE_ID, Cmd.READ_BLE, Cmd.READ_DEVICE_ID]
    assert result['timer_read_with_controls']
    assert 'raw_hex' not in result['queries'][0]
    assert result['queries'][1]['timer']['timeout_seconds'] == 900


def test_failed_control_stops_probe():
    dev = Fake(fail=Cmd.READ_DEVICE_ID)
    assert not run_probe(dev)['timer_read_with_controls']
    assert dev.calls == [Cmd.READ_DEVICE_ID]


def test_timer_timeout_still_checks_final_control():
    dev = Fake(fail=Cmd.READ_BLE)
    result = run_probe(dev)
    assert result['matching_awake_controls']
    assert not result['timer_read_with_controls']
    assert len(dev.calls) == 3


def test_wrong_response_opcode_rejected():
    dev = Fake(mismatch=True)
    assert not run_probe(dev)['timer_read_with_controls']
    assert len(dev.calls) == 1
