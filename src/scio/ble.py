"""Bluetooth LE transport for the SCiO, read-only / capture by default.

The command set and responses are the same as over USB; only the framing
differs (see :func:`scio.protocol.ble_packets` and
:class:`scio.protocol.BleReassembler`). Everything here follows the decompiled
app (``SCiOBLeService``, ``RequestCommandBuilder``, ``ResponseCommandParser``):

* vendor service ``3490``: commands are written to ``3492`` (control), replies
  arrive as notifications on ``3491`` (reporter), button presses on ``3493``;
* no bonding, no MTU request: packets are at most 20 bytes;
* writes go with response, except READY_FOR_WR, CLEAR_READY_FOR_WR and
  FILE_DOWNLOAD.

`bleak <https://github.com/hbldh/bleak>`_ does the radio work (WinRT on
Windows, BlueZ over D-Bus on Linux). bleak is asyncio-only, so :class:`ScioBLE`
runs its own event loop in a background thread and offers the same synchronous
interface as :class:`scio.usb.ScioUSB`; it therefore also works inside Jupyter,
whose own loop is already running. bleak is imported only when a BLE function is
used, so the rest of the package does not need it.

The device only advertises while it is awake: press its button first.
"""

from __future__ import annotations

import asyncio
import queue
import threading
from concurrent.futures import TimeoutError as _FutureTimeout

from . import protocol
from .device import ScioDevice
from .protocol import Cmd, ScioProtocolError, ScioTimeout

__all__ = ["ScioBLE", "find_scio_ble", "ScioNotFound", "ScioDisconnected",
           "ScioTimeout", "ScioProtocolError"]


class ScioNotFound(LookupError):
    """No matching SCiO is advertising."""


class ScioDisconnected(ScioTimeout):
    """The BLE link dropped while a response was awaited."""


_DISCONNECTED = object()


def _bleak():
    try:
        import bleak
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise ImportError("BLE needs the 'bleak' package: pip install bleak") from e
    return bleak


def _is_scio(name: str | None, service_uuids=()) -> bool:
    if name and "scio" in name.lower():
        return True
    return protocol.BLE_SERVICE_UUID in {u.lower() for u in service_uuids or ()}


async def _discover(timeout: float) -> list[tuple]:
    """Return ``(device, name, rssi, service_uuids)`` for every advertiser."""
    bleak = _bleak()
    found = await bleak.BleakScanner.discover(timeout=timeout, return_adv=True)
    out = []
    for device, adv in found.values():
        out.append((device, adv.local_name or device.name, adv.rssi,
                    list(adv.service_uuids or ())))
    return out


