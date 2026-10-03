"""Save source-hashed, method-level Java dataflow observations; no blanket APK claim."""
import argparse
from pathlib import Path
import _bootstrap
from scio_offline import research as r


NODES=[
('android/scioconnection/services/SCiOBLeService.java','public boolean performSpectrum',
 'Capture wrapper sends command 2; it does not compute spectral values.'),
('android/sdk/sciosdk/ScioInternalDevice.java','String dataAsBase64 = linkedList.get(0).getDataAsBase64();',
 'Scan-completion path Base64-encodes complete response payloads: index 0 dark, index 1 sample, optional index 2 gradient; creates ScioInternalReading.'),
('android/scioconnection/protocol/ResponseCommand.java','public String getDataAsBase64()',
 'Returns Base64.encodeToString(this.data, 0), without decrypting or decompressing.'),
('android/sdk/model/ScioInternalReading.java','this.sample = str;',
 'Constructor retains sample, dark and gradient strings; getters return these fields.'),
('android/sdk/model/ScioReading.java','this.sample = scioInternalReading.getSample();',
 'Public reading copies strings from internal reading without numerical processing.'),
('android/sdk/sciosdk/ScioInternalCloud.java','private String prepareAnalyzeJson(ScioReading scioReading, String str, String str2, Map',
 'SDK analysis request inserts sample/dark/gradient and white equivalents directly from reading getters.'),
('consumer/serverapi/ServerAPI.java','public BaseServerResponse scanSpectroscan',
 'Consumer spectro endpoint posts the supplied JSONObject to /v2/consumer/spectro-scan; no local decoder in this wrapper.'),
('consumer/background/workers/OfflineSampleScansAnalyzeWorker.java','if (!NetworkUtils.isNetworkConnected',
 'Offline-analysis worker returns without processing when network is unavailable; pending scans are uploaded/analyzed after connectivity resumes.'),
('consumer/serverapi/operations/SamplesOperationsManager.java','BaseServerResponse scan = new ServerAPI',
 'Queued analysis path calls ServerAPI.scan and handles the returned model, rather than deriving reflectance locally.'),
('android/common/model/FirmwareUpgradeModel.java','private byte[] getRawData',
 'Base64-decodes a server-provided file; first four bytes are exposed as checksum, remaining bytes as file data. This is not an embedded firmware asset.'),
('consumer/activities/FirmwareUpgradeActivity.java','this.upgradeState.data = this.fum.getByteData(next);',
 'Update activity obtains file data from the response model and divides it into transfer messages.'),
('android/scioconnection/services/SCiOBLeService.java','public boolean performFileDownload',
 'File-download wrapper supplies outbound bytes to FILE_DOWNLOAD; this is host-to-device writing, not firmware readback.'),
]

CALIBRATION_NODES = [
('android/scioconnection/protocol/FirmwareFiles.java', 'deadPixelsIndices(100)',
 'Enum maps deadPixelsIndices=100, centers=101, bins=102, nPixelsPerBin=103; names alone do not establish table element types or dimensions.'),
('consumer/activities/FirmwareUpgradeActivity.java', 'this.i2sTag = getScioDevice().getImage2SpecTag();',
 'Update completion obtains the image-to-spectrum tag for subsequent checksum reporting.'),
('android/sdk/sciosdk/ScioInternalDevice.java', 'return this.preferences.getI2S();',
 'getImage2SpecTag returns the stored I2S preference, not a computed cryptographic key in this method.'),
('consumer/activities/FirmwareUpgradeActivity.java', 'this.upgradeState.checksum = this.fum.getChecksumData(next);',
 'The following loop interprets the four supplied prefix bytes little-endian and stores their value in localChecksums. It does NOT calculate a checksum over file contents.'),
('consumer/activities/FirmwareUpgradeActivity.java', 'performReadFileHeader("dead_pixels_indices_checksum", 100, hashMap);',
 'Reads device headers for IDs 100..103, compares their checksum fields with the supplied update-prefix values, then reports them to server.'),
('android/sdk/sciosdk/ScioInternalDevice.java', 'final long u32 = responseCommand.getU32(12);',
 'Read-file-header callback returns the word at payload offset 12 as checksum; it does not return the file body.'),
('android/scioconnection/services/SCiOBLeService.java', 'responseCommandHandler.setRequestedCommandData(ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(i).array());',
 'Read-file-header wrapper serializes the file ID as four little-endian bytes, then sends READ_FILE_HEADER.'),
('common/serverapi/CommonServerAPI.java', 'public BaseServerResponse reportFirmwareParamsChecksum',
 'Caller supplies i2sTag as first string argument; this wrapper serializes it under compression_version with the four checksums. This ties metadata naming, not a compression implementation or key derivation.'),
]

