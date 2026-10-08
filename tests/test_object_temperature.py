from scio import protocol
from scio.device import ScioDevice


def test_read_object_temperature_returns_obj_t():
    class _Dev:
        def read_temperature(self):
            return {"obj_t": 32.63, "cmos_t": 21.1, "chip_t": 26.65}
    assert ScioDevice.read_object_temperature(_Dev()) == 32.63


def test_parse_temperature_obj_word():
    # skin reading from the fw-138 unit: w2 = 0x0cbf = 3263 -> 32.63 degC
    t = protocol.parse_temperature(bytes.fromhex("95010000690a0000bf0c0000"))
    assert round(t["obj_t"], 2) == 32.63
    # fw-147 reference unit reports 0 for the object word
    t0 = protocol.parse_temperature(bytes.fromhex("940100004d0a000000000000"))
    assert t0["obj_t"] == 0.0