class _LoopThread:
    """A private asyncio loop on a daemon thread; ``run`` blocks for a result."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever,
                                       name="scio-ble", daemon=True)
        self.thread.start()

    def run(self, coro, timeout: float | None = None):
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return fut.result(timeout)
        except _FutureTimeout:
            fut.cancel()
            raise ScioTimeout(f"BLE operation timed out after {timeout} s") from None

    def stop(self):
        if self.loop.is_closed():
            return
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        if not self.thread.is_alive():
            self.loop.close()


def find_scio_ble(timeout: float = 5.0) -> list[dict]:
    """Scan for BLE advertisers, likely SCiO devices first.

    A device counts as a SCiO when its name contains "scio" (case-insensitive;
    the app accepts names starting with "SCiO", and units can be renamed, e.g.
    "myScio") or it advertises the SCiO service.
    """
    runner = _LoopThread()
    try:
        found = runner.run(_discover(timeout), timeout + 10)
    finally:
        runner.stop()
    out = [{"address": d.address, "name": name, "rssi": rssi,
            "is_scio": _is_scio(name, uuids)} for d, name, rssi, uuids in found]
    out.sort(key=lambda d: (not d["is_scio"], -(d["rssi"] or -999)))
    return out


class ScioBLE(ScioDevice):
    """SCiO BLE session, read-only unless a write is explicitly authorized.

    *device* is a BLE address (``"B4:99:4C:59:66:01"``; a UUID on macOS), an
    advertised name, or ``None`` for the strongest SCiO in range. Use it exactly
    like :class:`scio.usb.ScioUSB`::

        with ScioBLE() as dev:
            info = dev.read_device_info()
            scan = dev.sample_spectrum(info["firmware_version"])

    *timeout* bounds every response; *scan_timeout* replaces it while a scan's
    first response is awaited (the app allows 30 s per scan task).
    """

    transport_name = "ble"

    def __init__(self, device: str | None = None, timeout: float = 10.0,
                 scan_timeout: float = 30.0, discover_timeout: float = 5.0,
                 connect_timeout: float = 20.0):
        super().__init__()
        self.device = device
        self.timeout = timeout
        self.scan_timeout = scan_timeout
        self.discover_timeout = discover_timeout
        self.connect_timeout = connect_timeout
        self.address = None
        self.name = None
        self.client = None
        self._runner = None
        self._responses: queue.Queue = queue.Queue()
        self._reassembler = protocol.BleReassembler()
        self._lock = threading.Lock()
        self._button = threading.Event()
        self.button_presses = 0
        self._last_cmd = None

    # -- connection -------------------------------------------------------
    def _match(self, found: list[tuple]):
        if self.device is None:
            scio = [f for f in found if _is_scio(f[1], f[3])]
            scio.sort(key=lambda f: -(f[2] or -999))
            return scio[0] if scio else None
        want = self.device.lower()
        for f in found:
            if f[0].address.lower() == want or (f[1] or "").lower() == want:
                return f
        return None

    def _make_client(self, target):
        return _bleak().BleakClient(target, disconnected_callback=self._on_disconnect,
                                    timeout=self.connect_timeout)

    def open(self):
        if self.client is not None:
            return self
        self._responses = queue.Queue()
        self._reassembler.reset()
        self._runner = _LoopThread()
        try:
            found = self._runner.run(_discover(self.discover_timeout),
                                     self.discover_timeout + 10)
            match = self._match(found)
            if match is None:
                what = f"'{self.device}'" if self.device else "any SCiO"
                raise ScioNotFound(f"{what} is not advertising; press the device "
                                   f"button to wake it and try again")
            target, self.name = match[0], match[1]
            self.address = target.address
            self.client = self._make_client(target)
            self._runner.run(self._connect(), self.connect_timeout + 10)
        except BaseException:
            self.close()
            raise
        return self

    async def _connect(self):
        await self.client.connect()
        if self.client.services.get_service(protocol.BLE_SERVICE_UUID) is None:
            raise ScioProtocolError(f"{self.address} has no SCiO service "
                                    f"{protocol.BLE_SERVICE_UUID}")
        await self.client.start_notify(protocol.BLE_REPORTER_UUID, self._on_report)
        try:
            await self.client.start_notify(protocol.BLE_BUTTON_UUID, self._on_button)
        except Exception:  # the button is a convenience, never a reason to fail
            pass

    async def _disconnect(self):
        for uuid in (protocol.BLE_REPORTER_UUID, protocol.BLE_BUTTON_UUID):
            try:
                await self.client.stop_notify(uuid)
            except Exception:
                pass
        await self.client.disconnect()

    def close(self):
        if self.client is not None and self._runner is not None:
            try:
                self._runner.run(self._disconnect(), 10)
            except Exception:
                pass
        self.client = None
        if self._runner is not None:
            self._runner.stop()
            self._runner = None

    @property
    def is_connected(self) -> bool:
        return self.client is not None and bool(getattr(self.client, "is_connected", False))

    # -- notification callbacks (run on the loop thread) ------------------
    def _on_report(self, _sender, data: bytearray):
        with self._lock:
            try:
                done = self._reassembler.feed(bytes(data))
            except ScioProtocolError as e:
                done = [e]
        for item in done:
            self._responses.put(item)

    def _on_button(self, _sender, data: bytearray):
        if bytes(data)[:1] == b"\x01":
            self.button_presses += 1
            self._button.set()

    def _on_disconnect(self, _client):
        self._responses.put(_DISCONNECTED)

    def wait_for_button(self, timeout: float | None = None) -> bool:
        """Block until the device button is pressed; ``False`` on timeout."""
        self._button.clear()
        return self._button.wait(timeout)

    # -- framing ----------------------------------------------------------
    def _discard_input(self):
        with self._lock:
            self._reassembler.reset()
        while True:
            try:
                item = self._responses.get_nowait()
            except queue.Empty:
                break
            if item is _DISCONNECTED:  # keep a dropped link visible to the reader
                self._responses.put(item)
                break

    def send_frame(self, frame: bytes):
        """Send one ``[seq, 0xBA, cmd, len, payload]`` frame as BLE packets.

        The app always starts a request at sequence 1 (the USB session counter
        does not apply), so the frame is re-split rather than sent as-is.
        """
        if self.client is None:
            raise ScioDisconnected("not connected; call open() first")
        if len(frame) < 5 or frame[1] != protocol.PROTOCOL_MARKER:
            raise ValueError("not a SCiO command frame")
        cmd = frame[2]
        length = frame[3] | (frame[4] << 8)
        payload = bytes(frame[5:5 + length])
        response = cmd not in protocol.NO_RESPONSE_WRITE_COMMANDS
        self._last_cmd = cmd
        for packet in protocol.ble_packets(cmd, payload):
            self._runner.run(self.client.write_gatt_char(
                protocol.BLE_CONTROL_UUID, packet, response=response), self.timeout)

    def _read_response(self) -> protocol.Response:
        timeout = self.timeout
        if self._last_cmd == Cmd.SAMPLE_SPECTRUM:
            timeout = max(self.timeout, self.scan_timeout)
            self._last_cmd = None  # later messages of the same scan stream quickly
        try:
            item = self._responses.get(timeout=timeout)
        except queue.Empty:
            raise ScioTimeout(f"no BLE response within {timeout} s") from None
        if item is _DISCONNECTED:
            self._responses.put(item)
            raise ScioDisconnected("BLE connection lost")
        if isinstance(item, Exception):
            raise item
        return item
