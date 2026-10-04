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
- Sample, dark, white and white-dark blobs are integrity-protected: any tested
  change to the second header word or the body gives `Bad_sample_signature`. The
  status bit in header word 0 is not covered (accepted in all six roles), and
  gradient edits, omission and zero-fill are accepted, all with an unchanged
  spectrum. ([`ciphertext_oracle/`](analysis_output/ciphertext_oracle/),
  [RESULTS](analysis_output/recovery_20261003/RESULTS.md))
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
- **The gradient is just as opaque.** Its body matches sample/dark on every statistic
  (entropy at the random expectation, flat histogram, no positional or run structure,
  no repeated blocks), sits 0.4999 bits from the same scan's sample body (so it is not
  derived from it), and shows no spectral leakage (48 tests, Bonferroni p 1.0). The
  server simply does not use it. [gradient](analysis_output/gradient_20261004/gradient.json)
- **Size arithmetic** ([size constraints](analysis_output/size_constraints_20261004/size_constraints.json)):
  no table or body is a whole number of 331 entries at any width, so the tables are
  not plain per-band arrays. `centers` (96 B) splits into 12 × 8 B, consistent with
  one record per receptor. No body splits 12 ways at ≥16-bit width or fits 12-bit
  packing; all are multiples of 16 B. The `-e`/`-o` gradient difference is 240 B
  (15 blocks).
- **"Intermediate scan" means a batch member, not partial decoding.** No DEX method
  references `/external_sdk/intermediate_scan` (a `Config` constant named
  `API_V1_UPLOAD_SCAN`, beside `API_V1_BATCH_ANALYSIS`). In 1.5.19 the consumer
  route `/v1/consumer/intermediate_scans/batch/` goes through the generic API helper
  next to an Applet flag `show_intermediate_results` and the `batch_id` /
  `analyze-batch` / `aggregated-result` workflow: per-scan results within a
  multi-scan batch. Name/co-location inference, not a traced response model.
  [sdk endpoints](analysis_output/sdk_endpoints_20261004/sdk_endpoints.json)
- Every supplied app path (Java 2017, Lab 1.3.12, Flutter 1.5.6 ARM64, 1.5.19 ARM32)
  is a Base64 pass-through. No client-side decoder exists in any supplied APK.
- No firmware body is available: USB exposes file headers only (`0x81` is a
  host-to-device write); the upgrade endpoint returns `new_version: null`, including
  when asked as a firmware-135/136 device (dsp_op `0x88`/`0x87`, all four files old,
  and the 1.2.6.476 app client; 2026-10-04,
  [old-firmware probe](analysis_output/firmware_old_version_20261004/campaign_summary.json)).
- Reference truth: 92 records in `02_processed_data/` carry a spectrum the server
  returned for exactly those bytes; 42 of them additionally carry the 2020/21
  spectrum. Six fresh cap scans (18 blobs) are **frozen** for prospective
  confirmation ([manifest](analysis_output/recovery_20261003_followup/fresh_reference_validation.json)).

**Not established**

- Whether the body is encrypted, or coded with position-shifting (entropy-coded)
  fields. Plain fixed-position coding is now disfavoured (see leakage above).
- Where the transform runs: BF512 DSP, CC2540 BLE SoC, or (decoding side) the server.
- Key architecture, absolute sample/white domain vectors, pixel geometry, table contents.

