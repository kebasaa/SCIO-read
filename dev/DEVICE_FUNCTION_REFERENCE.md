# SCIO device-function evidence reference

Updated 2026-10-03. Maintain this alongside [RECOVERY_STATUS](RECOVERY_STATUS.md).
Record useful functional findings here even when they do not recover a decoder.
Source paths below are relative to the supplied decompilation root; no credentials
or personal absolute paths are needed. Device-specific values are not universal.

Maintenance rule: add newly established functional behavior here during each
research session, with source/report links and scope. Preserve raw observations
in versioned evidence reports; correct interpretations without overwriting old
results. For an unrecovered value, explicitly record that it is missing rather
than leaving a suggestive name that a future programmer might mistake for data.

## Evidence and confidence

- **Observed:** saved device response or server result.
- **Code-supported:** behavior of an inspected method; not automatically every
  app version or device generation.
- **Hypothesis:** meaning not established by recovered code or independent truth.

Java scope here is `classes-dex_out/sources/com/consumerphysics/`. Its exact
mapping to an APK version has not been independently established. Source hashes,
anchors, and line numbers are recorded in
[calibration dataflow](analysis_output/recovery_20261003_followup/calibration_dataflow.json)
and [scan/firmware dataflow](analysis_output/recovery_20261003_followup/java_dataflow.json).

## Firmware and calibration file IDs

### Additional Analyzer 1.5.6 ARM64 app evidence

[Reviewed native paths](analysis_output/recovery_20261003_followup/flutter_dataflow.json)
record binary/source hashes and addresses. These are app behaviors, not device
firmware measurements, and do not generalize to the supplied ARM32 1.5.19 build.

- Reading parser `0x31db44`: incoming `sample`, `sampleDark`, `sampleGradient`
  are checked as Strings and copied into object offsets `0x7`, `0xb`, `0xf`.
  Timestamp is separate at `0x13`. These are Dart heap offsets, **not SCIO wire
  offsets**, detector indices or decoded spectral vectors.
- Request builder `0xa0a09c`: those fields become `sample`, `sample_dark`,
  `sample_gradient`; white-reading equivalents become `sample_white`,
  `sample_white_dark`, `sample_white_gradient`. No numerical transformation in
  this builder or the inspected reading parser. Upstream producer remains open.
- Getter `0x6ff260` reads `device_i2s`; the request builder inserts its result as
  `i2s_tag_config`. This is metadata transport evidence, not key derivation.
- Event parser `0x849cf8` delegates the nullable `reading` map to `0x31db44`.
  Separate constructor `0x849ca4` uses an embedded constant triplet and a success
  enum. The triplet is 1800/1800/1416 bytes (sample/dark/gradient); identity and
  physical provenance are unknown. It is not an observed successful device scan.
- No dead-pixel indices, calibration-table bodies, firmware payloads or new
  device command semantics recovered in this native analysis pass.

### Previously observed device file headers

Modern exact-APK extension: [Android bridge audit](analysis_output/recovery_20261003_followup/modern_bridge_v2.json)
connects the 1.5.6 BLE reporter to Base64, reading objects, and Flutter JSON method
results. First BLE packet framing is sequence `1`, marker `0xBA`, command byte,
U16LE payload length, then at most 15 payload bytes; following packets carry a
sequence byte and at most 19 more bytes. This is **BLE framing**, distinct from
USB framing and from the eight-byte scan-blob header. Reassembly removes only
transport framing, not scan-header bytes. No decode is performed in these paths.
Requests use the same split and always start at sequence `1`; the app writes
them *with response*, except READY_FOR_WR (`0x0E`), CLEAR_READY_FOR_WR (`0x11`) and
FILE_DOWNLOAD (`0x81`), which go *without response*. `src/scio/ble.py` implements
this and was verified against the firmware-147 unit on 2026-10-04.

The SDK reads the sample payload's first U32LE as status, but the public
`ScioReading` constructor does not copy the separate status property; the Flutter
reading JSON contains no status property either. This omission was checked in
fallback bytecode-oriented output. The full raw status remains in Base64. Neither
the callback name `onSuccess` nor the JSON type `success` proves raw status zero.

Device JSON independently exposes `calibrationReading` and `whiteReference`.
They are not interchangeable names for the gradient or for recovered calibration
tables. File IDs 89–92 and 100–103 match the earlier enum, but no table bodies,
dead-pixel indices or firmware bytes were recovered here.