IDENTITY_NODES = [
('android/scioconnection/protocol/commands/DeviceIdResponseCommandHandler.java', 'String dataAsHex2 = responseCommand.getDataAsHex(16, 8);',
 'Reads eight-byte IDs at offsets 0 and 16, U16 firmware at 24; swaps each pair of bytes of the second ID, not the entire ID.'),
('android/scioconnection/protocol/commands/BleIDResponseCommandHandler.java', 'String dataAsString2 = responseCommand.getDataAsString(66, 64);',
 'BLE ID offset 0 length 8, U16 firmware offset 8, name offset 50 length 16, I2S offset 66 length 64 with NUL removal and trim; no serial-fragment extraction here.'),
('android/scioconnection/protocol/commands/TemperatureResponseCommandHandler.java', 'long u32 = (long)',
 'Aptina expression truncates raw-375.22 before float division by 1.4092f, then truncates result. Chip/object U32 values use integer division by 100.'),
('android/scioconnection/protocol/CommandIDs.java', 'public static final byte READ_FILE_HEADER = -121;',
 'Signed Java command constant corresponds to unsigned 0x87. This is not the SDK internal task ID or a firmware file ID.'),
]

PHONE_NODES = [
('android/sdk/sciosdk/ScioPhoneInternalDevice.java', 'this.iSCiOClass = Class.forName(ANDROID_HARDWARE_ISCIO);',
 'Loads android.hardware.ISCiO reflectively; obtains SCiO_service through ServiceManager and Stub.asInterface. Implementation is outside this wrapper.'),
('android/sdk/sciosdk/ScioPhoneInternalDevice.java', 'getMethod("getMessageSize", Byte.TYPE)',
 'Both calibrate and scan query buffer sizes using byte selectors 1, 2, 3 before invoking takeSample with three byte arrays.'),
('android/sdk/sciosdk/ScioPhoneInternalDevice.java', 'getMethod("takeSample", byte[].class, byte[].class, byte[].class)',
 'Returned arrays are Base64-encoded. Constructor order maps buffer 2 to sample, buffer 1 to dark, buffer 3 to gradient; no numeric decode here.'),
('android/sdk/sciosdk/ScioPhoneInternalDevice.java', 'return new TemperatureResponseCommandHandler.DeviceTemperature(25.0f, 25.0f, 25.0f);',
 'This phone wrapper returns fixed 25-degree temperatures; calibrate stores fixed 20-degree before/after values. These constants are not measurements.'),
('android/sdk/sciosdk/ScioPhoneInternalDevice.java', 'return 128;',
 'getFirmwareVersion returns fixed 128, not a device query. Do not infer actual firmware from this wrapper.'),
('android/sdk/sciosdk/ScioPhoneInternalDevice.java', 'getMethod("getID", byte[].class)',
 'Allocates 16-byte buffer; getID return count controls byte-to-hex conversion, then uppercase preference storage. Distinct from BLE handler word-swapping.'),
('android/sdk/sciosdk/ScioPhoneInternalDevice.java', 'getMethod("getI2STag", new Class[0])',
 'Obtains I2S string from service and caches it; no local key derivation in this method.'),
]

