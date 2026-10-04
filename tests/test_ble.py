"""BLE framing and the ScioBLE session, against a fake GATT client (no bleak, no radio)."""

import struct
from types import SimpleNamespace

import pytest

from scio import ble, protocol
from scio.protocol import BleReassembler, Cmd, ScioProtocolError, ScioTimeout, ble_packets


# ------------------------------------------------------------------ framing
def test_packets_match_the_app_captures():
    assert [p.hex() for p in ble_packets(Cmd.SAMPLE_SPECTRUM)] == ["01ba020000"]
    assert [p.hex() for p in ble_packets(Cmd.READ_TEMPERATURE)] == ["01ba040000"]
    assert [p.hex() for p in ble_packets(Cmd.SET_INDICATION_LED, bytes(9))] == ["01ba0b0900" + "00" * 9]


def test_long_payload_splits_15_then_19_with_sequence_bytes():
    payload = bytes(range(40))
    packets = ble_packets(Cmd.READ_FILE_HEADER, payload)
    assert [len(p) for p in packets] == [20, 20, 7]
    assert [p[0] for p in packets] == [1, 2, 3]
    assert packets[0][5:] + packets[1][1:] + packets[2][1:] == payload


def test_scan_sized_messages_reassemble_back_to_back():
    dark, sample = bytes(range(256)) * 7 + bytes(8), bytes([7]) * 1800
    packets = ble_packets(Cmd.SAMPLE_SPECTRUM, dark) + ble_packets(Cmd.SAMPLE_SPECTRUM, sample)
    assert len(packets) == 190 and len(packets[94]) == 1 + 18   # 95 packets, 18 bytes last
    r = BleReassembler()
    out = [m for p in packets for m in r.feed(p)]
    assert [m.data for m in out] == [dark, sample]
    assert all(m.command == Cmd.SAMPLE_SPECTRUM and m.length == 1800 for m in out)
    assert not r.in_progress


def test_zero_length_response_completes_at_once():
    assert BleReassembler().feed(bytes.fromhex("01ba9a0000"))[0].data == b""


def test_sequence_gap_raises_with_partial_data():
    packets = ble_packets(Cmd.READ_BLE_ID, bytes(range(60)))
    r = BleReassembler()
    r.feed(packets[0])
    with pytest.raises(ScioProtocolError) as e:
        r.feed(packets[2])
    assert e.value.partial == bytes(range(15))
    assert not r.in_progress


def test_bad_packets_rejected():
    with pytest.raises(ScioProtocolError):
        BleReassembler().feed(bytes(21))
    with pytest.raises(ScioProtocolError):
        BleReassembler().feed(bytes.fromhex("02ba040000"))


# ------------------------------------------------------------------ session
def _ble_id_payload():
    data = bytearray(130)
    data[0:8] = bytes.fromhex("01665900004c99b4")
    data[8:10] = struct.pack("<H", 125)
    data[50:56] = b"myScio"
    tag = b"20150812-e:PRODUCTION"
    data[66:66 + len(tag)] = tag
    return bytes(data)


def _device_id_payload(fw=153):
    data = bytearray(26)
    data[0:8] = bytes(range(8))
    data[16:24] = bytes(range(16, 24))
    data[24:26] = struct.pack("<H", fw)
    return bytes(data)


SCAN = [bytes([1]) * 1800, bytes([2, 0, 0, 0]) + bytes([2]) * 1796, bytes([3]) * 1656]


class FakeClient:
    """Answers each complete request with the device's replies, split into notifications."""

    def __init__(self, replies, silent=()):
        self.replies = replies
        self.silent = set(silent)
        self.callbacks = {}
        self.writes = []
        self.is_connected = False
        self.request = BleReassembler()   # requests use the same framing as replies
        self.services = SimpleNamespace(
            get_service=lambda uuid: object() if uuid == protocol.BLE_SERVICE_UUID else None)

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def start_notify(self, uuid, callback):
        self.callbacks[uuid] = callback

    async def stop_notify(self, uuid):
        self.callbacks.pop(uuid, None)

    async def write_gatt_char(self, uuid, data, response=False):
        assert uuid == protocol.BLE_CONTROL_UUID and len(data) <= 20
        self.writes.append((bytes(data), response))
        for req in self.request.feed(bytes(data)):
            if req.command in self.silent:
                continue
            for reply in self.replies[req.command]:
                for packet in ble_packets(req.command, reply):
                    self.callbacks[protocol.BLE_REPORTER_UUID](None, bytearray(packet))


