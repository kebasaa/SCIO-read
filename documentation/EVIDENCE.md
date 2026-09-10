# SCIO decoding evidence and hypothesis ledger

This document separates observations from interpretations. Update it whenever
new captures or artifacts change the evidence.

## Established from local captures and decompiled apps

- Command `0x02` returns dark, sample and gradient blobs in that order on the
  available firmware.
- The Android apps Base64-encoded the returned bytes directly and sent all
  three sample blobs plus a white-reference triplet to the server.
- The Android apps did not calculate the returned spectrum locally.
- Available `-e` blobs are 1800/1800/1656 bytes. Their first little-endian word
  is 0 for dark/sample and 110 for gradient.
- The second word varies between blobs, including blobs from the same scan.
- Archived responses contain 331 values associated with 740–1070 nm.
- In the technical-support CSV, the final `spectrum_*` vector equals
  `sample_raw_* / wr_raw_*` wavelength-by-wavelength to numerical precision
  across 145 numeric rows. These are already spectral-domain server columns;
  they are not plaintext equivalents of the opaque device packets.
- Only firmware/table headers are currently present locally; their bodies have
  not been recovered from the device.
- The connected fw147 device reports file type 87 as a 119,233-byte BLE image,
  although the inspected 2017 Android enum labels type 89 as `ble`. Type 89 is
  empty on this unit. This version discrepancy is preserved rather than forced
  into one enum.
- `READ_BLE_ID` contains the stable ASCII serial fragment `DF1816004A` at bytes
  40–49, immediately before the device-name field. It is included in bounded
  identifier-key tests.
- Thirty new scans of one unmoved target were captured on 2026-09-07. The full
  corpus now contains 82 records and 324 blobs.
- Treating the body directly as an 8-bit, 12-bit, or 16-bit raster (both byte
  orders, C/F order, and every factorized width 8–128) produced no image
  signature or repeatable spatial structure. Across the full corpus the median
  within-label pixel correlation was -0.00085 and the best spatial score was
  0.099. This rejects a *direct* image representation, not an image hidden by a
  transform.

## Open hypotheses

| Hypothesis | Supporting evidence | Missing proof |
|---|---|---|
| Packed sensor/bin data | Sizes are compatible with several integer/bit layouts | Stable cross-scan structure and physical ordering |
| Compression | High entropy and varying payloads can result from compression | A valid stream or reproducible decompressor |
| Obfuscation | Device-side transform is plausible | Reversible algorithm consistent across held-out scans |
| Encryption | 16-byte alignment, high entropy, few repeated blocks | Identified cipher/IV/key and validated plaintext |
| Identifier-derived key | DSP/device/sensor/BLE IDs are available to firmware | A derivation that passes exact cross-scan validation |
| Key or algorithm in `dsp_op` | The artifact name suggests operational DSP code | Actual file body and identified implementation |

## Established spectral-domain calculation

For the archived technical-support export:

`reflectance[wavelength] = sample_raw[wavelength] / wr_raw[wavelength]`

Therefore the central reverse-engineering problem is now narrower: recover the
331-point sample-domain and white-reference-domain vectors from their respective
opaque dark/sample/gradient triplets. Do not apply packet-level subtraction or
division until a candidate transform demonstrates that those operations belong
before the server's exported `sample_raw`/`wr_raw` stage.

The BF512 supporting Lockbox establishes capability only. It does not show that
this SCIO configuration enabled Lockbox or that scan packets are encrypted.

## Acceptance rules

- Smoothness is a screening signal only.
- A transform must generalize across held-out material and calibration sessions.
- Replicate spectra require median Pearson correlation >= 0.98 and median
  spectral angle <= 0.10 radians.
- Claimed wavelength registration requires median held-out shape correlation
  >= 0.90 with archived server spectra after one affine amplitude normalization.
- If cryptographic protection is demonstrated but no local key/implementation
  exists, report that blocker instead of emitting a synthetic spectrum.

## Identifier/key hypothesis run (2026-09-07 implementation pass)

The current `01_rawdata/scan_json` corpus contributed serial, Aptina/device,
DSP, BLE and version fields. The bounded AES run tested 2,111 unique keys from
2,226 named derivations across the supported modes and header-based IV schemes.
No candidate reached the 0.60 screening threshold. The best score was 0.083,
consistent with a negative result. This rejects only the enumerated AES/KDF/IV
combinations; it neither proves encryption nor rules out other transforms.

An additional oracle then stopped assuming that valid plaintext must be a
smooth spectrum: it scored cross-capture repeatability over u8/u16/u32 views,
byte orders, and offsets. Results were negative for:

- 373 single-identifier AES keys;
- 1,825 unique AES keys including pairwise identifier/version constructions;
- 1,144 extra AES constructions specifically involving the printed case serial
  or the device-reported serial fragment; and
- 198 16-byte identifier keys under TEA and XTEA, both endiannesses, and ECB/
  CBC interpretations (1,584 transforms).

All best repeatability scores were approximately 0.120 and occurred only on
the initial pair, consistent with multiple-testing maxima rather than a hit;
the provisional acceptance threshold is 0.50. Separately, 576 small stream/
PRNG transforms (three common LCGs, xorshift32, MT19937, SHA-256 counter;
identifier/header seed variants; XOR/add) had best median repeat correlation
0.031 and no decompression hit. These are bounded negative results only.

## Firmware readback evidence (connected fw147 unit)

The live file list exposes types 87, 90, 91, 92 and 100–103. Type 87 is a
119,233-byte version-125 BLE runtime image; type 92 is the 32,628-byte DSP
operational image. `READ_FILE_HEADER` returns exactly one framed 16-byte header,
with no trailing body. Invalid IDs 80–86, 93–98 and 104–110 returned one fixed
sentinel (`020aa1021013ffffffffff02101bffff`); ID 88 returned a different fixed
16-byte value. Repeated passes were identical and not address-dependent.
Together with the decompiled host-to-device-only download path, this gives no
evidence for a USB firmware-body read operation. Guessed non-empty reserved
commands were not sent because their state-changing behavior is unknown.
The exact headers and sentinel groups are preserved in
`dev/analysis_output/live_device_file_audit.json`.

## Controlled capture matrix

Using `07_scio_capture.ipynb`, preserve raw bytes and capture:

1. 30 scans of one unmoved target under unchanged conditions.
2. 10 white-reference scans without repositioning.
3. 10 covered/dark scans.
4. 10 mirror scans and 10 scans at each available neutral reflectance level.
5. A second series after reconnecting, and after rebooting if practical.

Record device metadata, temperature, calibration path, timestamps, target label,
reposition/reboot events and operator notes. Never overwrite raw observations.
