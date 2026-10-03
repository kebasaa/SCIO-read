"""Record narrowly reviewed app findings with source hashes; no raw constants."""
import argparse
from pathlib import Path
import _bootstrap
from scio_offline import research as r


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=r.DEV/'private/lab_1_3_12_java/sources/com/consumerphysics'
    definitions=[
        ('researcher/activities/QuickScanActivity.java','jSONObject.put("sample", this.sample)',
         'QuickScan forwards sample/dark and stored white triplet plus i2s into request JSON. JPEG encoding here is for a separately attached photograph.'),
        ('researcher/serverapi/SamplesProcessor.java','newRecord(',
         'QuickScan analysis calls server newRecord and takes returned RecordModel; not local raw-to-spectrum math.'),
        ('common/serverapi/CommonServerAPI.java','public BaseServerResponse newRecord',
         'newRecord posts to /v3/collections/{id}/records. Endpoint discovered statically, not called.'),
        ('common/model/ModelParser.java','getJSONArray("spectrum_reflectance")',
         'Record parser reads the server spectrum_reflectance array into Float values.'),
        ('common/model/RecordModel.java','public Float[] getSpectrum()',
         'getSpectrum and getSpectrumReflectance return the same stored array; no transform in getters.'),
        ('researcher/serverapi/ProcessOfflineTestModel.java','testModelMany(',
         'Offline test records are sent to testModelMany; resulting spectrum and wavelengths are copied from the response. Offline name is not local decoding evidence.'),
        ('researcher/serverapi/ServerAPI.java','public BaseServerResponse getSampleSpectra',
         'Builds server preprocessing request: Log, Derivative order 1, SelectWL 740..1070, SubtractAvg, x_step 2. These display/request settings do not redefine the 331-band truth axis.'),
        ('android/sdk/sciosdk/ScioInternalDevice.java','String dataAsBase64 = linkedList.get(0).getDataAsBase64()',
         'Scan completion uses direct Base64 for dark/sample/optional gradient and separately reads sample status.'),
        ('android/scioconnection/protocol/ResponseCommand.java','public String getDataAsBase64()',
         'Direct Android Base64 encoding of response bytes.'),
        ('android/common/model/FirmwareUpgradeModel.java','public byte[] getByteData',
         'Firmware Base64 is split into first four checksum bytes and remaining transfer body; no recovered firmware body.'),
        ('researcher/activities/FirmwareUpgradeActivity.java','getPrefs().storeFirmwareFiles(null)',
         'Firmware upgrade uses cached model, sends body through file download, and clears cached firmware on completion. Not file readback.'),
        ('android/scioconnection/protocol/FirmwareFiles.java','deadPixelsIndices(100)',
         'File IDs 89 BLE, 90 DSP boot, 91 DSP dec, 92 DSP op, 100 deadPixelsIndices, 101 centers, 102 bins, 103 nPixelsPerBin. No actual indices/tables recovered.'),
        ('android/sdk/sciosdk/mock/ScioMockDevice.java','private static final String ID',
         'Mock returns ID 503E5732B5EF1F35, BLE address D0:B5:C2:97:83:42, i2s 20150812-o:PRODUCTION, firmware 128 and loads six assets. Mock metadata is not validated physical capture identity or a key.'),
        ('researcher/mock/MockScioService.java','public boolean performSpectrum',
         'Legacy service mock throws Not implemented for spectrum and white-reference operations. Its canned IDs/battery are not firmware evidence.'),
    ]
    rows=[]
    for relative,needle,claim in definitions:
        path=root/relative;text=path.read_text()
        lines=[i for i,line in enumerate(text.splitlines(),1) if needle in line]
        if not lines:raise ValueError('reviewed evidence changed: '+relative)
        rows.append({'file':relative,'sha256':r.sha(path.read_bytes()),'lines':lines,'finding':claim})
    format_sources=[]
    for path in sorted((r.DEV/'private/dart_3_11_4_format').glob('*')):
        if path.is_file():format_sources.append({'name':path.name,'sha256':r.sha(path.read_bytes()),
            'source':'https://raw.githubusercontent.com/dart-lang/sdk/3.11.4/runtime/vm/'+path.name})
    r.write_new(a.output,{'lab_decompilation':{'tool':'JADX 1.5.6','classes_reported':5084,'exit_code':1,'reported_errors':84,
        'limits':'Partial overall decompilation. Reviewed methods have source anchors; other methods may need fallback instruction output.'},
        'lab_observations':rows,'dart_format_sources':format_sources,
        'analyzer_1_5_19':{'binary_sha256':'9d46ae6000a652971848fecb894402727183ca07c986762198283564d9aecd9c',
            'snapshot_probe':'Target-specific candidate RO strings/object pool, not full deserialization.',
            'labels':[{'label':'sample_gradient_chars','pool_offset':'0xe20f','instruction':'0xc756cc'},
                      {'label':'sample_gradient_decoded_bytes','pool_offset':'0xe217','instruction':'0xc75778'},
                      {'label':'sample_gradient_preview','pool_offset':'0xe227','instruction':'0xc75904'}],
            'consumer':'0xc75364 reads diagnostic map fields and forwards invalid_scan_payload labels.',
            'caller':'0xc744ec supplies phase background_single_scan_before_upload.',
            'limits':'Origin of diagnostic map fields and numeric meaning of decoded_bytes unresolved. No demonstrated spectral unpack/decompress/decrypt routine.'},
        'network_device_activity':'None; no SCIO server requests or device commands.'})
    print('Reviewed observations:',len(rows))


if __name__=='__main__':main()