def _open(monkeypatch, client, **kw):
    dev_entry = SimpleNamespace(address="B4:99:4C:59:66:01")

    async def discover(timeout):
        return [(SimpleNamespace(address="00:11:22:33:44:55"), "Headphones", -40, []),
                (dev_entry, "myScio", -60, [])]

    monkeypatch.setattr(ble, "_discover", discover)
    monkeypatch.setattr(ble.ScioBLE, "_make_client", lambda self, target: client)
    d = ble.ScioBLE(**kw)
    d.SLEEP_BETWEEN_COMMANDS = 0
    return d.open()


REPLIES = {
    Cmd.READ_DEVICE_ID: [_device_id_payload()],
    Cmd.READ_BLE_ID: [_ble_id_payload()],
    Cmd.READ_TEMPERATURE: [bytes.fromhex("940100004D0A000000000000")],
    Cmd.SAMPLE_SPECTRUM: SCAN,
}


def test_session_reads_identity_and_a_three_blob_scan(monkeypatch):
    client = FakeClient(REPLIES)
    with _open(monkeypatch, client) as d:
        assert d.address == "B4:99:4C:59:66:01" and d.name == "myScio"
        assert d.transport_name == "ble"
        info = d.read_device_info()
        assert info["ble_id"] == "01665900004c99b4" and info["ble_fw_version"] == 125
        assert info["i2s_tag_config"] == "20150812-e:PRODUCTION" and info["firmware_version"] == 153
        assert round(d.read_temperature()["cmos_t"], 2) == 20.42
        scan = d.sample_spectrum(info["firmware_version"])
    assert [len(scan["blobs"][k]) for k in ("sample_dark", "sample", "sample_gradient")] == [1800, 1800, 1656]
    assert scan["status_word"] == 2
    # every request starts at sequence 1 and is written with response
    assert all(w[0][0] == 1 and w[1] is True for w in client.writes)
    assert client.is_connected is False


def test_missing_response_times_out(monkeypatch):
    client = FakeClient(REPLIES, silent={Cmd.READ_TEMPERATURE})
    with _open(monkeypatch, client, timeout=0.2) as d:
        with pytest.raises(ScioTimeout):
            d.read_temperature()


def test_write_guard_still_applies(monkeypatch):
    client = FakeClient(REPLIES)
    with _open(monkeypatch, client) as d:
        with pytest.raises(PermissionError):
            d.reset_device()
        with pytest.raises(PermissionError):
            d._command(Cmd.PARAMETER_SET, bytes(4))
    assert client.writes == []


def test_not_advertising_is_a_clear_error(monkeypatch):
    with pytest.raises(ble.ScioNotFound):
        _open(monkeypatch, FakeClient(REPLIES), device="AA:BB:CC:DD:EE:FF")


def _late_reply_after_next_write(client, cmd):
    """Make *cmd*'s late reply land after the next request is sent, before its own reply.

    That is the dangerous order: the stale frame is first in line for the reader.
    """
    orig = client.write_gatt_char

    async def late_then_own(uuid, data, response=False):
        for packet in ble_packets(cmd, REPLIES[cmd][0]):
            client.callbacks[protocol.BLE_REPORTER_UUID](None, bytearray(packet))
        client.write_gatt_char = orig
        await orig(uuid, data, response)
    client.write_gatt_char = late_then_own


