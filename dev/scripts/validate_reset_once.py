"""Explicitly authorized single reset, with durable before/after read evidence.

No timer, parameter, firmware, or calibration writes. Readback covers a subset,
not a guarantee about every setting or calibration body.
"""
import argparse
import time
from pathlib import Path
import _bootstrap
from scio import protocol, power
from scio.usb import ScioUSB, find_scio_ports
from scio_offline import research as r


def snapshot(device):
    result = {}
    for name, command, payload in [
        ('identity', 1, b''), ('timer', 0x9b, b''),
        *[(f'file_{i}', 0x87, i.to_bytes(4, 'little')) for i in (100,101,102,103)],
    ]:
        resp = device.raw_command(command, payload)[0]
        if resp.command != command:
            raise ValueError('unexpected response opcode')
        if name == 'identity':
            parsed = {'firmware_version': protocol.parse_device_id(resp.data)['firmware_version']}
        elif name == 'timer':
            parsed = power.parse_power_saver(resp.data)
        else:
            if len(resp.data) != 16:
                raise ValueError('unexpected file-header length')
            parsed = protocol.parse_file_header(resp.data)
        result[name] = {'sha256': r.sha(resp.data), 'bytes': len(resp.data), **parsed}
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--authorize-single-reset', action='store_true', required=True)
    a = p.parse_args()
    out = a.output_dir.resolve()
    if not out.is_relative_to(r.DEV) or out.exists():
        raise ValueError('requires a new directory under dev')
    ports = [x for x in find_scio_ports() if x['is_scio']]
    if len(ports) != 1:
        raise RuntimeError('requires exactly one SCIO port')
    reset = {'command': 0x83, 'payload_hex': '', 'maximum_attempts': 1}
    with ScioUSB(ports[0]['device'], timeout=3) as device:
        before = snapshot(device)  # Any failure aborts before resetting.
        r.write_new(out / 'before.json', before)
        r.write_new(out / 'reset_intent.json', reset)
        print('Baseline saved; issuing one reset, no timer write.', flush=True)
        try:
            response = device.reset_device(allow_write=True)
            reset['response'] = {'command': response.command, 'bytes': len(response.data),
                                 'sha256': r.sha(response.data)}
        except Exception as exc:
            reset['error_type'] = type(exc).__name__
            reset['warning'] = 'No response does not prove reset failed; never resent.'
        finally:
            r.write_new(out / 'reset_result.json', reset)
    # Bounded reconnect/read attempts only; never send a second reset.
    after = None
    attempts = []
    for attempt in range(3):
        time.sleep(3)
        ports = [x for x in find_scio_ports() if x['is_scio']]
        if len(ports) != 1:
            attempts.append({'attempt': attempt + 1, 'detected_devices': len(ports)})
            continue
        try:
            with ScioUSB(ports[0]['device'], timeout=3) as device:
                after = snapshot(device)
            r.write_new(out / 'after.json', after)
            attempts.append({'attempt': attempt + 1, 'readback_completed': True})
            break
        except Exception as exc:
            attempts.append({'attempt': attempt + 1, 'error_type': type(exc).__name__})
    compared = {k: before[k]['sha256'] == after[k]['sha256'] for k in before} if after else {}
    report = {'reset_attempts': 1, 'timer_writes': 0, 'reconnect_attempts': attempts,
              'after_available': after is not None, 'unchanged_fields': compared,
              'limits': 'Readback covers identity, timer and four calibration headers, not every setting or file body. Does not test remote power-on or immediate-off. Unchanged fields alone cannot prove a reset physically occurred.'}
    r.write_new(out / 'comparison.json', report)
    print('After available:', after is not None, 'unchanged checks:', compared)


if __name__ == '__main__':
    main()
