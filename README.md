[![GitHub](https://img.shields.io/github/license/kebasaa/SCIO-read)](https://www.gnu.org/licenses/gpl-3.0)

# Reading the SCiO spectrometer (Consumer Physics)

Tools to talk to a [Consumer Physics SCiO](https://www.consumerphysics.com/)
near-infrared spectrometer over USB, capture its raw scans, and work toward
decoding them **offline**. The SCiO is now end-of-life: Consumer Physics
de-activated accounts and its servers no longer analyse this device. The scan
encoding is unresolved: packing, compression, obfuscation and encryption are
all hypotheses. The goal is to identify that transform from local evidence and
recover repeatable wavelength-indexed spectra without the server.

Contributions - especially firmware blobs extracted from an old phone, or
Blackfin reverse-engineering - are very welcome. See
[How you can help](#how-you-can-help).

## Status

| Capability | State |
|---|---|
| Command the SCiO over USB, read metadata, temperature, battery | **Works** (`07_scio_capture.ipynb`) |
| Capture and store raw scans + white reference | **Works** |
| Convert a raw scan into a spectrum offline | **Researching**: the opaque transform is not yet identified |
| Convert via the Consumer Physics server | **Dead**: device is EOL, accounts de-activated, server refuses these scans |

`analyze_scio.py` builds a canonical corpus and hypothesis-neutral diagnostics.
The current 82-record/324-blob report rejects direct raster/image layouts,
common weak PRNG/stream transforms, and the enumerated AES/TEA/XTEA keys derived
from serials and hardware IDs. These are bounded negative results, not proof of
encryption or proof that no image-domain data exists behind the opaque layer.

## Quick start

1. Create the environment (or use any env with the listed packages):
   ```bash
   conda env create -f scio_env.yml   # numpy, pandas, scipy, matplotlib, pyserial, cryptography, jupyterlab, pytest
   ```
2. Turn the SCiO on (long press until it blinks blue) and connect USB.
3. Run `07_scio_capture.ipynb` to read the device and capture a white reference
   and a sample scan. Raw scans are saved under `01_rawdata/`.
4. To attempt decoding, run `08_scio_keyrecovery.ipynb` (or `recover_key.py`)
   after obtaining the DSP firmware from an old phone.
5. Run `analyze_scio.py` or `10_scio_evidence_pipeline.ipynb` to rebuild the
   corpus/evidence reports. Offline checks: `pytest tests/`.
6. `repeatability_key_search.py` and `embedded_cipher_search.py` reproduce the
   unchanged-target AES and TEA/XTEA identifier-key tests.

On Windows the SCiO appears as a Texas Instruments CDC serial port (VID:PID
`0451:16AA`); on Linux it is a `/dev/ttyACM*` device.

**If the SCiO enumerates but never answers** (commands time out waiting for the
`0xBA` marker), it is in its idle/charging state: the light pulses slowly
between light and dark blue instead of glowing steadily. Power-cycle it -
unplug USB, long-press to turn it off, long-press to turn it on until the light
is steady, then reconnect USB. It then responds to commands normally. This is a
device-state issue, not a serial-settings one.

## How the SCiO actually works

This section replaces earlier guesses in this repo with what was verified from
the device data and the decompiled apps.

1. **Optics.** A diffuser and a Fabry-Perot-style optical filter with several
   sub-filters of different centre wavelengths sit in front of a lens and a
   micro-lens array. Light of each wavelength lands as a ring/spot of a
   characteristic radius, so wavelength is encoded as position on the sensor
   (US patents [US9377396B2](https://patents.google.com/patent/US9377396B2) and
   [US10330531B2](https://patents.google.com/patent/US10330531B2)).
2. **CMOS sensor.** An ON Semiconductor MT9M034 (1280x960, 12-bit) captures the
   image.
3. **DSP binning.** A Blackfin BF512 DSP reduces the image to a compact vector
   using **per-device tables**: `deadPixelsIndices`, `centers`, `bins`,
   `nPixelsPerBin`. Their version is the `i2s_tag_config` string (e.g.
   `20150812-e:PRODUCTION`); the server called this the `compression_version`.
   "i2s" = *image-to-spectrum*.
4. **Opaque encoding.** Each scan sends three blobs—dark, sample, gradient—with
   an observed 8-byte prefix (`u32 type`, `u32 unclassified value`) and a
   high-entropy body. Body sizes are multiples of 16 on the available firmware.
   This is compatible with packed data, compression, obfuscation or encryption;
   it does not prove AES, a nonce, a per-device key, or Lockbox usage.
5. **Transport.** The phone received the three blobs over BLE/USB, base64-encoded
   them verbatim, and POSTed them (plus the stored white reference) to
   `api.consumerphysics.com`.
6. **Server (now gone).** The server undid the opaque encoding and binning and
   returned a 331-point reflectance spectrum on a linear axis
   (`{start: 740, steps: 1, num_WL: 331}` -> 740-1070 nm). Nothing in any app
   ever computed a spectrum locally.

### Corrections to earlier notes in this repo

- *"The raw bytes don't match the base64 sent to the server."* They do match.
  The confusion came from two things: the three responses arrive as
  **dark, sample, gradient** (index 0 is dark, not sample), and the old USB
  notebook used URL-safe base64 while the app/logs use standard base64.
- *"No clue what sample / dark / gradient mean."* Dark = exposure with the
  illumination off (baseline), sample = illuminated exposure, gradient = a third
  exposure (header type `0x6E`) the server model also used.
- *"12 filters x 27 nm = 331 bands."* Coincidence; the 331 points come from the
  server's `num_WL`, not from the optics arithmetic.
- *"R = S / C."* A conceptual sketch only; the server combined all six blobs
  (sample/dark/gradient and the white-reference triplet) with the per-device
  tables. The technical-support export establishes the final spectral-domain
  relationship exactly: `spectrum = sample_raw / wr_raw`. Converting each raw
  triplet into those spectral-domain vectors remains unresolved.
- *"It measures twice and averages."* One scan command returns two or three
  response blobs (by firmware version), not two averaged scans.

## Protocol reference

Frames in both directions: `[seq, 0xBA, cmd, len_lo, len_hi, payload...]`
(`0xBA` is the protocol marker; length is little-endian uint16). Over BLE each
20-byte notification is additionally prefixed with the sequence byte and there
is **no CRC**; over USB the whole frame arrives on the serial stream.

| Cmd | Hex | Meaning | Response |
|---|---|---|---|
| READ_DEVICE_STATUS | 0x00 | status | status payload |
| READ_DEVICE_ID | 0x01 | identifiers | dsp id `[0:8]`, aptina id `[16:24]` (16-bit words byte-swapped -> `device_id`), fw `u16@24` |
| SAMPLE_SPECTRUM | 0x02 | scan | 2 responses (fw < 136) or 3: dark, sample, gradient |
| READ_TEMPERATURE | 0x04 | temperature | 3x `u32` LE; cmos `(x-375.22)/1.4092` C, chip `x/100`, object `x/100` |
| READ_BATTERY_STATE | 0x05 | battery | charge% `u16`, health% `u8`, status `u8`, charging `u16`, mV `u16/1000` |
| READ_BLE_ID | 0x84 | BLE info | ble id `[0:8]`, ble fw `u16@8`, name `str(50,16)`, **i2s tag** `str(66,64)` |
| READ_FILE_HEADER | 0x87 | file header | 16 B = `u32` **type, size, version, checksum** (all LE). Payload `<I file_id` only (no offset/length) |
| READ_FILE_LIST | 0x94 | file list | 8-byte `(u32 type, u32 version)` entries; handler keeps only types 87-95 |

**Declared by the firmware but never sent by any app** (behaviour unknown; probed
read-only by `09_scio_probe.ipynb`): `READ_EVENT_LOG` 0x06, `PARAMETER_GET` 0x08,
`BIST` 0x09. The file-list handler reserves the id band 87-95, so a few opcodes
in that range (e.g. 0x88, 0x8A-0x8F, 0x93, 0x95) are unclaimed and are probed too.

Write / state commands - `PARAMETER_SET` 0x07, `SET_INDICATION_LED` 0x0B,
`READY_FOR_WR` 0x0E, `CLEAR_READY_FOR_WR` 0x11, `FILE_DOWNLOAD` 0x81,
`RESET_DEVICE` 0x83, `WRITE_USER_DEVICE_NAME` 0x91, `WRITE_BLE` 0x9A - **are never
sent by this project** and the USB transport / probe refuse them unless you
explicitly opt in.

### Can the firmware be pulled over USB?

**No, not with any command the apps know how to issue.** Every device→host
response is small and structured (spectrum, battery, temperature, ids, file list,
file header). `FILE_DOWNLOAD` (0x81) is host→device only; `READ_FILE_HEADER`
(0x87) returns only the 16-byte header and its request has no offset/length to
stream a body. There is no memory/flash/file-body read command and no raw-opcode
API in the SDK. The only untested surface is the three declared-but-unused
opcodes above and the reserved band; `09_scio_probe.ipynb` probes them safely.

**Probed on real hardware (fw 147): confirmed negative.** `READ_EVENT_LOG`,
`PARAMETER_GET` (all ids/shapes) and `BIST` return nothing; extended
`READ_FILE_HEADER` is ignored (still 16 bytes, no body); `READ_DEVICE_STATUS`
returns a trivial `{0,1}`. So pulling `dsp_op` (32628 bytes on this unit) needs
hardware - see below. The probe did confirm exact file sizes/checksums, which a
flash or JTAG dump can be validated against.

Scan blob body sizes depend on the i2s generation: `-e` firmware gives
1800/1800/1656 bytes (dark/sample/gradient), older `-o` gives 1800/1800/1416.

### Bluetooth LE (reference)

This project uses USB, but the SCiO speaks the same `0xBA` command protocol over
BLE, and the handles below are preserved for future BLE work. The vendor GATT
service is `00003490-0000-1000-8000-00805f9b34fb`, with:

| Role | UUID | Handle (this unit) |
|---|---|---|
| Control (write commands) | `00003492-…` | `0x0029` |
| Reporter (scan-data notifications) | `00003491-…` | replies on `0x0025` |
| Button pressed (notification) | `00003493-…` | `0x002c` reads `0x01` on press |

Standard characteristics: device name `0x2a00` (`00002a00-…`, handle `0x0003`);
system id `00002a23-…` (handle `0x0012`); manufacturer name `0x2a29` (handle
`0x001e`), under services `0x1800`/`0x180a`. Each of `3491`/`3492`/`3493` carries
CCCD/`0x2902` and `0x2901` descriptors.

Over BLE, a command is written to the control characteristic and the response
arrives as 20-byte notifications on the reporter (each prefixed with the sequence
byte, unlike USB). Example scan/calibration sequence seen on the wire (write to
handle `0x0029`):

```
01ba050000                    # read battery state
01ba0e0000                    # ready for white reference
01ba0b0900000000000000000000  # set indication LED (9-byte payload)
01ba040000                    # read temperature
01ba020000                    # sample spectrum (the scan) -> replies on 0x0025
```

With BlueZ you can drive it directly, e.g.:

```bash
sudo gatttool -i hci0 -b <MAC> --char-write-req -a 0x0029 -n 01ba020000 --listen
```

The `05_scio_ble_devel.ipynb` notebook has an unfinished `bleak`-based attempt;
a working BLE transport would reassemble the sequence-prefixed notifications into
`[0xBA, cmd, len, data]` frames (see `scio/protocol.py`).

## Calibration (white reference)

A white reference is the same `SAMPLE_SPECTRUM` command taken with the SCiO in
its cover / on a known white surface. It is stored and reused; the app
recalibrated when it was too old, too many scans had passed, or the CMOS
temperature had drifted. `scio.store.calibration_status` mirrors that logic;
`07_scio_capture.ipynb` writes `scio-wr/1` files under
`01_rawdata/scan_json_calibration/`.

## The opaque-transform problem and bounded key hypothesis

If statistical evidence supports encryption, one testable branch is:

1. **Get the DSP firmware** (`dsp_op`) and the binning tables. They are not on
   the server any more, but both SCiO apps cached them in Android
   SharedPreferences on the phone (see below).
2. **Triage** the artifact (`scio.firmware.triage`): a valid Blackfin LDR image
   is analysable; a high-entropy artifact remains opaque and needs more evidence.
3. **Find the cipher** (`scio.keyrecover.find_signatures`): locate the AES
   S-box / round constants (or XTEA/ChaCha) in `dsp_op`.
4. **Test firmware-derived keys** (`scio.keyrecover.recover`): 16/24/32-byte
   constants near the cipher code, plus standard derivations of the device
   identifiers, are decrypted against real scans and scored by a plaintext
   oracle (a candidate may turn the body into a smooth numeric vector),
   corroborated across several blobs. **No key spaces are
   brute-forced** - only constants actually present in the firmware are tried.
5. **Validate**: decrypt a fixture that also has the server's stored spectrum
   and confirm the derived reflectance matches it.

Run it: `python recover_key.py --scans 01_rawdata/scan_json --firmware 01_rawdata/device_files`.

## How you can help

- **Firmware blobs from an old phone.** If you have (or can borrow) a phone that
  ran the SCiO or SCiO Lab app, extract its cached firmware:
  - rooted: copy `/data/data/com.consumerphysics.consumer/shared_prefs/` (or
    `...researcher`);
  - no root: `adb backup -f scio.ab -noapk com.consumerphysics.consumer`.
  Point `08_scio_keyrecovery.ipynb` at it. The key files are `dsp_op` (id 92)
  and the tables `centers`/`bins`/`nPixelsPerBin`/`deadPixelsIndices` (100-103).
- **Blackfin reverse-engineering.** If `dsp_op` is plaintext, disassembly of the
  BF512 code to find the cipher and key derivation is the fastest route.
- **Hardware.** JTAG/OTP readout of the BF512, or a logic-analyser tap on the
  CMOS-to-DSP bus (captures unencrypted pixels), are the fallback options
  documented in [`documentation/firmware_notes.md`](documentation/firmware_notes.md).

## Repository layout

| Path | What |
|---|---|
| `scio/` | Python package: capture, corpus, evidence, candidate transforms, validation |
| `07_scio_capture.ipynb` | Connect over USB, capture white reference + scans |
| `08_scio_keyrecovery.ipynb` | Load firmware, run key recovery, validate, decode |
| `recover_key.py` | Command-line key recovery |
| `repeatability_key_search.py` | AES search scored by unchanged-target repeatability |
| `embedded_cipher_search.py` | Bounded TEA/XTEA identifier-key search |
| `tests/test_offline.py` | Offline tests (no hardware) |
| `01_rawdata/` | Captured scans, white references, and `log_extracted/` fixtures (raw scan + the server spectrum, for regression) |
| `02_extract_log_scan.ipynb` | Extract scans from old app log files |
| `03/04/06_*.ipynb` | Earlier decoding attempts (superseded by `08`) |
| `09_scio_probe.ipynb` | Safe read-only probing of undocumented USB opcodes |
| `10_scio_evidence_pipeline.ipynb` | Canonical corpus and transform evidence report |
| `capture_matrix.py` | Labeled read-only replicate capture utility |
| `analyze_flash_dump.py` | Compare/carve independently acquired SPI or JTAG dumps |
| `documentation/EVIDENCE.md` | Fact/hypothesis ledger and acceptance gates |
| `documentation/HARDWARE_ACQUISITION.md` | Read-only SPI/JTAG acquisition procedure |
| `documentation/HANDOFF.md` | Onboarding for another programmer taking over |
| `documentation/` | Datasheets, patents, `firmware_notes.md` |
| `archive/` | Superseded scripts/notebooks kept for history |

## License and credits

Software under GPL v3. Logos and icons are trademarks of Consumer Physics.

Thanks to GitHub users [AndreySamokhin](https://github.com/AndreySamokhin),
[onoff0](https://github.com/onoff0), [franklin02](https://github.com/franklin02)
and [JanBessai](https://github.com/JanBessai) for earlier reverse-engineering
help, and to everyone still trying to keep the SCiO usable.

## Changelog

- 2026-09: Added an evidence-led offline pipeline. Earlier encryption, nonce,
  Lockbox and key-location conclusions are now tracked as hypotheses pending
  cross-scan and held-out spectral validation.
- 2023-03: Log extraction and initial (unsuccessful) decoding attempts.
- 2020-05: Moved to Jupyter notebooks; USB scan capture.
