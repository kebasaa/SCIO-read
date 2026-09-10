# SCIO-read handoff

Onboarding for a programmer taking over this project. Read this for *how to work
here*; read [`../README.md`](../README.md) for the device itself - the protocol,
every command, the data formats and the server API live there and are not
duplicated.

## TL;DR

- **Capture works.** Over USB: metadata, temperature, battery, firmware file
  list/headers, white reference, scans. Validated on the real device (fw 147).
- **Scan -> spectrum works** through the vendor server, and is bit-exact: two
  2020 scans replayed today matched their stored spectra to ~2e-15 and 5e-15.
  It needs an active Consumer Physics account.
- **Offline decoding does not work** and is unlikely to without hardware. That
  whole strand lives in [`../dev/`](../dev/README.md); the working pipeline does
  not depend on it.
- The scan store holds **97 canonical records**, including 42 that carry the
  spectrum the server returned in 2020/2021 - a real regression target.

## Environment

conda env **`tp`** (`<USER_HOME>\.conda\envs\tp`): numpy, pandas, scipy,
matplotlib, pyserial, requests, cryptography, jupyterlab, pytest. Run everything
with `<USER_HOME>\.conda\envs\tp\python.exe`.

Nothing needs installing: `conftest.py` puts `src/` and `dev/` on `sys.path` for
tests, notebooks insert `src/` themselves, and scripts import `_bootstrap` first.

```bash
pytest tests/            # working pipeline, offline, ~35 tests
pytest dev/tests/        # offline-decoding research, ~17 tests
```

The two suites must pass **independently** - `pytest tests/` has to work with
`dev/` deleted. If you ever need a flat import across both, you have coupled the
strands and should undo it.

## Layout

```text
src/scio/          the working library
dev/               offline-decoding research (own package, tests, notebooks)
tools/             replay_all_scans.py, analyze_scan.py, check_public_safety.py
tests/             tests for src/scio
01_rawdata/        captures - APPEND ONLY, see below
02_processed_data/ records + spectra
documentation/     this file, firmware_notes.md, HARDWARE_ACQUISITION.md, datasheets
```

`src/scio/`:

| module | role |
|---|---|
| `protocol` | framing and response parsers - **pure**, no I/O, fully unit-tested |
| `usb` | `ScioUSB` transport; refuses write opcodes unless `allow_write=True` |
| `probe` | safety-gated probing of undocumented opcodes (allowlist, empty payloads) |
| `store` | on-disk formats, base64 conventions, white-reference persistence and policy |
| `cloud` | vendor API: login, `spectro-scan`, calibration thresholds, WR validation |
| `credentials` | encrypted, machine-bound credential store |
| `session` | **the workflow**: `capture`, `convert_legacy`, `extract_logs`, `process`, `process_pending` |
| `logscan` | recover scans out of old app logcat dumps |
| `corpus` | inventory of every local capture, sha256-deduplicated |
| `reference` | archived vendor CSV exports |
| `paths` | portable, non-identifying path labels for anything published |

## Working with the device

USB CDC, VID:PID `0451:16AA` (COM5 on this machine). **The SCiO answers only when
fully awake - steady blue.** When idle or charging it pulses light/dark blue and
its USB endpoint goes silent or vanishes entirely. Unplug, long-press off,
long-press on until steady blue, replug. It re-idles on its own after a period
without commands, so keep traffic flowing during a session.

Notebooks, numbered by role: `01_scio_scan_to_spectrum.ipynb` (the workflow),
`02_scio_device_health.ipynb` (identifiers, battery, temperature, firmware file
headers), `03_scio_probe.ipynb` (read-only opcode probing). All three import only
`scio`; offline-decoding notebooks are in `dev/notebooks/`, and superseded ones in
`archive/notebooks/` (frozen - see [`../archive/README.md`](../archive/README.md)).

## The data rules

**`01_rawdata/` is append-only.** Nothing in it is ever modified or deleted.
`session.convert_legacy` and `session.extract_logs` *copy* older captures into
the canonical format; the originals stay authoritative. Verify with a hash
manifest before and after any change that touches it - the only permitted
difference is new files under `01_rawdata/scans/`.

**Canonical record - `scio-scan/2`** (`01_rawdata/scans/*.json`), self-contained
by design so it can be processed years later without this repository:

