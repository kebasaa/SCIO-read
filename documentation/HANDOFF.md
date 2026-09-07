# SCIO-read handoff

Onboarding for a programmer taking over the effort to read and decode a
Consumer Physics SCiO spectrometer offline. Read this, then the README.

## TL;DR / current status

- **Talking to the device works.** Over USB we can read metadata, temperature,
  battery, the firmware file list/headers, run a white reference, and capture
  scans. Validated on the real device (fw 147).
- **Decoding is unresolved.** The bodies are high-entropy and AES-block-sized,
  but packing, compression, obfuscation and encryption remain live hypotheses.
  The second prefix word is not proven to be a nonce.
- **No key location is established.** `dsp_op`, identifiers, serial numbers and
  firmware tables are candidate evidence sources, not confirmed key stores.
- **Negative results so far:** the cloud route is dead; the identifier/KDF set
  tested at the time produced no validated hit; and the probed USB commands did
  not return firmware bodies. These results do not prove encryption. See
  [`firmware_notes.md`](firmware_notes.md).

## How to talk to the SCiO

- **Environment:** conda env `tp` (`<USER_HOME>\.conda\envs\tp`). Has
  numpy, pandas, scipy, matplotlib, pyserial, cryptography, jupyterlab, pytest.
  Run notebooks/scripts with `<USER_HOME>\.conda\envs\tp\python.exe`.
- **Connection:** USB. The SCiO enumerates as a TI CDC serial port, VID:PID
  `0451:16AA` (COM5 on this machine). Framing both ways:
  `[seq, 0xBA, cmd, len_lo, len_hi, payload]`, length little-endian u16.
- **Device quirk (important):** the SCiO answers commands only when fully awake
  (steady blue). When idle/charging it pulses slowly light/dark blue and its USB
  either goes silent or drops off entirely. **Fix:** unplug USB, long-press to
  power off, long-press to power on until steady blue, replug. It also re-idles
  on its own after a period of inactivity (see the timing note in
  `firmware_notes.md` / README).
- **Notebooks / scripts:**
  - `07_scio_capture.ipynb` - connect, health, white reference, capture scans.
  - `09_scio_probe.ipynb` - safe read-only probing of undocumented opcodes.
  - `08_scio_keyrecovery.ipynb` / `recover_key.py` - attempt decoding once you
    have the DSP firmware.
  - `pytest tests/` - offline checks (no hardware), ~40 tests.

## What the code does (`scio/` package)

- `protocol.py` - command opcodes, frame builder, response parsers (pure).
- `usb.py` - `ScioUSB` transport (pyserial): read-only device queries, white
  reference, `sample_spectrum`. Refuses write/state opcodes unless `allow_write`.
- `store.py` - JSON/CSV schemas, base64 wrapping (standard, 76-col, matching the
  app), fixtures, white-reference persistence and staleness (`calibration_status`).
- `firmware.py` - extract/parse DSP firmware & table blobs from a phone's
  SharedPreferences or adb backup; triage (entropy, strings, Blackfin LDR parse).
- `evidence.py` / `corpus.py` - canonical provenance plus neutral statistical
  diagnostics across every local capture.
- `decode.py`, `repeatability.py` and `embedded_cipher_hypothesis.py` - bounded
  AES/TEA/XTEA transforms and cross-capture screening; smoothness is explicitly
  insufficient to validate a key.
- `image_hypothesis.py` and `stream_hypothesis.py` - direct raster-layout and
  weak stream/PRNG tests, both currently negative.
- `keyrecover.py` - bounded candidate tests from firmware constants, serials,
  IDs and version tags. No key-space brute forcing.
- `probe.py` - safety-gated USB opcode probing (allowlist, empty payloads).

Data under `01_rawdata/`: `scan_json/` scans, `scan_json_calibration/` white
references, `device_files/` device info + file headers, `probe_logs/` probe
results, `log_extracted/` fixtures (raw scan + the server's spectrum, for
regression).

## The blocker in detail

