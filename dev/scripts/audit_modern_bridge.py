"""Hash reviewed exact-APK paths without exporting full decompiled sources."""
import argparse
import io
from pathlib import Path
import zipfile
import _bootstrap
from scio_offline import research as r

NODES = [
('android/scioconnection/services/SCiOBLeService.java', 'this.responseCommandParser.add(bArr);',
 'Reporter characteristic bytes are passed directly to the response parser.'),
('android/scioconnection/protocol/ResponseCommandParser.java', 'this.overallLength = (bArr[3] & 255) | ((bArr[4] & 255) << 8);',
 'BLE first packet: sequence byte 1, marker 0xBA, command, U16LE payload length, then up to 15 payload bytes. Subsequent packets contribute up to 19 bytes after sequence. No payload decompression/decryption in this parser.'),
('android/scioconnection/protocol/ResponseCommandParser.java', 'responseCommand.setData(bArr);',
 'Reassembled payload bytes become ResponseCommand.data without stripping the scan-specific header.'),
('android/scioconnection/protocol/ResponseCommand.java', 'return Base64.encodeToString(this.data, 0);',
 'The exact modern APK directly Base64-encodes the entire response payload.'),
('android/sdk/sciosdk/ScioInternalDevice.java', 'String dataAsBase65 = linkedList.get(0).getDataAsBase64();',
 'Scan completion assigns response 0 to dark and response 1 to sample; optional response 2 is gradient. Sample U32 at offset zero is separately read as status, but remains in the Base64 payload.'),
('android/sdk/model/ScioInternalReading.java', 'this.sampleGradient = str3;',
 'Constructor keeps all three strings; associates device ID/i2s metadata and last white reference separately.'),
('android/sdk/model/ScioReading.java', 'this.sample = scioInternalReading.getSample();',
 'Public reading copies sample/dark/gradient and metadata unchanged. Constructor does not copy the separate status field; verified in fallback output too.'),
('scio_sdk/model/ScioReadingModel.java', 'return new ScioReadingModel(scioReading.getSample(), scioReading.getDarkSample(), scioReading.getSampleGradient(), scioReading.getTimestamp());',
 'Flutter bridge model copies strings to sample/sampleDark/sampleGradient plus timestamp; no separate status property.'),
('scio_sdk/model/ScanResultModel.java', 'return new ObjectMapper().writeValueAsString(this);',
 'Scan result serializes type and nullable reading as JSON, without numerical processing.'),
('scio_sdk/ScioSdkPlugin.java', 'return ScanResultModel.toJson(str, scioReading);',
 'Scan success callback passes the JSON result through pending MethodChannel.Result.success; scanLightOff is separately emitted as an event. Do not conflate method result with event channel.'),
('scio_sdk/model/ScioDeviceModel.java', 'this.calibrationReading = scioReadingModel;',
 'Device JSON has separate calibrationReading and whiteReference models plus id/i2s/firmware fields; the two reading concepts are not interchangeable.'),
('android/common/model/FirmwareUpgradeModel.java', 'return Arrays.copyOfRange(rawData, 4, rawData.length);',
 'Firmware file strings decode via Base64; first four decoded bytes are exposed separately as checksum, remainder as transfer body. This class contains no recovered firmware body or checksum algorithm.'),
('android/scioconnection/protocol/FirmwareFiles.java', 'deadPixelsIndices(100),',
 'Exact modern APK retains file enum ble=89, dsp_boot=90, dsp_dec=91, dsp_op=92, deadPixelsIndices=100, centers=101, bins=102, nPixelsPerBin=103.'),
('scio_sdk/ScioSdkPlugin.java', 'int iIntValue = ((Integer) methodCall.argument("seconds")).intValue();',
 'Modern Flutter shutdown-timeout write explicitly accepts seconds, not minutes.'),
('android/sdk/sciosdk/ScioInternalDevice.java', 'this.scioServiceConnection.getScioService().performWriteBle(((Integer) task.data).intValue(), new AnonymousClass27(task));',
 'Modern writeBle task forwards the supplied integer without the older UI minute-to-second adjustment.'),
('android/scioconnection/services/SCiOBLeService.java', 'responseCommandHandler.setRequestedCommandData(new byte[]{0, 0, (byte) i, (byte) (i >>> 8)});',
 'Writes timeout as 00 00 plus low 16 bits little-endian under WRITE_BLE (0x9A). Older signed-byte UI adjustment is not established as a firmware requirement. No write was tested.'),
('android/sdk/sciosdk/mock/ScioMockDevice.java', 'private static final String I2STAG = "20150812-o:PRODUCTION";',
 'Mock constants: ID 503E5732B5EF1F35, address D0:B5:C2:97:83:42, BLE ID bleId, i2s 20150812-o:PRODUCTION, firmware 128, RSSI -31, temperatures 25, battery values 100/100/100/100/37. Reads assets/mock/{scan,wr}-{sample,dark,gradient}. These do not identify the connected device or separate Flutter fixture, and are not evidence of a cryptographic key.'),
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--apps', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = r.DEV/'private/analyzer_1_5_6_java/sources/com/consumerphysics'
    rows = []
    for name, anchor, observation in NODES:
        path = root/name
        raw = path.read_bytes()
        lines = raw.decode('utf-8').splitlines()
        matches = [i for i,line in enumerate(lines,1) if anchor in line]
        if not matches:
            raise ValueError('Missing anchor: '+name)
        rows.append({'source':name, 'sha256':r.sha(raw), 'lines':matches,
                     'anchor':anchor, 'observation':observation})
    fallback = r.DEV/'private/analyzer_1_5_6_fallback/ScioReading.java'
    raw = fallback.read_bytes()
    constructor = raw.decode().split('public ScioReading(',1)[1].split('private void readObject',1)[0]
    if '.status =' in constructor or 'getStatus()' in constructor:
        raise ValueError('Status-copy omission hypothesis contradicted')
    archive = a.apps/'apk/SCiO+Analyzer_1.5.6_APKPure.xapk'
    assets = []
    with zipfile.ZipFile(archive) as outer:
        for member in sorted(outer.namelist()):
            if not member.endswith('.apk'):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(member))) as apk:
                for name in sorted(apk.namelist()):
                    if name.startswith('assets/mock/'):
                        data = apk.read(name)
                        assets.append({'member':member+'!'+name,'bytes':len(data),'sha256':r.sha(data)})
    native = []
    for name, meaning in [
        ('6ce400.txt','At 0x6ce4ac reads spectrum from a map, checks nullable List, maps with double type and closure at 0x6cf004. Source is a parsed response-like object; network caller not yet established.'),
        ('6cf004.txt','Closure checks input is num then dispatches one numeric method. No raw triplet input or wavelength reconstruction in this closure. toDouble interpretation is consistent with caller type but dispatch table not independently resolved.')]:
        path = r.DEV/'private/native_ranges'/name
        native.append({'source':r.label(path),'sha256':r.sha(path.read_bytes()),'observation':meaning})
    r.write_new(a.output, {'schema':1, 'scope':'Exact supplied Analyzer 1.5.6 XAPK; input hashes in modern_dex_inputs.json',
        'decompiler_result':{'exit_code':1,'reported_error_count':161,
                            'limits':'Whole-APK decompilation completed with errors. Inspected methods are narrower evidence; not exhaustive coverage.'},
        'observations':rows, 'fallback_status_check':{'sha256':r.sha(raw),'constructor_copies_status':False},
        'mock_asset_inventory':assets,'native_spectrum_observations':native,
        'conclusion':'Inspected Android producer path is BLE framing -> whole-payload Base64 -> copied strings -> JSON MethodChannel result. No numerical decode or cryptographic transform recovered. Encryption/compression remain unresolved.'})
    print('Reviewed Java observations:',len(rows),'mock assets:',len(assets))


if __name__ == '__main__':
    main()