```text
annotation{name, scan_id, comment}    name is mandatory - a nameless scan is lost data
sampled_at, created_at, scan_uid
device{device_id, i2s_tag_config, firmware_version, …}
temperature{scan_before, scan_after}  float, app-truncated and raw u32
raw{sample, sample_dark, sample_gradient}          each {size, hex, b64}
white_reference{wr_id, sampled_white_at, blobs, temperature_before/after, …}
calibration{status_at_scan, thresholds, thresholds_source, report}
provenance{source, converted_from, notes[]}
reference_spectrum                    the server's answer, when history has one
unused_but_recorded{…}                deliberately kept, clearly labelled
```

The `unused_but_recorded` convention matters: information that the current
pipeline ignores is **kept and labelled**, never dropped. Some of it will be the
key to the offline problem.

Both blob encodings are stored on purpose - `hex` is authoritative, `b64` is
byte-for-byte what the server expects.

**Processed output** (`02_processed_data/*_spectrum.json` + `.csv`) embeds the
entire scan record alongside the spectrum, so it too stands alone.

Where the 97 records came from:

| group | n | note |
|---|---|---|
| 2020/2021 app logs, already extracted | 26 | carry the server's spectrum |
| 2020/2021 app logs, newly mined | 17 | the old notebook dropped scans the server never answered |
| 2023 USB series | 18 | **no white reference exists** - borrows a later one, physically invalid, flagged in every record |
| 2026 USB series | 36 | 30 of them needed the i2s tag repaired |

## Things that will bite you

- **`device_id` must be uppercase** or the API returns 404.
- **An empty `i2s_tag_config` is rejected** and silently ruins a capture session.
  `read_device_info` retries and sets `i2s_tag_missing`; check it.
- **Base64 must be standard, 76-col wrapped** - not URL-safe.
- **Access tokens expire in ~14 s.** Fetch one per request.
- **Never publish a real phone MAC or a home-directory path.** The 2020 log
  fixtures contain a real phone MAC; canonical records deliberately do not
  propagate it, and `tools/check_public_safety.py` guards this. Run it before
  pushing.
- Calibration files are **never overwritten** - same-minute saves get `_2`,
  "latest" is computed by sorting. Don't add a `_latest` copy back.

## What to do next

The working pipeline is done. Useful directions, roughly by value:

1. **A BLE transport.** The protocol is identical; only notification reassembly
   is missing. That frees the device from a cable and from this machine.
2. **Offline decoding** - see [`../dev/README.md`](../dev/README.md). Software
   routes are exhausted; an SPI-flash dump (~$15) or BF512 JTAG is the way in.
   [`HARDWARE_ACQUISITION.md`](HARDWARE_ACQUISITION.md) has the procedure.
3. **Mirror everything now.** The vendor server is the only decoder that exists.
   Every scan worth keeping should be processed and stored before it disappears -
   `session.process_pending()` exists for exactly that.

## Key facts for this unit

- `device_id` `8032AB45611198F1`; `dsp_id` `e24da26b2304c2c0`; `ble_id`
  `01665900004c99b4`; BLE MAC `B4:99:4C:59:66:01`
- firmware 147; BLE firmware 125; i2s tag `20150812-e:PRODUCTION`; name `myScio`
- firmware file sizes/checksums: see the table in the README
- calibration thresholds (live): `time_diff=1e9` min, `scan_diff=1e9`,
  `temp_diff=10000` - every rule off

## References

- [`../README.md`](../README.md) - the device and protocol reference
- [`firmware_notes.md`](firmware_notes.md) - the living RE log: probe results,
  cipher-mode evidence, calibration endpoints, the replay experiment
- [`HARDWARE_ACQUISITION.md`](HARDWARE_ACQUISITION.md) - flash dump / JTAG procedure
- [`ADSP-BF512.pdf`](ADSP-BF512.pdf) - DSP datasheet (Lockbox, OTP, boot, JTAG)
- [`US9377396.pdf`](US9377396.pdf), [`US10330531.pdf`](US10330531.pdf) - the optics
  and system patents
- Sparkfun, "SCiO Pocket Molecular Scanner Teardown" - BF512, CC2540, Alliance
  SDRAM, three unidentified ICs
