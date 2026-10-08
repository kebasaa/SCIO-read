# Contributed fw-138 SCiO — firmware request, cross-white test, header deltas (2026-10-08)

A second owner contributed an older unit (device specs in `device.json`; personal
details not stored here). It is an older generation than the project's own unit:
**DSP firmware 138, BLE 124, i2s tag `20150812:PRODUCTION` (no `-e/-o` suffix),
gradient blob 1416 B.** One raw scan (sample/dark/gradient, no white reference) was
contributed; it decodes cleanly offline (1800/1800/1416 B, correct headers,
~7.9 bits/byte).

## 1. Firmware request — no offer for the tested parameters

The idea: an out-of-date device might be offered the upgrade images the project has
never obtained. Four firmware-upgrade GETs, 20 s apart (`probe_foreign_firmware.py`,
`campaign_summary.json`):

| job | device | versions | result |
|---|---|---|---|
| foreign_all_zero | fw-138 unit, bare tag | all `0x00` | 200, `new_version: null` |
| foreign_real_fw138 | fw-138 unit, bare tag | real fw-138 map | 200, `new_version: null` |
| foreign_tables_outdated | fw-138 unit, bare tag | code real, tables `0x00` | 200, `new_version: null` |
| own_device_control | owner's fw-147 unit, `-e` tag | owner current | 200, `new_version: null` |

All four returned the **byte-identical** 51-byte `{"new_version":null}` (SHA-256
`f7bb8314…`) — the same empty response the owner's own device gets. The control proves
the endpoint accepted these authenticated requests, not that its firmware store
is empty. **Bounded negative:** null for these parameters; it does not prove
the firmware is unavailable to every authorized client. No install, reset or device
command.

## 2. Cross-white test — tested mixed-device combinations are rejected

The contributed scan has no white reference, so it cannot be replayed alone. Instead
its sample+dark were paired with the **owner's** white reference and submitted two ways
(`probe_foreign_crosswhite.py`, `../foreign_fw138_crosswhite_20261008/crosswhite_summary.json`):

| job | device_id / tag | result |
|---|---|---|
| control_initial / control_final | owner | 200, valid spectrum |
| cross_owner_identity | owner id + `-e` tag | **400 `Bad_sample_signature`** |
| cross_foreign_identity | fw-138 id + bare tag | **400 `Bad_sample_signature`** |

These foreign-sample/owner-white combinations were rejected under both tested
identities. This does not identify the failing blob, establish per-blob verification
or a cryptographic signature, or isolate binding to device_id rather than generation,
calibration or another field. Verification order and the payload transform remain unknown.

## 3. File-header deltas vs the owner's fw-147 — comparison leads

Byte-sum checksums on both units (the analyzer's assumption):

| id | name | fw-138 (contributed) | fw-147 (owner) | note |
|---|---|---|---|---|
| 87 | ble_runtime | 119278 / 124 / 12946070 | 119233 / 125 / 12925168 | different size+version |
| 90 | dsp_boot | 7284 / 17 / **687783** | 7284 / 17 / **688456** | **same size+version, Δsum −673** |
| 91 | dsp_dec | 14600 / 12 / **1548912** | 14600 / 12 / **1548938** | **same size+version, Δsum −26** |
| 92 | dsp_op | 32212 / 138 / 4101455 | 32628 / 147 / 4151168 | different size+version |
| 99 | (file 99) | 32 / 0 / 0 | — | present on fw-138 |
| 100 | deadPixelsIndices | 2366 / 1 / 127520 | 1714 / 3 / 97267 | different size+version |
| 101 | centers | 96 / 1 / 4880 | 96 / 3 / 6080 | same size, diff version |
| 102 | bins | 140 / 1 / 13587 | 140 / 3 / 13587 | same size+**sum**, diff version |
| 103 | nPixelsPerBin | 974 / 1 / 30963 | 1166 / 3 / 36371 | different size+version |

`dsp_boot` (v17) and `dsp_dec` (v12) have equal reported size/version but different
checksum fields. No firmware bodies or proven checksum algorithm are available.
Even an established byte sum would not constrain how many bytes differ: extensive
changes can have a small net sum. Personalization and embedded keys remain hypotheses,
not localized findings. Compare actual bodies if they become available.

`bins` has equal reported size/checksum across generations. This does not establish
identical bytes or a generation-stable table.

### Interpretation correction and request-format follow-up, 2026-10-08

Raw reports above are preserved. Contributor jobs in this earlier campaign included
four calibration-table IDs as well as four code IDs. The exact four-code-key follow-up
with fresh tokens and bracketing controls also returned four null offers:
[`../contributor_fw138_exact4_20261008_network/REPORT.md`](../contributor_fw138_exact4_20261008_network/REPORT.md).
The interpretation corrections above replace the unsupported store/signature/key-region
claims, without altering historical raw results.

## 4. White reference received — fw-138 samples ingested and replayed (2026-10-08)

The contributor then sent a **white reference plus three samples** (pine wood, tomato,
skin), all base64 (`scans.json`). These were written as canonical `scio-scan/2` records
(`scripts/ingest_foreign_fw138.py`) and replayed to the server under his device_id +
bare tag + his white (`session.process_pending`, `replay_summary.json`):

| sample | server result |
|---|---|
| skin (hand) | **HTTP 200, 331-band spectrum** (reflectance 0.31–1.26) |
| pine wood | 422 `InvalidScan` |
| tomato | 422 `InvalidScan` |

The blobs are valid under their own device_id (no `Bad_sample_signature`): all three
passed the integrity check. Two then failed the physics/quality gate (`422 InvalidScan`,
"try again"), one decoded. (As in §2, this does not establish the check's mechanism.) This is the project's **first self-collected fw-138 paired sample**
(skin). The three raw records remain in the corpus; pine/tomato simply have no spectrum
(like dark frames the server rejects).

**Included across the research strand.** The foreign device is now part of the canonical
corpus and the multi-device readers: `leakage.corpus_groups()` lists both devices and runs
per device (fw-138 n=1 → underpowered, reported honestly); `validation.load_pairs()`
includes the skin pair; `transform_class` reports the `20150812` generation (gradient 1408 B)
alongside `-e` (1648 B), with length fixed within each generation. Live/physical operations
stay owner-only.

## 5. Object temperature is live on the fw-138 unit (2026-10-08)

`READ_TEMPERATURE` word 2 (`obj_t = w2/100`) reads 0 on the owner's fw-147 unit but is a
live surface temperature on this fw-138 unit: skin 32.63 °C vs wood/tomato ~20 °C, white
22.71 °C. The four raw triples and the data table are in
[`../../DEVICE_FUNCTION_REFERENCE.md`](../../DEVICE_FUNCTION_REFERENCE.md); a convenience
`ScioDevice.read_object_temperature()` was added. Whether the owner's fw-147 unit also
reports a live value when pointed at a warm target is an open read-only check.

Blob SHA-256 of all contributed scans is in `scans.json`.