The modern SDK's **mock**, not physical, device declares ID `503E5732B5EF1F35`,
address `D0:B5:C2:97:83:42`, BLE ID `bleId`, i2s `20150812-o:PRODUCTION`, firmware
128, RSSI -31, temperature values 25, and battery fields 100/100/100/100/37.
Its `assets/mock/{scan,wr}-{sample,dark,gradient}` file references do not resolve
to files in any nested APK of this supplied 1.5.6 XAPK. Do not transfer these
placeholder identifiers to the connected device or separate Dart fixture, or
promote them to evidence-backed encryption keys.

#### Saved device headers

Observed words from `file_headers` in
[saved USB capture metadata](analysis_output/recovery_20261003_followup/usb_white_cap_six.json).
These are metadata, not recovered file bodies. Columns preserve all four raw
32-bit words; the checksum interpretation of word 3 is code-supported. Word 1
is a candidate byte length; word 2 agrees with listed versions. Do not silently
turn either into a proved file format.

| Requested ID | Name/evidence | Word 0 | Word 1 | Word 2 | Word 3 (checksum field) |
|---|---|---:|---:|---:|---:|
| 87 / 0x57 | Listed BLE runtime; repository label | 87 | 119233 | 125 | 12925168 |
| 89 / 0x59 | `ble` in Java enum; absent from this list | 4294967295 | 4294967295 | 4294967295 | 4294967295 |
| 90 / 0x5A | `dsp_boot` | 90 | 7284 | 17 | 688456 |
| 91 / 0x5B | `dsp_dec` | 91 | 14600 | 12 | 1548938 |
| 92 / 0x5C | `dsp_op` | 92 | 32628 | 147 | 4151168 |
| 99 / 0x63 | Purpose unresolved; not listed | 99 | 32 | 0 | 0 |
| 100 / 0x64 | `deadPixelsIndices` | 100 | 1714 | 3 | 97267 |
| 101 / 0x65 | `centers` | 101 | 96 | 3 | 6080 |
| 102 / 0x66 | `bins` | 102 | 140 | 3 | 13587 |
| 103 / 0x67 | `nPixelsPerBin` | 103 | 1166 | 3 | 36371 |

`android/scioconnection/protocol/FirmwareFiles.java` supplies IDs 89–92 and
100–103, plus `no_file(0)`. Do not equate IDs 87 and 89 or infer a valid file from
an all-ones header. ID 99's response is not proof of stored key material.
The name `dsp_dec` alone does not establish decryption or its processor location.

### Dead pixels and binning: what is actually known

The update activity explicitly associates ID 100 with
`dead_pixels_indices_checksum`, 101 with `centers_checksum`, 102 with
`bins_checksum`, and 103 with `n_pixels_per_bin_checksum`.

**Actual dead-pixel indices have not been recovered.** Neither have center values,
bin memberships, per-bin pixel counts, element types, array dimensions, ordering,
or the mapping to 331 output wavelengths. Do not divide an apparent file length by
an assumed element size and report that as the number of pixels or bands.
These names support a pixel-selection/binning interpretation, but not its exact
algorithm or its position relative to opaque encoding.

For any future acquisition, preserve the entire body, header, hash, device and
firmware association, and I2S tag. Test candidate layouts jointly against these
four files and independent paired spectra, not one attractive array in isolation.

## Checksum and calibration-update data flow

1. `FirmwareUpgradeModel` Base64-decodes each supplied update value, exposes its
   first four bytes as checksum data, and the remaining bytes as file data.
2. `FirmwareUpgradeActivity.performDownloadNextFile` interprets those four bytes
   little-endian and stores the resulting value by file ID in `localChecksums`.
   **This loop does not calculate a checksum over the file body.** Therefore it
   does not identify CRC, sum, or another checksum algorithm.
3. After updating, the activity reads headers for files 100–103. In
   `ScioInternalDevice.performReadFileHeader`, `getU32(12)` is returned to its
   callback. The activity compares that value to the supplied prefix value.
4. The activity reports the four values through `reportFirmwareParamsChecksum`.
   It passes `i2sTag` as the first string argument; the server wrapper names this
   field `compression_version`. `getImage2SpecTag()` itself returns the stored
   I2S preference. This is a concrete metadata connection, **not evidence of a
   compression algorithm, encryption key, or key derivation**.