def test_late_reply_to_a_timed_out_request_is_never_returned_for_the_next(monkeypatch):
    client = FakeClient(REPLIES, silent={Cmd.READ_TEMPERATURE})
    with _open(monkeypatch, client, timeout=0.3) as d:
        with pytest.raises(ScioTimeout):
            d.read_temperature()
        client.silent = set()
        _late_reply_after_next_write(client, Cmd.READ_TEMPERATURE)
        info = d.read_device_info()          # the stale temperature reply lands first
        assert info["firmware_version"] == 153 and info["i2s_tag_config"]
        assert d.stale_replies == 1


def test_stale_scan_message_cannot_be_paired_with_a_new_scan(monkeypatch):
    client = FakeClient(REPLIES)
    with _open(monkeypatch, client) as d:
        _late_reply_after_next_write(client, Cmd.READ_TEMPERATURE)
        scan = d.sample_spectrum(153)
    assert [scan["blobs"][k] for k in ("sample_dark", "sample", "sample_gradient")] == SCAN
    assert d.stale_replies == 1


def test_stray_tail_packets_do_not_fail_the_next_command(monkeypatch):
    client = FakeClient(REPLIES)
    with _open(monkeypatch, client) as d:
        for packet in ble_packets(Cmd.READ_BLE_ID, bytes(130))[3:]:   # tail of an old reply
            client.callbacks[protocol.BLE_REPORTER_UUID](None, bytearray(packet))
        assert round(d.read_temperature()["cmos_t"], 2) == 20.42
        assert d.stray_packets == 5


def test_reply_starting_mid_message_keeps_the_new_reply(monkeypatch):
    client = FakeClient(REPLIES)
    with _open(monkeypatch, client) as d:
        orig = client.write_gatt_char

        async def lose_a_packet_first(uuid, data, response=False):
            # half of an old 0x84 reply arrives (its tail is lost) just before ours
            client.callbacks[protocol.BLE_REPORTER_UUID](
                None, bytearray(ble_packets(Cmd.READ_BLE_ID, bytes(130))[0]))
            await orig(uuid, data, response)
        client.write_gatt_char = lose_a_packet_first
        assert round(d.read_temperature()["cmos_t"], 2) == 20.42   # own reply survives
        assert d.stale_replies == 1                                 # old loss was dropped


def test_data_loss_in_our_own_reply_is_raised(monkeypatch):
    client = FakeClient(REPLIES)
    with _open(monkeypatch, client) as d:
        orig = client.write_gatt_char

        async def drop_second_packet(uuid, data, response=False):
            client.callbacks_backup = client.callbacks[protocol.BLE_REPORTER_UUID]
            sent = []
            client.callbacks[protocol.BLE_REPORTER_UUID] = lambda s, p: sent.append(bytes(p))
            await orig(uuid, data, response)
            client.callbacks[protocol.BLE_REPORTER_UUID] = client.callbacks_backup
            for i, p in enumerate(sent):
                if i != 1:
                    client.callbacks_backup(None, bytearray(p))
        client.write_gatt_char = drop_second_packet
        with pytest.raises(ScioProtocolError):
            d._command(Cmd.READ_BLE_ID)


def test_reconnect_after_the_link_drops(monkeypatch):
    client = FakeClient(REPLIES)
    d = _open(monkeypatch, client)
    try:
        d._on_disconnect(client)
        client.is_connected = False
        assert d.is_connected is False
        with pytest.raises(ble.ScioDisconnected):
            d.read_temperature()             # fails fast, does not write to a dead link
        d.open()                             # reconnects instead of returning early
        assert d.is_connected
        assert round(d.read_temperature()["cmos_t"], 2) == 20.42
    finally:
        d.close()


def test_disconnect_is_reported(monkeypatch):
    client = FakeClient(REPLIES, silent={Cmd.READ_TEMPERATURE})
    with _open(monkeypatch, client, timeout=5) as d:
        d._on_disconnect(client)
        with pytest.raises(ble.ScioDisconnected):
            d.read_temperature()


# ------------------------------------------------------- session takeover
@pytest.fixture(autouse=True)
def _no_leaked_sessions():
    yield
    ble.close_all()