- A scan returns three blobs: dark, sample, gradient (1800/1800/1656 bytes on
  `-e` firmware). Each has an 8-byte observed prefix (`u32 type`: 0 for
  sample/dark, 0x6E for gradient; second `u32` unclassified) and a high-entropy,
  16-byte-aligned body. Different repeated bodies are evidence to quantify, not
  proof of a particular cipher or mode.
- **No USB readback path.** Every device->host response is small/structured
  (spectrum, battery, temperature, ids, file list, file header). `FILE_DOWNLOAD`
  (0x81) is host->device only. `READ_FILE_HEADER` (0x87) returns only 16 bytes
  (`type,size,version,checksum`) and ignores appended offset/length. The declared
  but unused opcodes `READ_EVENT_LOG` (0x06), `PARAMETER_GET` (0x08), `BIST`
  (0x09) do not respond; reserved-band `0x88/0x89/0x93/0x95` ack empty,
  `0x8A-0x8F` unimplemented. All probed on hardware; logs in `01_rawdata/probe_logs/`.

## Additional artifact routes (outside the current software-only scope)

1. **External SPI flash dump.** The plain BF512 has no internal flash and boots
   from an external SPI flash (one of three unlabelled ICs on the board;
   identify it by its markings during teardown). Read it with a ~$15 CH341A +
   SOIC-8 clip. Gives `dsp_boot/dsp_dec/dsp_op` as stored (may be Lockbox
   encrypted/signed). `dsp_op` is **32628 bytes** on this unit - use that and the
   checksums below to validate a dump.
2. **BF512 JTAG.** With a Blackfin JTAG/ICE, read OTP + L1 SRAM, or halt the DSP
   during a scan to capture the AES key from RAM/registers directly. Works even
   if the flash image is encrypted, unless Lockbox/OTP has disabled JTAG.
3. **Any old phone/backup with the cached firmware.** Both SCiO apps stored the
   firmware in SharedPreferences (`firmware.file.names` string-set; files under
   the bare enum names, base64 with a 4-byte LE checksum prefix). `scio.firmware`
   already extracts these. The consumer app deletes them after a completed
   upgrade, so a phone that never finished one is best.
4. **Finish/redo USB probing** on other firmware versions - low odds, but cheap.

The step-by-step electrical safety, double-read, carving and validation process
is in [`HARDWARE_ACQUISITION.md`](HARDWARE_ACQUISITION.md). The corresponding
tool is `analyze_flash_dump.py`.

If `dsp_op` is recovered, `firmware.triage` tests for a plaintext LDR and reports
high-entropy artifacts as opaque. Disassembly may reveal packing, compression,
obfuscation or cryptography. A smooth candidate is insufficient: success also
requires cross-scan consistency and held-out agreement with stored spectra.

## Key facts for this unit

- device_id `8032AB45611198F1`; dsp_id `e24da26b2304c2c0`; ble_id `01665900004c99b4`
- firmware 147; i2s tag `20150812-e:PRODUCTION`; name `myScio`
- file header checksums / sizes: `dsp_op`(92) checksum 4151168, **size 32628 B**;
  `centers`(101) 6080 / 96 B; `bins`(102) 13587 / 140 B; `nPixelsPerBin`(103)
  36371 / 1166 B; `deadPixelsIndices`(100) 97267; `dsp_boot`(90) 688456;
  `dsp_dec`(91) 1548938. (Full record in `01_rawdata/device_files/`.)
- Captured corpus: white references and sample scans, including a 30-scan
  unchanged-target series; the current index has 82 records / 324 blobs.

## References

- `documentation/firmware_notes.md` - the living RE log (probe results, cipher-mode
  evidence, checksum notes, hardware options).
- `documentation/ADSP-BF512.pdf` - DSP datasheet (Lockbox, OTP, boot modes, JTAG).
- `documentation/US9377396.pdf`, `US10330531.pdf` - the optics/system patents.
- Teardown: Sparkfun "SCiO Pocket Molecular Scanner Teardown" (BF512, CC2540,
  Alliance SDRAM, 3 unidentified ICs).
