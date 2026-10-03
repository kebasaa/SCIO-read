"""Read-only USB metadata, with bounded optional captures and no parameter writes."""
import argparse
import base64
import time
from pathlib import Path
import _bootstrap
from scio.usb import ScioUSB,find_scio_ports
from scio.protocol import Cmd
from scio_offline import research as r


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True,type=Path); p.add_argument('--captures',type=int,default=0); p.add_argument('--wait-seconds',type=int,default=0)
    a=p.parse_args()
    if not 0<=a.captures<=6: raise ValueError('capture budget is 0..6')
    if not 0<=a.wait_seconds<=120: raise ValueError('wait budget is 0..120 seconds')
    if not a.output.resolve().is_relative_to(r.DEV): raise ValueError('output must be below dev')
    if a.output.exists(): raise FileExistsError('choose a new evidence filename')
    ports=[x for x in find_scio_ports() if x['is_scio']]
    deadline=time.monotonic()+a.wait_seconds
    while not ports and time.monotonic()<deadline:
        time.sleep(2); ports=[x for x in find_scio_ports() if x['is_scio']]
    if len(ports)!=1: raise RuntimeError('requires exactly one detected SCIO port')
    rows=[]
    with ScioUSB(ports[0]['device'],timeout=3) as device:
        info=device.read_device_info()
        for name,call in [('ble_id_raw',lambda:device.raw_command(Cmd.READ_BLE_ID)[0].data.hex()),
                          ('file_list',device.read_file_list),('file_headers',device.read_all_file_headers),
                          ('temperature',device.read_temperature),('battery',device.read_battery),
                          ('ble_config',lambda:device.raw_command(Cmd.READ_BLE)[0].data.hex()),
                          ('ble_status',lambda:device.raw_command(Cmd.READ_BLE_STATUS)[0].data.hex())]:
            try: rows.append({'query':name,'result':call()})
            except Exception as exc: rows.append({'query':name,'error_type':type(exc).__name__})
        captures=[]
        for i in range(a.captures):
            scan=device.sample_spectrum(info.get('firmware_version',0))
            captures.append({'status_word':scan['status_word'],'blobs_b64':{k:base64.b64encode(v).decode() for k,v in scan['blobs'].items()}})
            r.write_new(a.output.parent/(a.output.stem+'_captures')/f'{i:02d}.json',{'device':info,**captures[-1]})
            print('Captured',i+1,'of',a.captures,flush=True)
    r.write_new(a.output,{'device':info,'queries':rows,'captures':captures,
                        'limits':'Only allowlisted read/capture commands. No firmware, parameter, calibration or protection changes.'})
    print('SCIO connected; firmware',info.get('firmware_version'),'queries',len(rows),'captures',len(captures))


if __name__=='__main__':main()
