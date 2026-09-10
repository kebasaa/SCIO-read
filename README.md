<!-- markdownlint-disable MD013 -->

# The SCiO spectrometer: a technical reference

The Consumer Physics **SCiO** is a pocket near-infrared spectrometer, sold
2015-2019 and now discontinued. It has no offline mode: the device emits opaque
blobs and a vendor server turns them into spectra. This repository documents the
device end-to-end - transport, framing, every command, the data formats, the
calibration rules and the server API - and provides a working Python
implementation, so that a SCiO you own stays usable.

Two paths exist:

| | status |
|---|---|
| **Capture -> vendor server -> spectrum** | **works.** Verified against 2020/2021 stored spectra to ~1e-15. Needs an active Consumer Physics account. |
| **Capture -> spectrum, offline** | **unsolved.** The blobs are encrypted on the device's DSP; see [`dev/README.md`](dev/README.md). |

Capture itself needs **no network**. A scan is written as a self-contained
record and can be converted to a spectrum later, from anywhere. That separation
is the point: the server may be switched off at any time, and a record captured
today must still be convertible the day someone breaks the offline path.

---

## Contents

1. [Quick start](#1-quick-start)
2. [Transport](#2-transport)
3. [Command reference](#3-command-reference)
4. [Scan data anatomy](#4-scan-data-anatomy)
5. [Firmware and calibration files](#5-firmware-and-calibration-files)
6. [White reference and calibration](#6-white-reference-and-calibration)
7. [Server API](#7-server-api)
8. [Practical gotchas](#8-practical-gotchas)
9. [Repository layout](#9-repository-layout)

---

## 1. Quick start

```bash
conda env create -f scio_env.yml      # or: conda activate tp
jupyter lab 01_scio_scan_to_spectrum.ipynb
```

Notebook `01_scio_scan_to_spectrum.ipynb` is the whole workflow: name the scan,
connect, capture, upload, plot. Everything it does is a call into `src/scio/`:

```python
import sys; sys.path.insert(0, "src")
from scio import credentials, session, usb

dev  = usb.ScioUSB("COM5").open()
path = session.capture(dev, "bark", comment="north-facing trunk")   # offline
dev.close()

out = session.process(path, credentials.get_token())                # online, later
```

Raw records land in `01_rawdata/scans/`, spectra in `02_processed_data/`.
`session.process_pending()` uploads a backlog whenever you next have a
connection.

Three notebooks, numbered by role - `01` is the one to open:

| notebook | what it is for |
|---|---|
| `01_scio_scan_to_spectrum.ipynb` | the full workflow: annotate, connect, capture, upload, plot |
| `02_scio_device_health.ipynb` | identifiers, battery, temperature, firmware file headers |
| `03_scio_probe.ipynb` | read-only probing of undocumented opcodes |

All three import only `scio`; offline-decoding research is in `dev/notebooks/`,
and superseded notebooks are in `archive/notebooks/`.

**The device must be fully awake.** A steady blue LED means it answers commands.
A slow light/dark pulse means it is idle or charging, and its USB endpoint goes
silent or disappears. Fix: unplug, long-press off, long-press on until steady
blue, replug. It re-idles by itself after a period without commands.

---

## 2. Transport

### USB CDC

The SCiO enumerates as a Texas Instruments CDC serial port, **VID:PID
`0451:16AA`**. Baud rate is irrelevant (it is a USB CDC device, not a real UART);
DTR/RTS handling does not matter. Responses arrive as one contiguous frame.

### Bluetooth LE

The same `0xBA` command protocol runs over BLE. This project uses USB, but the
BLE facts are recorded here because they are hard to rediscover. Vendor GATT
service `00003490-0000-1000-8000-00805f9b34fb`:

| Role | UUID | Handle (this unit) |
|---|---|---|
| Control (write commands) | `00003492-…` | `0x0029` |
| Reporter (scan-data notifications) | `00003491-…` | replies on `0x0025` |
| Button pressed (notification) | `00003493-…` | `0x002c`, reads `0x01` on press |

Standard characteristics: device name `0x2a00` (handle `0x0003`), system id
`00002a23-…` (`0x0012`), manufacturer name `0x2a29` (`0x001e`), under services
`0x1800`/`0x180a`. Each of `3491`/`3492`/`3493` carries CCCD (`0x2902`) and
`0x2901` descriptors.

A command is written to the control characteristic; the response arrives as
20-byte notifications on the reporter, **each prefixed with the sequence byte**
(unlike USB, where the frame is contiguous). A real scan sequence, written to
handle `0x0029`:

```text
01ba050000                    # read battery state
01ba0e0000                    # ready for white reference
01ba0b0900000000000000000000  # set indication LED (9-byte payload)
01ba040000                    # read temperature
01ba020000                    # sample spectrum -> replies on 0x0025
```

With BlueZ:

```bash
sudo gatttool -i hci0 -b <MAC> --char-write-req -a 0x0029 -n 01ba020000 --listen
```

`archive/notebooks/05_scio_ble_devel.ipynb` holds an unfinished `bleak` attempt.
**Why it failed, so the next attempt does not repeat it:** it wrote the command to
the control characteristic and then called `read_gatt_char` on that *same*
characteristic to get the answer. Replies never arrive there - they arrive as
notifications on the **reporter** characteristic, which must be subscribed to
first. (It also wrote the ASCII string `"01ba040000"` rather than the five bytes
`bytes.fromhex("01ba040000")`, so the device received garbage either way.)

A working BLE transport only needs to subscribe to the reporter and reassemble
the sequence-prefixed 20-byte notifications into `[0xBA, cmd, len, data]` frames;
the parsers in `src/scio/protocol.py` then apply unchanged.

### Framing (both directions, both transports)

```text
[seq, 0xBA, cmd, len_lo, len_hi, payload...]
```

| field | size | meaning |
|---|---|---|
| `seq` | 1 B | sequence counter; `0x01` for a first/only packet |
| `0xBA` | 1 B | protocol marker (`-70` as a signed Java byte) |
| `cmd` | 1 B | command id, see below |
| `len` | 2 B | payload length, **little-endian uint16** |
| `payload` | `len` B | command-specific |

**There is no CRC or checksum.** A response reuses the same layout, so a reader
should hunt for the `0xBA` marker and resynchronise rather than assume alignment
- `scio.usb.ScioUSB._read_response` does exactly that.

Some commands answer with **several** frames back to back: `SAMPLE_SPECTRUM`
returns two or three, one per blob.

---

## 3. Command reference

Legend: **R** read-only (safe), **W** writes or changes device state (this
project never sends these), **X** declared in the app but unimplemented on this
firmware (147) - probed on hardware, logs in `01_rawdata/probe_logs/`.

The **app symbol** column names the method or constant in the decompiled Android
app that issues each command. Those names are the way back into the
decompilation if you ever need to re-derive a layout; keep them.

### Read commands

| cmd | name | request payload | response | app symbol | notes |
|---|---|---|---|---|---|
| `0x00` | READ_DEVICE_STATUS | - | 8 B: two `u32` LE, observed `{0, 1}` | `CommandIDs.READ_DEVICE_STATUS` | **R** |
| `0x01` | READ_DEVICE_ID | - | ≥26 B, see below | `performReadDeviceId` | **R** |
| `0x02` | SAMPLE_SPECTRUM | - | 2 or 3 frames of blob data | `performSpectrum` | **R** (capture; persists nothing) |
| `0x04` | READ_TEMPERATURE | - | 12 B: three `u32` LE | `performReadTemperature` | **R** |
| `0x05` | READ_BATTERY_STATE | - | 8 B, see below | `performReadBattery` | **R** |
| `0x84` | READ_BLE_ID | - | ≥130 B, see below | `performReadDeviceBleId` | **R** |
| `0x85` | READ_BLE_STATUS | - | ble status | `CommandIDs.READ_BLE_STATUS` | **R** |
| `0x87` | READ_FILE_HEADER | `<I` file_id | **exactly 16 B**: four `u32` LE | `performReadFileHeader`, via `SCiOBLeService.performReadFileHeader(int)` | **R** |
| `0x94` | READ_FILE_LIST | - | *n* × 8 B `(u32 type, u32 version)` | `performReadFileList`, via `SCiOBLeService.performReadFileList()` | **R** |
| `0x9B` | READ_BLE | - | ble config | `CommandIDs.READ_BLE` | **R** |

**`0x01` READ_DEVICE_ID**

| offset | size | field |
|---|---|---|
| `[0:8]` | 8 B | DSP id (hex, lowercase) |
| `[8:16]` | 8 B | unclassified |
| `[16:24]` | 8 B | Aptina id, stored with **16-bit words byte-swapped** |
| `[24:26]` | 2 B | firmware version, `u16` LE |

`device_id` - the value the server wants - is the Aptina field with each 4-hex-char
group `abcd` rewritten as `cdab`, then **uppercased**:
`328045ab1161f198` -> `8032AB45611198F1`.

**`0x04` READ_TEMPERATURE** - three `u32` little-endian words:

```text
cmos_t = (w0 - 375.22) / 1.4092        # Aptina CMOS sensor, degC
chip_t = w1 / 100.0                    # DSP chip, degC
obj_t  = w2 / 100.0                    # object; 0.0 on this unit
```

The Android app truncates to integer **twice**:
`cmos_t_app = trunc(trunc(raw - 375.22) / 1.4092)`, so raw `404` gives **19**,
not `20.42`. This matters: the calibration temperature rule compares the
truncated value. `parse_temperature` returns `cmos_t`, `cmos_t_app` and
`raw_u32` so nothing is lost.

**`0x05` READ_BATTERY_STATE**

| offset | type | field |
|---|---|---|
| `0` | `u16` | charge % |
| `2` | `u8` | health % |
| `3` | `u8` | health status |
| `4` | `u16` | charging status |
| `6` | `u16` | voltage, mV (divide by 1000) |

An early notebook read the charging status as `0` = not charging, `4` = full,
`6` = battery error, anything else = charging. Treat that as an **unverified
hypothesis**: the code carrying it masked the byte with `& 3` before comparing
against 4 and 6, so its own branches were unreachable and the mapping was never
exercised. `parse_battery` returns the raw value and interprets nothing.

**`0x84` READ_BLE_ID**

| offset | size | field |
|---|---|---|
| `[0:8]` | 8 B | BLE id (hex) |
| `[8:10]` | 2 B | BLE firmware version, `u16` |
| `[40:50]` | 10 B | device serial fragment (NUL-padded string) |
| `[50:66]` | 16 B | user device name |
| `[66:130]` | 64 B | **`i2s_tag_config`**, e.g. `20150812-e:PRODUCTION` |

The i2s ("image to spectrum") tag identifies the binning-table generation and is
**mandatory** in every server request. A dropped BLE-ID read leaves it empty and
silently produces unusable scans, so `read_device_info` retries and flags
`i2s_tag_missing`.

**`0x87` READ_FILE_HEADER** - request `struct.pack("<I", file_id)`. The response
is **always 16 bytes**: `(type, size, version, checksum)` as four `u32` LE.
Appending an offset/length to the request is ignored - there is no readback path
(see [§5](#5-firmware-and-calibration-files)).

**`0x94` READ_FILE_LIST** - a flat array of 8-byte `(u32 file_type, u32 version)`
entries covering the 87-95 band.

### Write / state-changing commands

Never sent by this project. `ScioUSB` refuses them unless `allow_write=True`.

| cmd | name | app symbol | notes |
|---|---|---|---|
| `0x03` | SET_SAMPLE_SETTINGS | - | unused by the app |
| `0x07` | PARAMETER_SET | `CommandIDs.PARAMETER_SET` | **W** |
| `0x0B` | SET_INDICATION_LED | - | **W**, 9-byte payload |
| `0x0E` | READY_FOR_WR | `performReadyForWR` | **W**, LED/UX hint so the device button can trigger a white reference; firmware ≥ 144 |
| `0x11` | CLEAR_READY_FOR_WR | `performClearReadyForWR` | **W**, counterpart of `0x0E` |
| `0x81` | FILE_DOWNLOAD | `performFileDownload` | **W**, host->device **only** - it uploads firmware, it does not read it |
| `0x83` | RESET_DEVICE | `CommandIDs.RESET_DEVICE` | **W**, disruptive |
| `0x91` | WRITE_USER_DEVICE_NAME | `CommandIDs.WRITE_USER_DEVICE_NAME` | **W** |
| `0x9A` | WRITE_BLE | `CommandIDs.WRITE_BLE` | **W** |

### Declared but unimplemented (firmware 147)

All probed on real hardware:

| cmd | name (app symbol) | observed |
|---|---|---|
| `0x06` | READ_EVENT_LOG (`CommandIDs.READ_EVENT_LOG`) | **X** no response |
| `0x08` | PARAMETER_GET (`CommandIDs.PARAMETER_GET`) | **X** no response |
| `0x09` | BIST (built-in self test) | **X** no response |
| `0x88`, `0x89`, `0x93`, `0x95` | reserved band | valid frame returned, **empty body** |
| `0x8A`-`0x8F` | reserved band | no response |

---

## 4. Scan data anatomy

`SAMPLE_SPECTRUM` (`0x02`) returns one frame per blob. How many depends on the
firmware (`DeviceInfo.java`):

- firmware < 136 -> **2** frames (dark, sample);
- firmware ≥ 153 with gradient sampling disabled -> **2**;
- otherwise -> **3** (dark, sample, gradient).

**Wire order is dark, sample, gradient.**

Sizes depend on the i2s generation:

| i2s tag | sample | dark | gradient |
|---|---|---|---|
| `…-e:…` (this unit) | 1800 B | 1800 B | 1656 B |
| `…-o:…` (older) | 1800 B | 1800 B | 1416 B |

Each blob is:

```text
[0:4]   u32 LE  type      0x00 for sample and dark, 0x6E (110) for gradient
[4:8]   u32 LE  varies per scan - a nonce/IV counter is the leading hypothesis,
                but this is NOT proven
[8:]            body: an exact multiple of 16 bytes, ~7.9 bits of entropy per byte
```

The first `u32` of the **sample** response frame doubles as a status word (`0`
on a healthy scan).

Handy check when reading base64 by eye: sample / dark / white / white-dark all
begin `AAAAA` (leading `u32` = 0), while the two gradient blobs begin `bgAAA`
(`0x6E`). A blob whose base64 starts with anything else is not a SCiO scan blob.

What is established about the body: it is high-entropy, AES-block-aligned, and
repeated scans of a physically unchanged target share **no** ciphertext blocks -
so it is not ECB, and something per-scan varies. What is *not* established: the
cipher, the mode, the key location, or whether compression or packing is applied
first. See [`dev/README.md`](dev/README.md) for the full negative result.

---

## 5. Firmware and calibration files

`READ_FILE_LIST` / `READ_FILE_HEADER` expose the device's stored files.

A `READ_FILE_HEADER` response is `(type, size, version, checksum)`. Read from
this fw-147 unit (`01_rawdata/device_files/`):

| id | name | size | version | checksum |
|---|---|---|---|---|
| 87 | `ble_runtime` | 119233 B | 125 | 12925168 |
| 89 | `ble` | *absent* (`0xFFFFFFFF` in every word) | | |
| 90 | `dsp_boot` | 7284 B | 17 | 688456 |
| 91 | `dsp_dec` | 14600 B | 12 | 1548938 |
| 92 | **`dsp_op`** | **32628 B** | 147 | 4151168 |
| 100 | `deadPixelsIndices` | 1714 B | 3 | 97267 |
| 101 | `centers` | 96 B | 3 | 6080 |
| 102 | `bins` | 140 B | 3 | 13587 |
| 103 | `nPixelsPerBin` | 1166 B | 3 | 36371 |

`dsp_op`'s version equals the device firmware version, and the three table files
share version 3. Use the size and checksum to validate any flash dump.

The 2017 Android enum calls the BLE image type **89**; this fw-147 device reports
type **87** as a 119233-byte BLE image. Both observations are kept in
`protocol.FIRMWARE_FILES` rather than reconciled away.

**Only headers can be read back. Bodies cannot.** `FILE_DOWNLOAD` (`0x81`) writes
to the device; `READ_FILE_HEADER` returns 16 bytes and ignores any offset. There
is no other candidate opcode - the reserved band was probed exhaustively. This is
why offline decoding is blocked: `dsp_op` contains the image-to-spectrum code and
presumably the key, and the only ways to obtain it are an external SPI-flash dump,
BF512 JTAG, or a phone that cached it (see
[`documentation/HARDWARE_ACQUISITION.md`](documentation/HARDWARE_ACQUISITION.md)).

Both SCiO apps cached these files in Android SharedPreferences
(`/data/data/com.consumerphysics.consumer/shared_prefs/`) as base64 with a 4-byte
little-endian checksum prefix, listed in a `firmware.file.names` string-set. The
consumer app deletes them after a **completed** upgrade, so a phone that never
finished one is the best candidate. `dev/scio_offline/firmware.py` extracts them.

---

## 6. White reference and calibration

A white reference (WR) is the same `SAMPLE_SPECTRUM` command taken with the SCiO
in its cover, on the white surface inside. It is stored, reused across scans, and
sent to the server with **every** scan.

### The client decides, not the server

This was verified both by reading the decompiled apps and by testing the live
API. `isCalibrationNeeded()` walks these rules in order, each skipped when its
threshold is `<= 0`:

| result | condition |
|---|---|
| `NEVER` | no WR stored, or missing i2s tag / device id |
| `TIME_THRESHOLD` | WR older than `time_diff` |
| `EXCEED_SCANS_LIMIT` | `scans_since_calibration >= scan_diff` |
| `TEMP_THRESHOLD` | \|current CMOS temp − WR temp\| > `temp_diff` |
| `NO_NEED` | otherwise |

Mirrored exactly by `store.calibration_status` / `store.calibration_report`. The
temperature compared is the app's **double-truncated** value (see `0x04` above),
and the WR temperature is the mean of its before/after readings.

Thresholds come from the server but are only advice:

```http
GET /v1/device/calibration_thresholds?device_id=<DEVICE_ID>
-> {"thresholds": {"time_diff": …, "scan_diff": …, "temp_diff": …,
                   "min_scans_for_new_batch": …}}
```

`time_diff` is in **minutes**. For this device the live values are
`time_diff = 1e9`, `scan_diff = 1e9`, `temp_diff = 10000` - every rule
effectively disabled, so **a white reference is needed only when none exists**.
`min_scans_for_new_batch` is parsed by the app but never read by
`isCalibrationNeeded`; it is stored, labelled unused.

**The server never rejects a scan for a stale white reference.** 62 stored scans
plus 2 deliberately mismatched cross-pairs were replayed, including a WR 2289
days old and a pairing whose WR post-dates its scan. All 64 returned spectra. The
experiment is in `02_processed_data/replay_experiment/`; the tool is
`tools/replay_all_scans.py`.

There is a separate, purely advisory quality check:

```http
POST /v1/device/{device_id}/user_calibration
-> {"calibration": {"is_valid": true, "calibration_id": "<uuid>"}}
```

The app stores the WR *before* calling it, and a `false` verdict never un-stores
it.

### Storage

White references are written as `YYYYMMDD_HHMM_calibration.json`, with the same
timestamp inside. **They are never overwritten**: a same-minute save becomes
`..._calibration_2.json`, and "latest" is computed by sorting, so the whole
calibration history is preserved. Legacy `wr_*.json` files are still read.

Every canonical scan record embeds its own WR blobs, temperatures and thresholds,
so a single scan file is self-contained.

---

## 7. Server API

Base: `https://api.consumerphysics.com`. Requests carry
`X-SCiO-Client-Version: Android 1.3.8.554`.

### Login (OAuth implicit flow)

```text
POST /oauth/login       (email + password)
  -> 302 /oauth/authorize
  -> 302 <redirect_uri>#access_token=<token>&expires_in=14&…
```

Tokens are **short-lived** - `expires_in=14`. Fetch a fresh one per request;
`session.process_pending` does. Credentials are asked for once and stored in
`.scio_credentials.enc` (Fernet, PBKDF2-HMAC-SHA256 with 200 000 iterations, key
derived from `getpass.getuser() | platform.node()`), which is gitignored and does
not travel between machines.

An inactive account returns `HTTP 403 {"user_status": "inactive"}`. That is an
account state, not a bug - Consumer Physics can reactivate it.

### Scan -> spectrum

```http
POST /v2/consumer/spectro-scan
```

All twelve fields are required unless noted:

| field | value |
|---|---|
| `device_id` | uppercase 16 hex, from `0x01` |
| `sampled_at` | ISO 8601 with offset and milliseconds |
| `sampled_white_at` | ditto, from the white reference |
| `scio_edition` | `"scio_edition"` |
| `i2s_tag_config` | e.g. `20150812-e:PRODUCTION` - **rejected if empty** |
| `mobile_mac_address` | required; this project sends `02:00:00:00:00:00` |
| `sample` | base64 blob |
| `sample_dark` | base64 blob |
| `sample_white` | base64 blob |
| `sample_white_dark` | base64 blob |
| `sample_gradient` | base64, optional (3-frame firmware) |
| `sample_white_gradient` | base64, optional |
| `widget_scan_attributes` | `[]` |

One further field appears in captured request bodies but is **not required**:
`mobile_GPS` (`latitude`, `longitude`, `locality`, `country`, `admin_area`,
`address_line`), which the phone app attached to every scan. The server accepts
scans without it, so this project does not send it.

Base64 must be **standard alphabet, `=`-padded, newline every 76 characters** -
Android's `Base64.DEFAULT`. URL-safe base64 is rejected.

Response:

```json
{"_type": "POST spectroscan2",
 "spectrum": [ …331 floats… ],
 "wavelengths": {"start": 740, "steps": 1, "num_WL": 331}}
```

giving reflectance at **740-1070 nm in 1 nm steps**.

Error taxonomy seen in the apps and on the wire: `invalid_scan`, `low_signal`,
`high_ambient`, `material_unknown`, `novelty`, `InvalidUsage` (a malformed or
missing field), plus plain HTTP `401`/`403` for auth and transient `502`s.

### Firmware upgrade

```http
GET /v1/device/{ble_id}/firmware-upgrade?…
-> {"new_version": null}     # device already up to date
```

The only firmware-serving endpoint, and it serves nothing for a current device.
Blobs, when present, are base64 with a 4-byte little-endian checksum prefix.

---

## 8. Practical gotchas

- **`device_id` must be UPPERCASE.** Lowercase returns HTTP 404 - proven, see
  `01_rawdata/probe_logs/calibration_v1_thresholds_lowercase.json`.
- **An empty `i2s_tag_config` is rejected outright** (`InvalidUsage`). Thirty
  scans in this repository were captured with an empty tag because a single BLE-ID
  read dropped; they were unusable until the tag was filled in from the device's
  white reference. `read_device_info` now retries and flags the failure.
- **Base64 must be standard, not URL-safe.** One legacy group in this repo stored
  URL-safe unpadded base64; the canonical records re-encode from the
  authoritative hex.
- **The device must be steady blue.** Pulsing = idle/charging = silent USB.
  Power-cycle it.
- **Access tokens expire in seconds.** Fetch one per request.
- **The white-reference decision is yours, not the server's.** If you care about
  photometric accuracy, take a fresh WR; the server will happily accept a
  six-year-old one and return a meaningless number.
- **A smooth curve is not a decoded spectrum.** Random bytes read as float32 look
  smooth. Validation requires agreement with a held-out server spectrum.

---

## 9. Repository layout

| path | contents |
|---|---|
| `src/scio/` | the working library: `protocol`, `usb`, `probe`, `store`, `cloud`, `credentials`, `session`, `logscan`, `corpus`, `reference`, `paths` |
| `01`-`03` notebooks | the three live notebooks (see [§1](#1-quick-start)) |
| `dev/` | offline-decoding research (`scio_offline`, scripts, `notebooks/`, its own tests) - see [`dev/README.md`](dev/README.md) |
| `dev/notebooks/superseded/` | earlier decoding attempts, each labelled superseded, kept as the exploration record |
| `tools/` | `replay_all_scans.py`, `analyze_scan.py`, `check_public_safety.py` |
| `tests/` | offline tests for the working pipeline (`pytest tests/`) |
| `01_rawdata/scans/` | **canonical `scio-scan/2` records** - self-contained, ready to process |
| `01_rawdata/` (rest) | the original captures, untouched: `log_files/`, `log_extracted/`, `scan_json/`, `scan_json_calibration/`, `device_files/`, `probe_logs/` |
| `02_processed_data/` | records **plus** their spectra, and the replay experiment |
| `documentation/` | RE log, hardware acquisition guide, handoff, datasheets, patents |
| `archive/` | superseded notebooks (`notebooks/`), scripts and raw notes (`more_info/`), frozen - see [`archive/README.md`](archive/README.md) |

`01_rawdata/scans/` holds 97 records: 26 from 2020/2021 app logs (each carrying
the spectrum the server returned at the time - a genuine regression target), 17
more recovered from logs that were never mined, 18 from a 2023 USB series, and 36
from 2026. The canonical records are **additional copies**; every original file
is byte-identical to what it was before.

Scans converted from the 2023 series have **no white reference of their own** and
borrow a later one. The server returns a spectrum, but it is not a calibrated
measurement, and every such record says so in `provenance.notes`.

### Tests

```bash
pytest tests/          # working pipeline - passes with dev/ deleted
pytest dev/tests/      # offline-decoding research
```

The two suites are deliberately independent; that is what keeps the strands
decoupled.

---

## License and credits

**This repository is licensed under the GNU General Public License v3.0** - see
[`LICENSE`](LICENSE) for the full text. That covers everything written here: the
`scio` and `scio_offline` libraries, the notebooks, the tools, the tests and this
documentation.

**Not covered by the GPL, and not ours to license:**

- **Consumer Physics documents and trademarks.** SCiO, Consumer Physics and
  related names, logos and marks belong to their owners. The patents reproduced
  under `documentation/` ([`US9377396.pdf`](documentation/US9377396.pdf),
  [`US10330531.pdf`](documentation/US10330531.pdf)) are their filings, included
  for reference only.
- **Other third-party documents**, likewise reference-only: the Analog Devices
  [`ADSP-BF512.pdf`](documentation/ADSP-BF512.pdf) datasheet, and the notes in
  `archive/more_info/` that came from other people.
- **Captured device data** under `01_rawdata/` is measurement output from the
  author's own unit, not third-party material - it is shared under the same GPL
  as the rest.

Nothing here redistributes Consumer Physics firmware, application code or
decompiled sources. This is independent interoperability work on hardware the
author owns, using the vendor's own documented API and the author's own account.

Facts here were established from: the decompiled Android apps (consumer and
researcher/Lab), live probing of a fw-147 device over USB, captured app logs, the
live server API, the Sparkfun SCiO teardown, and the ADSP-BF512 datasheet.
Corrections are welcome - especially anything that turns a stated hypothesis into
a fact, or refutes one.