The inspected checksum endpoint is a report/update workflow, not a documented
calibration-table download endpoint. No requests to it were made in this work.

## Command IDs and boundaries

Unsigned IDs below correspond to Java signed bytes where applicable. Sources:
`android/scioconnection/protocol/CommandIDs.java`, inspected service wrappers,
and repository `src/scio/protocol.py`. Direction and side effects matter.

| ID | Name | Relevant behavior / restriction |
|---|---|---|
| 0x00 | READ_DEVICE_STATUS | Read status |
| 0x01 | READ_DEVICE_ID | Device identity metadata; distinct from file IDs |
| 0x02 | SAMPLE_SPECTRUM | Capture; raw dark/sample/optional gradient responses |
| 0x04 | READ_TEMPERATURE | Read temperature metadata |
| 0x05 | READ_BATTERY_STATE | Read battery metadata |
| 0x06 | READ_EVENT_LOG | Named read command; not arbitrary memory access |
| 0x08 | PARAMETER_GET | Named getter; do not invent parameter meanings |
| 0x84 | READ_BLE_ID | BLE identity/configuration metadata |
| 0x85 | READ_BLE_STATUS | Read BLE status |
| 0x87 | READ_FILE_HEADER | Four-byte little-endian file ID request; header only |
| 0x94 | READ_FILE_LIST | Type/version metadata; no file contents |
| 0x9B | READ_BLE | BLE configuration read |
| 0x81 | FILE_DOWNLOAD | **Host-to-device write**, not firmware readback |
| 0x83 | RESET_DEVICE | Disruptive; not part of this read-only session |
| 0x03, 0x07 | SET_SAMPLE_SETTINGS, PARAMETER_SET | Settings writes; not used |
| 0x0E, 0x11 | READY_FOR_WR, CLEAR_READY_FOR_WR | State-changing calibration controls; not used |
| 0x91, 0x9A | WRITE_USER_DEVICE_NAME, WRITE_BLE | Writes; not used |

The Java task ID `91` used internally for `readFileHeader` is **not** the wire
command and is **not** firmware file ID 91. The wire header-read command is 0x87.
The `0xBA` value is the protocol marker, not an operation. Preserve these
namespaces in future documentation and tooling.

### Framing, identity, and temperature fields

Repository framing (`src/scio/protocol.py`) is
`[sequence, 0xBA, command, payload_length_le16, payload...]`. BLE notification
fragmentation is distinct from the contiguous USB serial framing; do not feed
notification sequence bytes into a candidate spectrum decoder.

Inspected `protocol/commands/DeviceIdResponseCommandHandler.java` reads an
eight-byte identifier at payload offset 0, another at offset 16, and firmware
version as U16 at offset 24. It swaps the two bytes **within each 16-bit word**
of the second identifier before returning it. Repository labels are DSP ID and
Aptina/device ID respectively. This is not reversal of all eight bytes.

`BleIDResponseCommandHandler.java` reads BLE ID at offset 0 (8 bytes), BLE
firmware at offset 8 (U16), name at offset 50 (16 bytes), and I2S tag at offset 66
(64 bytes), removing NULs and trimming the tag. Bytes 10–49 hold the device
serial (30 + 10 characters) and are **not read by this inspected Java handler**.
Hardware-tested on 2026-10-04 (no app sends these): `0x89` writes `[10:40]` and
`0x93` writes `[66:130]`, raw ASCII as in the app's `0x91` rename of `[50:66]`,
persistent across a power cycle; an empty payload clears the field. `0x88` and
`0x95` acknowledge writes with no visible effect. See README section 3.
Preserve original bytes and parser provenance when testing identifier-derived
hypotheses. Never combine identifiers from different devices.

`TemperatureResponseCommandHandler.java` reads three U32 values at offsets
0, 4, and 8. Its Aptina conversion truncates `(raw - 375.22)` to an integer,
converts to float, divides by `1.4092f`, then truncates again. Chip and object
values use integer division by 100 before conversion to float. The repository
also exposes non-truncated numerical variants; distinguish those from app-exact
behavior when reproducing calibration decisions. This formula is app code,
not independently verified sensor metrology.

