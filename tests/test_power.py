import pytest
from scio import power, protocol
from scio.usb import ScioUSB, ScioTimeout


@pytest.mark.parametrize('minutes,seconds', [(1,60),(2,120),(3,271),(4,271),(13,783),(15,783),(30,1807)])
def test_app_signed_byte_encoding(minutes, seconds):
    assert power.power_saver_seconds(minutes) == seconds
    assert power.power_saver_payload(minutes) == b'\0\0' + seconds.to_bytes(2, 'little')


@pytest.mark.parametrize('value', [0,31,-1,True,1.5,'3'])
def test_bad_timer_rejected(value):
    with pytest.raises((ValueError, TypeError)):
        power.power_saver_payload(value)


def test_timer_read_preserves_unknown_fields():
    assert power.parse_power_saver(bytes.fromhex('aabb0f01cc')) == {
        'timeout_seconds':271, 'app_display_minutes':4, 'raw_hex':'aabb0f01cc'}
    with pytest.raises(ValueError):
        power.parse_power_saver(b'\0\0')


def test_observed_firmware147_timer_response():
    # Captured via READ_BLE between two matching identity controls; no write.
    result = power.parse_power_saver(bytes.fromhex('00006801'))
    assert result['timeout_seconds'] == 360
    assert result['app_display_minutes'] == 6


class Serial:
    def __init__(self): self.writes = []
    def reset_input_buffer(self): pass
    def write(self, value): self.writes.append(value)
    def flush(self): pass


def device():
    d = ScioUSB('unused')
    d.ser = Serial()
    d.SLEEP_BETWEEN_COMMANDS = 0
    d._read_response = lambda: protocol.Response(0x9A, 0, b'')
    return d


def test_writes_require_explicit_optin_and_never_auto_reset():
    d = device()
    with pytest.raises(PermissionError): d.set_power_saver(3)
    with pytest.raises(PermissionError): d.reset_device()
    with pytest.raises(PermissionError): d.reset_device(allow_write=1)
    assert d.ser.writes == []
    result = d.set_power_saver(3, allow_write=True)
    assert d.ser.writes == [bytes.fromhex('01ba9a040000000f01')]
    assert result['encoded_seconds'] == 271
    assert result['reset_sent'] is False
    assert result['hardware_verified'] is False
    d.reset_device(allow_write=True)
    assert d.ser.writes[-1] == bytes.fromhex('02ba830000')


def test_reset_timeout_not_retried():
    d = device()
    def timeout(): raise ScioTimeout('no response')
    d._read_response = timeout
    with pytest.raises(ScioTimeout): d.reset_device(allow_write=True)
    assert len(d.ser.writes) == 1


def test_read_timer_only_sends_read():
    d = device()
    d._read_response = lambda: protocol.Response(0x9B, 4, bytes.fromhex('00008403'))
    assert d.read_power_saver()['timeout_seconds'] == 900
    assert d.ser.writes == [bytes.fromhex('01ba9b0000')]
