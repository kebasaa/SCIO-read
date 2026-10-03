"""Hash reviewed cache/dataflow anchors without exporting cache values."""
import argparse
from pathlib import Path
import _bootstrap
from scio_offline import research as r


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=r.DEV/'private/lab_1_3_12_java/sources/com/consumerphysics'
    definitions=[
        ('common/model/ModelParser.java','optJSONObject("new_version")','Update payload map is read from new_version; names mapped with FirmwareFiles.valueOf.'),
        ('researcher/utils/Prefs.java','editorEdit.putString(firmwareFiles.toString(), firmwareUpgradeModel.getData(firmwareFiles))','Payloads stored under bare enum names; per-user firmware.file.names indexes the keys.'),
        ('researcher/utils/Prefs.java','editorEdit.remove(getUserEmail() + ".firmware.file.names")','Null update model removes index only, not old bare-name strings.'),
        ('android/sdk/config/ScioDevicePreferences.java','public ScioDevicePreferences setScioFileVersions','ScioFirmwareFiles stores version metadata, not update-body data.'),
        ('android/sdk/sciosdk/ScioInternalDevice.java','setScioFileVersions(jSONArray.toString())','Producer constructs JSON key/value entries from file-list response before storing version metadata.'),
        ('android/sdk/sciosdk/ScioInternalDevice.java','long u32 = responseCommand.getU32(12)','Read-header callback exposes checksum word at offset 12, not file body.'),
        ('researcher/activities/FirmwareUpgradeActivity.java','this.localChecksums.put','localChecksums gets U32LE from supplied four-byte prefix; not a checksum over body computed by the app.'),
        ('researcher/activities/FirmwareUpgradeActivity.java','map.get("dead_pixels_indices_checksum").equals','Downloaded table prefixes compared with device header words for IDs 100..103.'),
        ('researcher/activities/FirmwareUpgradeActivity.java','int i = this.upgradeState.currentMessage * 192','Firmware transfer splits body into messages of at most 192 bytes; host-to-device path, not extraction command.'),
    ]
    rows=[]
    for relative,needle,claim in definitions:
        path=root/relative;data=path.read_bytes();lines=data.decode().splitlines()
        matches=[i for i,line in enumerate(lines,1) if needle in line]
        if not matches:raise ValueError('evidence anchor missing: '+relative)
        rows.append({'source':relative,'sha256':r.sha(data),'lines':matches,'finding':claim})
    r.write_new(a.output,{'observations':rows,
        'correction':'Earlier RECOVERY_STATUS cache handoff conflated ScioFirmwareFiles metadata with actual bodies and overstated deletion on completion. Corrected in place; earlier immutable reports preserved.',
        'limits':'Exact Lab APK partial JADX output; targeted methods reviewed. No firmware body, checksum algorithm, table values, decompression or decryption recovered. No endpoint calls or device writes.'})
    print('Recorded anchors:',len(rows))


if __name__=='__main__':main()
