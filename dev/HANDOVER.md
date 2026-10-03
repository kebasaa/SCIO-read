# Offline-decoding handover

The short, current answer to "where is the offline decoder, and what should I try
next?". The full chronological record is [RECOVERY_STATUS.md](RECOVERY_STATUS.md);
device facts are in [DEVICE_FUNCTION_REFERENCE.md](DEVICE_FUNCTION_REFERENCE.md);
how to work in this repository is in
[`../documentation/HANDOFF.md`](../documentation/HANDOFF.md).

> **Maintenance rule.** Whoever starts a work session updates this file *first*:
> delete tasks that are finished (move their one-line result into "Current state"
> or "Do not repeat"), revise the remaining ones, and fix any other document the
> new work invalidates. This file must describe the present, not the history.

## Current state

**Established**

- The server computes reflectance as a sample-domain quantity divided by a
  white-domain quantity. The response table is multiplicatively separable to
  ~1e-16 with no fitted parameters, and swapping roles exposes a stable non-unity
  self-response factor C(λ) (1.022–1.055 over 740–1070 nm).
  [separability](analysis_output/recovery_20261003_followup/separability_live/verification.json),
  [symmetry](analysis_output/recovery_20261003_followup/symmetry/self_response_factor.json)
- Dark handling is not additive, not a per-band affine map, not a shared scalar gain,
  and C is not a low-order polynomial.
  [dark affine](analysis_output/recovery_20261003_followup/dark_affine/comparison.json),
  [response structure](analysis_output/recovery_20261003_followup/response_structure.json)
- Sample and dark blobs are integrity-protected: any edit gives
  `Bad_sample_signature`. Gradient edits, omission and zero-fill are accepted with
  an unchanged spectrum. ([`ciphertext_oracle/`](analysis_output/ciphertext_oracle/))
- Blob = 8-byte header (word 0 type/status, gradients carry 110; word 1 fresh per
  blob) + fixed-size body: 1792 B sample/dark, 1648 B gradient on `-e` firmware,
  1408 B gradient on `-o`. Body ≈ 7.9 bits/byte, positionally featureless; 30 captures
  of an unchanged target are at 0.49986 bit distance from each other.
- **No supervised leakage.** Sample and dark bodies carry no fixed-position
  information about the server spectrum: 96 permutation tests (bits, bytes, u16
  LE/BE × mean, log-mean, slope, PC1–3 × max-|r| scan and grouped-CV ridge, 92
  records, 10,000 within-acquisition permutations) give 4.2% below p = 0.05,
  median p 0.50, best held-out R² below zero. The same detectors find a single
  fixed-position u16 field carrying the signal level at p ≈ 0.002 on synthetic
  fixtures of this size, and never flag the encrypted twin.
  [leakage](analysis_output/leakage_20261003/leakage.json). This points away from
  a plain fixed-rate coder of counts and toward encryption (or a coder whose
  fields do not sit at fixed positions); it is not proof of encryption.
- Every supplied app path (Java 2017, Lab 1.3.12, Flutter 1.5.6 ARM64, 1.5.19 ARM32)
  is a Base64 pass-through. No client-side decoder exists in any supplied APK.
- No firmware body is available: USB exposes file headers only (`0x81` is a
  host-to-device write); the upgrade endpoint returns `new_version: null`.
- Reference truth: 92 records in `02_processed_data/` carry a spectrum the server
  returned for exactly those bytes; 42 of them additionally carry the 2020/21
  spectrum. Six fresh cap scans (18 blobs) are **frozen** for prospective
  confirmation ([manifest](analysis_output/recovery_20261003_followup/fresh_reference_validation.json)).

**Not established**

- Whether the body is encrypted, or coded with position-shifting (entropy-coded)
  fields. Plain fixed-position coding is now disfavoured (see leakage above).
- Where the transform runs: BF512 DSP, CC2540 BLE SoC, or (decoding side) the server.
- Key architecture, absolute sample/white domain vectors, pixel geometry, table contents.

**Hardware** (SparkFun teardown, see references): ADSP-BF512 Blackfin DSP,
AS4C8M16SA 128 Mbit SDRAM, CC2540F256 BLE SoC (256 KB internal flash, hardware
AES), three unidentified ICs beside the SDRAM, and a custom sensor with **12
receptors**, each with its own filter, aperture and lens over a wire-bonded
photodiode array.

## Open tasks, ranked

With the leakage negative, software-only discrimination of the body is close to
exhausted; the firmware (tasks 1–2) is the decisive input.

### 1. Identify the boot flash from the teardown photos

- The BF512 has no internal program flash unless it is an `F` variant (check the
  marking against the ADI datasheet rather than assuming). Its boot stream (LDR)
  must come from somewhere: one of the three unidentified ICs is the prime
  candidate for an SPI flash.