POWER_NODES = [
('consumer/activities/sciosettings/PowerSaverActivity.java', 'final int u16 = linkedList.get(0).getU16(2) / 60;',
 'Reads automatic-off seconds as U16 at READ_BLE response offset 2; displays integer minutes.'),
('consumer/activities/sciosettings/PowerSaverActivity.java', 'byte b = (byte) (convert & 255);',
 'After minutes*60, converts low byte to signed Java byte; if less than 15, adds another signed-byte cast of 15-b. This is not an unsigned clamp.'),
('consumer/activities/sciosettings/PowerSaverActivity.java', 'getScioDevice().writeBle(convert, r0);',
 'Writes encoded timer; success callback schedules resetDevice, not an immediate-off command.'),
('android/scioconnection/services/SCiOBLeService.java', 'responseCommandHandler.setRequestedCommandData(new byte[]{0, 0, (byte) (i >>> 0), (byte) (i >>> 8)});',
 'WRITE_BLE payload is 00 00 followed by the low/high bytes of the seconds argument.'),
('android/scioconnection/services/SCiOBLeService.java', 'return performCommand(CommandIDs.RESET_DEVICE, responseCommandHandler);',
 'Reset is opcode 0x83 with no payload set by this wrapper. No proof that reset means sustained power-off or that a powered-off device can receive it.'),
('android/sdk/sciosdk/ScioInternalDevice.java', 'private void disconnectDevice(boolean z)',
 'Disconnect clears tasks, unbinds service, and may destroy the host BLE service. Do not call disconnect a device shutdown command.'),
]


RESET_NODES = [
('consumer/activities/sciosettings/RenameDeviceActivity.java', 'RenameDeviceActivity.this.performReset(trim);',
 'Rename success invokes reset; performReset retains the requested name in app preferences. Supports intended restart semantics, not proof of device-side retention of every setting.'),
('consumer/activities/sciosettings/RenameDeviceActivity.java', 'on timeout - reset - good thing',
 'Reset timeout is explicitly treated as an acceptable path to closing the activity; do not automatically resend a timed-out reset.'),
('consumer/activities/FirmwareUpgradeActivity.java', 'this.state = State.RESET_SECOND_SET;',
 'Reset is a stage of the firmware update state machine after transfers, consistent with restarting to use updated files. Device implementation not recovered.'),
('consumer/activities/onboarding/OnBoarding2ConnectActivity.java', 'OnBoarding2ConnectActivity.this.scioDevice.resetDevice(new ResponseCommandHandler()',
 'Onboarding invokes reset after rename, then checks calibration need and disconnects; not a documented factory-reset workflow.'),
]


def main():
    p=argparse.ArgumentParser();p.add_argument('--apps',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    group=p.add_mutually_exclusive_group();group.add_argument('--calibration',action='store_true');group.add_argument('--identity',action='store_true');group.add_argument('--phone',action='store_true');group.add_argument('--power',action='store_true');group.add_argument('--reset',action='store_true');a=p.parse_args()
    prefix=Path('classes-dex_out/sources/com/consumerphysics');rows=[]
    for relative,anchor,note in (RESET_NODES if a.reset else POWER_NODES if a.power else PHONE_NODES if a.phone else IDENTITY_NODES if a.identity else CALIBRATION_NODES if a.calibration else NODES):
        path=a.apps/prefix/relative;raw=path.read_bytes();lines=raw.decode('utf-8').splitlines()
        locations=[i for i,line in enumerate(lines,1) if anchor in line]
        if not locations:raise ValueError('source anchor missing: '+relative)
        rows.append({'source':(prefix/relative).as_posix(),'sha256':r.sha(raw),'anchor':anchor,'matching_lines':locations,'observation':note})
    r.write_new(a.output,{'nodes':rows,'coverage':'Manually inspected method-level paths in classes-dex_out source tree; APK/version correspondence not newly established.',
        'limits':'No claim of exhaustive Java coverage or completed Flutter AOT control flow. Strings and pass-through wrappers do not locate the device/server opaque transform. No hardware or update commands executed.'})
    print('source-hashed observations',len(rows))


if __name__=='__main__':main()