**Hardware** (full reference with all photos: [`../documentation/HARDWARE.md`](../documentation/HARDWARE.md);
desk review in
[`HARDWARE_ACQUISITION.md`](../documentation/HARDWARE_ACQUISITION.md#teardown-photo-review-2026-10-04)):

- **DSP:** `ADSP-BF512 KBCZ-3`, 300 MHz BGA, with **no on-chip program flash** (datasheet
  Rev E ordering guide). It boots via BMODE straps from external parallel/SPI flash, an
  SPI0 or UART0 host, ≤3 KB OTP, or SDRAM. OTP cannot hold `dsp_op`. Lockbox exists;
  whether it is used is unknown.
- **No standalone flash chip visible** on either face. Legible parts: SDRAM, CC2540F256
  (labelled "9A"), probable ADP5062 charger, two unidentified small QFNs.
- **Hypothesis (unverified):** the CC2540 stores the DSP images and boots the BF512 as a
  host. All reported files together (176,861 B) fit in its 256 KB flash.
- **CC2540 debug-lock state is unknown.** It cannot be read from photos or over USB.
  Debug pins: P2_1 = DD (pin 35), P2_2 = DC (pin 34), plus RESET_N. No labelled header is
  visible; four castellated edge pads by `TP802` are a candidate.
- **Sensor:** 12 receptors in a 3 × 4 grid (filters, apertures of differing size, lenses)
  over a wire-bonded array. The module flex carries its own `FW:9216` sticker.

## Open tasks, ranked

All remaining tasks need a separately authorised hardware session with the device
opened (the housing is not designed to be reopened). Nothing below may write, erase,
reset or change straps or protection.

### 1. Passive boot-traffic capture

- **Goal:** record the DSP's boot stream as it crosses a bus at power-on. Whatever
  BMODE selects (SPI flash, SPI0 host, UART0 host), the LDR data must travel over
  SPI0/UART0 unless it comes from the ≤3 KB OTP. This route is read-only and needs no
  unlocking.
- **First:** with the board unpowered, find accessible test points on the BF512's
  SPI0/UART0 nets and the CC2540's matching peripheral pins. The BF512 is a BGA, so this
  needs continuity tracing, not photos.
- **Validate** the capture against the known headers: `dsp_boot` 7,284 B, `dsp_dec`
  14,600 B, `dsp_op` 32,628 B, v147, checksum 4151168 (README §5), and parse it as LDR
  (`scio_offline.firmware`).

### 2. CC2540F256 debug-lock status

- Locate DD/DC/RESET_N (continuity from pins 35/34), then use a CC Debugger-class tool's
  status/ID readout only. Verify the status command against TI SWRU191 before use.
- **Never accept a chip-erase prompt.** If the chip is locked, record that and stop.
- If it is unlocked, a read-only flash dump would cover the BLE runtime, any AES/signing
  material and, under the hypothesis above, the DSP images.

### 3. External flash or BF512 JTAG (only if task 1 points there)

- HARDWARE_ACQUISITION.md routes A and B, unchanged.

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
| Gradient as a weaker or derived blob | [gradient](analysis_output/gradient_20261004/gradient.json) |
| Size-only layout fitting (12 receptors, 331 bands) | [size constraints](analysis_output/size_constraints_20261004/size_constraints.json) |
| `intermediate_scan` as a decoding endpoint | [sdk endpoints](analysis_output/sdk_endpoints_20261004/sdk_endpoints.json) |
| Looking for a standalone flash chip in the teardown photos | [teardown markings](../documentation/teardown/README.md#markings-read-from-these-photos-2026-10-04) |
| Firmware offer as a firmware-135/136 device; 2-frame scan with the 1.2.6.476 client (null; spectrum identical) | [old-firmware probe](analysis_output/firmware_old_version_20261004/campaign_summary.json) |
| Same-target bit agreement | README §4 (0.49986 bit distance over 30 captures) |

Documentation: `dev/README.md` was reconciled with this file on 2026-10-04 (fixed
container vs fixed rate, JPEG scope, integrity-check scope, firmware endpoint,
key-architecture framing, acceptance gate).

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
- [`../documentation/HARDWARE.md`](../documentation/HARDWARE.md) (hardware reference, photos),
  [`../documentation/HARDWARE_ACQUISITION.md`](../documentation/HARDWARE_ACQUISITION.md)
- SparkFun teardown with board photos:
  <https://learn.sparkfun.com/tutorials/scio-pocket-molecular-scanner-teardown-/all>