Source locations for these handlers are relative to the Java scope above under
`android/scioconnection/protocol/commands/`. Their hashes are recorded in
[identity/temperature evidence](analysis_output/recovery_20261003_followup/identity_temperature_dataflow.json).

**Object temperature (word 2) is live on at least one unit.** The README notes
`obj_t = w2/100` reads `0.0` on the firmware-147 reference unit. A contributed
firmware-138 unit reports a **non-zero object/surface temperature that tracks the
target** (raw `READ_TEMPERATURE` triples, `obj = w2/100`):

| target | raw u32 LE (w0 w1 w2) | obj_t |
|---|---|---|
| white reference (in cover) | `8d010000 b5080000 df080000` | 22.71 °C |
| pine wood | `91010000 4d090000 c5070000` | 19.89 °C |
| tomato | `94010000 d1090000 e3070000` | 20.19 °C |
| skin (hand) | `95010000 690a0000 bf0c0000` | 32.63 °C |

Skin (~32.6 °C) versus room-temperature targets (~20 °C) matches real surface
temperatures, so it looks like a genuine (uncalibrated, likely contact) reading
rather than noise. `obj_t` is therefore **not universally 0** — it is unit/firmware
dependent. `ScioDevice.read_object_temperature()` returns it.

**Confirmed on the firmware-147 unit (2026-10-08, read-only):** a 16-read
`READ_TEMPERATURE` series (`scripts/read_object_temperature.py`, command 0x04 only,
no scans/writes) returned `obj_t = 0.00` on every read while the sensor went from
open air to skin contact; `cmos_t`/`chip_t` varied normally
([evidence](analysis_output/objt_20261008/objt.json)). So fw-147 never populates the
object word, while the fw-138 unit does — the field is firmware/unit dependent, not
universally live. Not checked against a reference thermometer.

**It is not a different command or format on fw-147.** The raw `READ_TEMPERATURE`
response is exactly 12 bytes (`900100007909000000000000` → `[400, 2425, 0]`); the
object `u32` at offset 8 is literally `0x00000000` on the wire, and stays 0 when read
immediately after a `SAMPLE_SPECTRUM` (LED fired). The command (0x04), the 12-byte
3×`u32` format, and the decompiled `TemperatureResponseCommandHandler`
(`object = u32(8)/100`) are identical across firmware and app versions. So the 0 is
the firmware not populating the word, not an alternate command, a longer response, a
different offset, or a parsing error
([evidence](analysis_output/objt_20261008/temp_command_fw147.json)).

## Power control: USB and BLE

**Confirmed in inspected app code:** configurable automatic-off timer over the
BLE command transport. **Not confirmed:** immediate remote shutdown, waking a
sleeping device, or powering on a fully off device over USB or BLE. Lack of a
command in this audit is not proof no such firmware capability exists.

`PowerSaverActivity` reads `READ_BLE` (0x9B), interpreting U16 LE at offset 2 as
seconds and dividing by 60 for the displayed minutes. `SCiOBLeService` writes
`WRITE_BLE` (0x9A) with payload `00 00 seconds_lo seconds_hi`. After a successful
write, the activity schedules `RESET_DEVICE` (0x83, empty payload) one second
later. The reset is a separate disruptive operation; its power-state outcome
and USB behavior have not been hardware-validated here.

The researcher source's `resources/res/layout/activity_power_saver.xml` has
SeekBar maximum 29, while the activity adds one: observed UI range **1–30 minutes**.
Its `resources/res/values/strings.xml` says the SCIO will turn off after the
timeout and warns that reducing it might turn the device off. The same resource
file directs the user to press the physical button for around three seconds to
turn it on, then charge by micro-USB if necessary. This is evidence of the manual
workflow, not proof that charging itself wakes the command processor.

Both inspected consumer and researcher activities contain this unusual operation:

```text
seconds = minutes * 60
low = signed_int8(seconds & 255)
if low < 15:
    seconds += signed_int8(15 - low)
```

Examples: 1 minute -> 60 seconds; 3 -> 271; 15 -> 783; 30 -> 1807.
The reason is unresolved. Do not silently replace the signed casts with an
unsigned minimum, or claim these are measured shutdown times. Zero/immediate-off
and arbitrary values outside the app UI are not supported by the new helper.

