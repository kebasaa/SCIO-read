"""Bounded USB power-saver read with awake controls; never writes device settings."""
import argparse
from pathlib import Path
import _bootstrap
from scio import power, protocol
from scio.usb import ScioUSB, find_scio_ports
from scio_offline import research as r


def run_probe(device):
    rows = []
    controls = []
    for name, command in [('control_before', protocol.Cmd.READ_DEVICE_ID),
                          ('power_saver', protocol.Cmd.READ_BLE),
                          ('control_after', protocol.Cmd.READ_DEVICE_ID)]:
        row = {'query': name, 'command': command}
        try:
            response = device.raw_command(command)[0]
            row.update(response_command=response.command, bytes=len(response.data),
                       sha256=r.sha(response.data))
            if response.command != command:
                raise ValueError('unexpected response command')
            if name.startswith('control'):
                identity = protocol.parse_device_id(response.data)
                row['firmware_version'] = identity['firmware_version']
                controls.append(r.sha(response.data))
            else:
                row['timer'] = power.parse_power_saver(response.data)
            row['valid'] = True
        except Exception as exc:
            row.update(valid=False, error_type=type(exc).__name__)
        rows.append(row)
        if name == 'control_before' and not row['valid']:
            break  # No blind requests to a device that is not demonstrably answering.
    control_ok = len(controls) == 2 and controls[0] == controls[1]
    return {'queries': rows, 'matching_awake_controls': control_ok,
            'timer_read_with_controls': control_ok and any(
                x['query'] == 'power_saver' and x['valid'] for x in rows),
            'limits': 'Read-only ID/timer/ID sequence, no retries or scans. Identity bytes are hashed, not exported. Valid read does not validate setting writes, power-off timing, reset, or wake behavior.'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--live', action='store_true')
    a = p.parse_args()
    output = a.output.resolve()
    if not output.is_relative_to(r.DEV):
        raise ValueError('output must be under dev')
    if output.exists():
        raise FileExistsError('choose a new output file')
    if not a.live:
        r.write_new(output, {'plan': ['READ_DEVICE_ID', 'READ_BLE', 'READ_DEVICE_ID'],
                             'writes': False, 'requests_maximum': 3,
                             'requires': 'Exactly one awake SCIO USB device; --live is explicit.'})
        return
    ports = [x for x in find_scio_ports() if x['is_scio']]
    if len(ports) != 1:
        raise RuntimeError('requires exactly one detected SCIO')
    with ScioUSB(ports[0]['device'], timeout=3) as device:
        result = run_probe(device)
    r.write_new(output, result)
    print('queries', len(result['queries']), 'matching controls', result['matching_awake_controls'],
          'timer read', result['timer_read_with_controls'])


if __name__ == '__main__':
    main()
