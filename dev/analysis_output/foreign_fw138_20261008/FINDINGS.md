# Contributed fw-138 SCiO — firmware request, cross-white test, header deltas (2026-10-08)

A second owner contributed an older unit (device specs in `device.json`; personal
details not stored here). It is an older generation than the project's own unit:
**DSP firmware 138, BLE 124, i2s tag `20150812:PRODUCTION` (no `-e/-o` suffix),
gradient blob 1416 B.** One raw scan (sample/dark/gradient, no white reference) was
contributed; it decodes cleanly offline (1800/1800/1416 B, correct headers,
~7.9 bits/byte).

## 1. Firmware request — server still offers nothing

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
the token and endpoint are healthy, so this is "the store has nothing", not an auth or
transport failure. **Bounded negative:** null for these parameters; it does not prove
the firmware is unavailable to every authorized client. No install, reset or device
command.

## 2. Cross-white test — the signature is device-bound per blob

The contributed scan has no white reference, so it cannot be replayed alone. Instead
its sample+dark were paired with the **owner's** white reference and submitted two ways
(`probe_foreign_crosswhite.py`, `../foreign_fw138_crosswhite_20261008/crosswhite_summary.json`):

| job | device_id / tag | result |
|---|---|---|
| control_initial / control_final | owner | 200, valid spectrum |
| cross_owner_identity | owner id + `-e` tag | **400 `Bad_sample_signature`** |
| cross_foreign_identity | fw-138 id + bare tag | **400 `Bad_sample_signature`** |

A scan cannot be assembled from a foreign sample and the owner's white under either
identity: whichever device_id the request carries, the other side's blobs fail the
signature. This **confirms the per-blob signature is bound to the request's device_id**
and that sample and white are not validated as independent, swappable halves. It does
not reveal the signature algorithm or the payload transform.

## 3. File-header deltas vs the owner's fw-147 — a per-device region in boot/dec

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

**Key observation (contributor's, confirmed):** `dsp_boot` (v17) and `dsp_dec` (v12)
have **identical size and version on both units but different byte sums**. Two devices
running the same versioned boot/decrypt code differ by a small amount inside those
images — i.e. a **per-device region embedded in `dsp_boot`/`dsp_dec`**, separate from
the versioned code and from `dsp_op`. This localizes where per-device material
(plausibly a key or per-device calibration) lives, and is a concrete target for the
hardware routes: dumping `dsp_boot`/`dsp_dec` from either unit should expose where the
two differ.

`bins` is identical in size and byte sum across generations (only the version differs),
so that table may be generation-stable.

## 4. Open: a paired fw-138 spectrum needs the contributor's white reference

To add a real older-generation paired sample to the corpus, the contributor's white
reference is required (`sample_white`, `sample_white_dark`, and `sample_white_gradient`).
With it, `probe_foreign_firmware.py` will replay the scan under the fw-138 device_id +
bare tag and store the paired sample. (Awaiting that data.)

Blob SHA-256 of the contributed scan is in `device.json`.