**Modern-APK scope correction:** the exact 1.5.6 Flutter plugin accepts an integer
argument named `seconds`; SDK `writeBle` forwards it to a service that writes
`00 00 low_byte high_byte` under opcode `0x9A`, without the older UI's adjustment.
Thus that adjustment is an older app-compatibility behavior, not an established
wire-protocol or firmware requirement. Existing minute-based production helper
was deliberately left unchanged. No modern setter, reset, zero timeout, or new
timer value has been tested on the device. This finding does not establish
remote power-on, immediate power-off, or persistence semantics.

Library additions (explicitly requested by the user, unlike dev-only decoder work):

- `scio.power`: pure app-compatible timer encoding and response parser, also
  reusable by a future BLE transport. No BLE connection implementation is added.
- `ScioUSB.read_power_saver()`: read-only timer query; does not power on a device.
- `ScioUSB.set_power_saver(minutes, allow_write=True)`: guarded timer write,
  returns requested/encoded duration and raw response. Does not automatically
  reset, retry, or claim persistence/application of the setting.
- `ScioUSB.reset_device(allow_write=True)`: guarded single reset request; timeout
  may mean the connection disappeared, not that reset failed. Never alias this
  operation to `power_off()` or `power_on()`.

All normal capture operations and the probe denylist retain their read-only
defaults. Mocked serial tests check exact frames, opt-in enforcement, input
validation, signed-byte edge cases, and no automatic reset/retry. No command
was sent to the actual device for this investigation. A previously saved
`usb_white_cap_six.json` READ_BLE attempt timed out, so it does not validate the
USB timer interpretation. A device-observed off/on test remains separate work.

`disconnectDevice` only clears/unbinds the host connection; UI names such as
`turnOff` are not evidence of a shutdown opcode. Source-hashed method anchors:
[power dataflow](analysis_output/recovery_20261003_followup/power_dataflow.json).

### Live-validation readiness

### Reset semantics and user safety condition

**Later event and current restriction:** the user subsequently authorized one
reset, then cancelled and requested documentation only. The 0x83 request had
already been sent before cancellation arrived. The response timed out, and three
bounded read-only reconnect attempts failed with `SerialException`. The command
was not retried; no timer write occurred. The run had completed when the stop
request was processed. All device work is now stopped; do not attempt additional
reads or resets without new direction. Evidence is preserved in
[reset_validation_01](analysis_output/recovery_20261003_followup/reset_validation_01/).
There is a before snapshot but no after snapshot, so settings retention and actual
restart/shutdown outcome remain unknown. The earlier assessment below describes
the evidence before that attempt, not a claim that no reset has ever been sent.

The user authorizes reset only if it restarts without resetting device settings.
No reset or timer write was sent under that conditional authorization.

Additional inspected callers support **intended restart semantics**: rename
success invokes 0x83 while retaining the new name in app preferences; onboarding
also resets after rename; firmware update uses RESET_FIRST_SET/RESET_SECOND_SET
stages after transfers. Together with resetting after the timer write, this is
strong evidence against interpreting it as an intentional factory reset.
`RenameDeviceActivity` even treats a reset timeout as acceptable; do not retry
just because the device disappears before acknowledgement.

Nevertheless, caller intent is not a recovered implementation of firmware 147's
command handler. No settings-retention guarantee or complete settings backup is
available. A before/after read of a few fields could detect some changes only
after the fact and would not satisfy the user's condition beforehand. Therefore
keep the reset/timer-write test on hold, rather than discovering its semantics
by risking the device's configuration. Library reset documentation carries the
same warning. [Source-hashed reset callers](analysis_output/recovery_20261003_followup/reset_semantics.json).

### USB timer-read results

**Subsequent live result:** after the user connected and woke the device, the
three-read probe completed successfully on firmware 147. READ_BLE (0x9B)
returned `00 00 68 01`: U16 LE at offset 2 is **360 seconds / 6 minutes**. Both
identity controls returned matching 28-byte payload hashes. Evidence:
[power_read_live_01.json](analysis_output/recovery_20261003_followup/power_read_live_01.json).
Thus USB timer reading is observed on this unit; the earlier timeout does not
establish an unsupported command. No timer setting, reset, shutdown test, or
scan was performed. The reported six minutes is not a measured shutdown time.
The following readiness notes describe the preceding preparation.

Both supplied Bluetooth logs contain zero complete 0x83/0x9A/0x9B frames under
the existing strict reassembler; see [power traffic](analysis_output/recovery_20261003_followup/power_traffic.json).
They cannot establish shutdown/wake behavior. No SCIO USB port was detected
during the subsequent check, so live timer validation remains pending.