- Map SPI/JTAG test points from the high-resolution photos.
- **Output:** a read-only dump plan. Physical work is a separately authorised session.
- **Validate** any dump against known headers, e.g. `dsp_op` 32,628 B, v147,
  checksum 4151168; `dsp_boot` 7,284 B; `dsp_dec` 14,600 B (README §5).

### 2. CC2540F256 debug-lock status

- Read-only status query over the TI debug interface. **Never erase-to-unlock.**
- File 87 (119,233 B BLE runtime) fits its flash, and it has hardware AES, so it is
  a serious candidate for where encryption/signing happens.

### 3. Sensor-geometry constraints

- Does a 12-sub-aperture layout fit the table sizes (`deadPixelsIndices` 1714 B,
  `nPixelsPerBin` 1166 B, `bins` 140 B, `centers` 96 B) and the body sizes
  (1792 / 1648 / 1408)? A constraint for any codec hypothesis, not a decode.

### 4. Static trace of `/v1/external_sdk/intermediate_scan`

- Live route (401 on POST). Trace request/response models in the 2017 researcher
  source, Lab 1.3.12 and 1.5.x DEX. No credential extraction or use.

### 5. Gradient blob

- Ignored by the server, header 110, generation-dependent size. Compare its
  statistics with sample/dark; test whether it is less protected or structured.

### 6. Documentation consolidation

- `dev/README.md` still states, as settled, that every modified blob is rejected,
  that all routes are exhausted, that JPEG is excluded, that the firmware endpoint
  is decommissioned, and that the device holds two secrets. Correct those against
  RECOVERY_STATUS and this file.

## Do not repeat

Each is a bounded negative with saved evidence; repeat only with a genuinely new
hypothesis that the earlier run could not have seen.

| Route | Evidence |
|---|---|
| Identifier-derived keys (≈220k configurations, corrected framing) | [key_search_confirmed](analysis_output/recovery_20261003/key_search_confirmed.json), [foreign](analysis_output/recovery_20261003/key_search_foreign.json) |
| Generic compression and word-swap/bit-reverse representations | [compression_only](analysis_output/recovery_20261003/compression_only.json), [representation_codecs](analysis_output/recovery_20261003_followup/representation_codecs.json) |
| Headerless baseline-JPEG Huffman parsing | [jpeg_entropy](analysis_output/recovery_20261003_followup/jpeg_entropy.json) |
| Unknown-polynomial CRC, seeded Murmur/FNV/DJB2 | [unknown_crc](analysis_output/recovery_20261003_followup/unknown_crc.json), [seed](analysis_output/recovery_20261003_followup/unknown_checksum_seed.json) |
| APK/DEX/native/resource/container scans for firmware or tables | [routes v2](analysis_output/recovery_20261003_followup/firmware_routes_summary_v2.json), [containers v2](analysis_output/recovery_20261003_followup/firmware_containers_v2.json) |
| 1.5.19 gradient diagnostic labels (Base64 length checks only) | [validation_trace](analysis_output/recovery_20261003_followup/validation_trace.json) |
| Mock fixtures (duplicates of 2017 source constants) | [mock comparison](analysis_output/recovery_20261003_followup/mock_constant_comparison.json) |
| Server bit-flip/mutation oracles (closed by the signature) | [`ciphertext_oracle/`](analysis_output/ciphertext_oracle/) |
| Firmware-endpoint polling | [server recheck](analysis_output/recovery_20261003_followup/firmware_server_recheck/summary.json) |
| Supervised leakage, fixed-position linear (bits/bytes/u16) | [leakage](analysis_output/leakage_20261003/leakage.json) |
| Same-target bit agreement | README §4 (0.49986 bit distance over 30 captures) |

## Closed for this owner

- The original 2015 phone and its app-data backup (unavailable).
- Lab-portal `sample_raw`/`wr_raw` export (no working credentials).
- USB body readback: headers only; `FILE_DOWNLOAD` is a write.

## Ground rules

- `01_rawdata/` is append-only. `src/` and `dev/` stay decoupled.
- Vendor-server requests need the owner's explicit approval, ≥20 s spacing, and a
  saved plan before sending. No device writes, resets or protection changes.
- Private material (decompiled sources, raw pools, responses) goes in
  `dev/private/` (git-ignored).
- Tests: `python -m pytest tests` and `python dev/scripts/test_without_network.py`.

## References

- [RECOVERY_STATUS.md](RECOVERY_STATUS.md), [NATIVE_ANALYSIS.md](NATIVE_ANALYSIS.md),
  [DEVICE_FUNCTION_REFERENCE.md](DEVICE_FUNCTION_REFERENCE.md)
- [`../documentation/HARDWARE_ACQUISITION.md`](../documentation/HARDWARE_ACQUISITION.md)
- SparkFun teardown with board photos:
  <https://learn.sparkfun.com/tutorials/scio-pocket-molecular-scanner-teardown-/all>