SCIO_A = ("B4:99:4C:59:66:01", "SCiOmyScio")
SCIO_B = ("AA:BB:CC:00:11:22", "SCiOother")


class _Radio:
    """Fake air: each session gets its own client; a held SCiO stops advertising."""

    def __init__(self, monkeypatch, devices=(SCIO_A,)):
        self.devices = list(devices)
        self.clients = []
        radio = self

        self.scans = 0

        async def discover(timeout):
            radio.scans += 1
            held = {c.address for c in radio.clients if c.is_connected}
            return [(SimpleNamespace(address=a), n, -60, []) for a, n in radio.devices if a not in held]

        def make_client(session, target):
            client = FakeClient(REPLIES)
            client.address = target.address
            radio.clients.append(client)
            return client

        monkeypatch.setattr(ble, "_discover", discover)
        monkeypatch.setattr(ble.ScioBLE, "_make_client", make_client)

    def session(self, device=None):
        d = ble.ScioBLE(device, timeout=2)
        d.SLEEP_BETWEEN_COMMANDS = 0
        return d


def test_rerun_cell_takes_over_the_session_left_open(monkeypatch, capsys):
    radio = _Radio(monkeypatch)
    d1 = radio.session().open()
    d2 = radio.session().open()            # d1 never closed: the notebook re-run case
    assert "closed an earlier ScioBLE connected to B4:99:4C:59:66:01" in capsys.readouterr().out
    assert d2.is_connected and not d1.is_connected
    assert d2.read_device_info()["i2s_tag_config"]
    with pytest.raises(ble.ScioDisconnected):
        d1.read_temperature()
    assert ble._SESSIONS == {d2}


def test_takeover_by_explicit_address_and_by_name(monkeypatch):
    radio = _Radio(monkeypatch)
    d1 = radio.session().open()
    d2 = radio.session("b4:99:4c:59:66:01").open()   # case-insensitive address
    d3 = radio.session("SCiOmyScio").open()          # and by advertised name
    assert d3.is_connected and not d1.is_connected and not d2.is_connected


def test_session_for_another_device_is_left_alone(monkeypatch, capsys):
    radio = _Radio(monkeypatch, devices=(SCIO_A, SCIO_B))
    other = radio.session(SCIO_B[0]).open()
    mine = radio.session(SCIO_A[0]).open()           # A is advertising: no takeover
    assert other.is_connected and mine.is_connected
    assert "closed an earlier" not in capsys.readouterr().out
    radio.devices = [SCIO_B]                         # A switched off; only B is held
    with pytest.raises(ble.ScioNotFound):
        radio.session(SCIO_A[0]).open()
    assert other.is_connected                        # still not closed


def test_no_holder_means_a_clear_not_found_message(monkeypatch):
    _Radio(monkeypatch, devices=())
    with pytest.raises(ble.ScioNotFound, match="another program or notebook kernel"):
        ble.ScioBLE().open()
    assert ble._SESSIONS == set()                    # a failed open() leaves nothing behind


def test_close_and_close_all_empty_the_registry(monkeypatch):
    radio = _Radio(monkeypatch, devices=(SCIO_A, SCIO_B))
    a = radio.session(SCIO_A[0]).open()
    b = radio.session(SCIO_B[0]).open()
    assert ble._SESSIONS == {a, b}
    a.close()
    assert ble._SESSIONS == {b}
    assert ble.close_all() == 1 and ble._SESSIONS == set() and not b.is_connected


def test_named_takeover_skips_the_scan_that_cannot_succeed(monkeypatch):
    radio = _Radio(monkeypatch)
    radio.session(SCIO_A[0]).open()
    radio.scans = 0
    d2 = radio.session(SCIO_A[0]).open()     # named and held here: no pointless first scan
    assert d2.is_connected and radio.scans == 1
    radio.scans = 0
    d3 = radio.session().open()              # unnamed: must scan first (another SCiO may answer)
    assert d3.is_connected and radio.scans == 2