`dev/scripts/probe_power_readonly.py` prepares a bounded identity/timer/identity
sequence. Without `--live` it only saves a plan. With an awake connected unit,
it issues at most three read commands, stops after an invalid initial control,
checks response opcodes, and does not send timer writes, reset, scans, or wake
commands. Use a new output filename under `dev` for each run. Identity payloads
are hashed, not exported. Four mocked cases cover success, asleep/failed initial
control, timer timeout followed by a good control, and unexpected opcode.

A successful timer read would confirm only an interpretable response while the
device answers controls. A timeout between successful controls would isolate
the timer read from a generally unresponsive device. Neither result would justify
claiming remote power-on or validating an untested write/reset sequence.

## Scan and spectral behavior established so far

- Fixed-size scan containers do not establish fixed-rate compression. Padding,
  fixed buffers, and trailers can hide variable compressed lengths. Legacy
  `transform_class` exclusions were corrected in schema 2; preserve old reports
  as historical rather than inheriting their conclusions.
- A bounded keyless word/bit-representation codec probe found no validated
  intermediate. Its occasional short raw-DEFLATE streams also occur in random
  controls; they must not be interpolated or labeled as spectral vectors. See
  [representation codec evidence](analysis_output/recovery_20261003_followup/representation_codecs.json).

- Inspected Java paths Base64-encode raw response payloads and place sample,
  dark, and gradient strings in analysis JSON; no numerical decode in those methods.
- `gradient` is a scan component, not the external white reference. Its role
  remains unresolved; omission was accepted in the documented bounded oracle.
- Tested server spectra have 331 wavelengths, 740–1070 nm inclusive. This is not
  proof that opaque bodies contain 331 plaintext numbers.
- Tested intact substitutions support independent sample/white processing with
  a common factor C. Three self-reference pairs reproduce C to floating-point
  precision. C is server-derived, not a locally recovered calibration table.
- Simple additive, fixed per-band affine, and tested shared-scalar dark models
  fail numerical equivalence. Absolute sample/white vectors remain unrecovered.
- Rejected mutations do not establish a MAC or encryption. Compression-only,
  including image-related compression, remains a hypothesis subject to the
  bounded negative tests in the recovery log.

## Native-app evidence and remaining tracing work

### Phone-integrated sensor route: external service, not recovered decoder

`android/sdk/sciosdk/ScioPhoneInternalDevice.java` is distinct from the BLE/USB
device path. It reflectively loads `android.hardware.ISCiO`, finds its `Stub`,
and calls `asInterface` on Android ServiceManager's `SCiO_service` binder.
Its implementation is not shown in this wrapper. A definition-table audit of
all **22 DEX files across nine supplied archives** found nine occurrences of
`ScioPhoneInternalDevice` but **zero definitions** of `android.hardware.ISCiO`
or `android.hardware.ISCiO$Stub`, with no parse errors. This is a bounded absence
of these exact class definitions, not proof about dynamic code or system images.
See [DEX boundary evidence](analysis_output/recovery_20261003_followup/phone_service_boundary.json).

The inspected wrapper exposes the following service boundary:

| Service method | Wrapper behavior |
|---|---|
| `getMessageSize(byte)` | Selectors 1, 2, 3 determine three buffer lengths |
| `takeSample(byte[], byte[], byte[])` | Fills three buffers; caller Base64-encodes each |
| `getID(byte[])` | Fills a 16-byte allocation; returned count controls hex conversion |
| `getI2STag()` | Returns string cached as I2S preference |

Constructor argument order associates buffer 1 with dark, 2 with sample, and 3
with gradient. This does not reveal the buffers' internal encoding. The wrapper's
ID conversion formats each returned byte in order and uppercases the hex; it
does not perform the BLE handler's per-word byte swap. Do not interchange those
representations without device/generation evidence.

Important placeholder behavior: `getFirmwareVersion()` returns constant 128;
`getLastTemperature()` returns three constant 25 values; `calibrate()` stores
constant 20 before/after temperatures. These are **not measured values**. The
wrapper's `getScioCalibrationReading()` also constructs an empty reading with
fixed temperatures, and battery information is hard-coded. These placeholders
must not be used as evidence about the connected pocket device's firmware,
physical temperature, or calibration. Source-hashed method anchors:
[phone wrapper dataflow](analysis_output/recovery_20261003_followup/phone_wrapper_dataflow.json).

This route suggests a system/vendor implementation would be a relevant artifact
if independently available. It does not imply that the user's unavailable
historical phone had integrated SCIO hardware, and does not reopen that backup
route. No system service or APK was executed during this audit.

### Flutter snapshots

[Native inventory](analysis_output/recovery_20261003_followup/native_paths.json):
nine supplied archives, 50 library occurrences, 27 distinct SHA-256 hashes.
The 1.5.19 app contains ARM32 Dart snapshots without compressed pointers; 1.5.6
contains ARM64 snapshots with compressed pointers. Snapshot-format hashes and
section locations are recorded in the inventory and are **not candidate keys**.

Newer gradient diagnostic literals (`sample_gradient_decoded_bytes`,
`sample_gradient_preview`, `sample_gradient_chars`) are useful AOT tracing targets.
They do not prove an image or spectral decode. The follow-up below resolves
selected references to a diagnostic consumer; the producer is still unresolved. Generic multimedia
libraries and codec strings do not connect those codecs to SCIO payloads.

The historical phone and its backups are unavailable. Do not keep assigning
that route to the user. Remaining acquisition options must be evaluated against
the supplied artifacts or a separately authorized read-only hardware session.

## Follow-up app evidence: Analyzer 1.5.19 and Lab Toolkit

Firmware storage correction: `ScioFirmwareFiles` contains file-version metadata,
not bodies. In the exact Lab app, body containers come from the response's
`new_version` object and are stored under bare enum names; the per-user
`firmware.file.names` set indexes them. `storeFirmwareFiles(null)` removes the
index, not the strings. Read-header checksum at byte 12 is compared with the
little-endian four-byte update prefix; this is not host-side checksum recovery.

Fresh USB firmware-route check: `usb_firmware_recheck.json` confirms firmware 147,
BLE 125 and the previously recorded file headers (including file 87 runtime,
89 sentinel and 99 length 32). I2s bytes remain empty; the historical tag used in
server requests is separately labeled. No body read, reset, update or captures.
The known firmware endpoint returned null offers for current/one-below/current
versions; no body was obtained. These are observations, not a global absence
claim. The direct DEX vendor 80-byte array is `Workshop.COLORS`, not calibration.

See `analysis_output/recovery_20261003_followup/app_followup.json` for hashed
source anchors and `lab_fixtures.json` for blob headers/hashes. No device commands
were sent for this audit.

- Analyzer 1.5.19 ARM32 has an invalid-payload diagnostic consumer at `0xc75364`.
  It reads gradient character count, decoded-byte count and preview fields from
  a map. One caller labels the phase `background_single_scan_before_upload`.
  Follow-up `validation_trace.json` resolves the producer at `0xc75cac`:
  decoded bytes means Base64 output length, and preview means up to 96 code units
  of encoded input plus ellipsis. The helper tests emptiness, Base64 validity and
  decoded length >= 4, not SCIO header/body integrity or spectral calibration.
  Sample/dark are required; gradients may be empty; white fields are checked if
  their keys exist. These client checks do not establish server acceptance.
- Exact Lab Toolkit 1.3.12.144 repeats file IDs 89/90/91/92 and 100/101/102/103
  for BLE/DSP boot/DSP dec/DSP op and deadPixelsIndices/centers/bins/nPixelsPerBin.
  These names and IDs are established; actual dead-pixel indices/table bodies
  remain missing. Firmware Base64 has a four-byte checksum prefix followed by
  transferred data; the checksum algorithm is not established by this split.
- Its QuickScan result comes from server `spectrum_reflectance`. An offline-queue
  processor still calls the server. Log/Derivative/SelectWL/SubtractAvg are sent
  as server preprocessing options, not applied locally in that request builder.
- The two code-embedded mock gradients start with U32LE 110. Asset mock gradients
  start with zero. Both are 1,416 bytes; this is observed framing, not a decoded
  status interpretation. Mock identity values are listed in `RECOVERY_STATUS.md`
  and must not be assigned to the physical device or treated as known keys.
  Follow-up comparison finds all six code constants identical in the supplied
  source tree labeled 2017. They are not independent new captures or new truth.
