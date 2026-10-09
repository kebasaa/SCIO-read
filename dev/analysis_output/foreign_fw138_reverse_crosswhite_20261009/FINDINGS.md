# Reverse cross-white — owner sample + fw-138 white (2026-10-09)

The mirror of `foreign_fw138_crosswhite_20261008` (which did owner white + fw-138 sample).
Here the owner's valid scan is kept (owner sample/dark + owner gradients) and the **white
reference's two non-gradient blobs** (`sample_white`, `sample_white_dark`) are replaced with the
**contributor fw-138** white reference (from `foreign_fw138_retake_20261008/scans.json`). The owner
`sample_white_gradient` is kept, mirroring the forward test's keeping of the owner `sample_gradient`.
Submitted live to `api.consumerphysics.com/v2/consumer/spectro-scan` under two identities.
Script: `dev/scripts/probe_foreign_reverse_crosswhite.py`. 4 requests, 20 s apart, clean run (no halt).

| job | identity | result | side flagged |
|---|---|---|---|
| control_initial | owner | **200**, valid 331-band spectrum | — |
| cross_owner_identity | owner id + `-e` tag | **400 `Bad_sample_signature`** | `white` |
| cross_foreign_identity | fw-138 id + bare tag | **400 `Bad_sample_signature`** | `sample` |
| control_final | owner | **200**, spectrum identical to control (no drift) | — |

## Result

A white reference from device A (fw-138) does **not** work with sample data from device B (owner
fw-147). The server rejects the mixed request with `400 Bad_sample_signature` before producing any
spectrum, under both identities. Combined with the forward test (2026-10-08), **both cross-device
directions are now tested and both are rejected**; only same-device scans decode.

Note the flagged side matches the mismatched side: under the **owner** identity the server flags the
`white` side (the foreign white), and under the **fw-138** identity it flags the `sample` side (the
owner sample) — i.e. it reports the side whose blobs are bound to a device other than the request's
`device_id`.

## Limits

Consistent with (not proof of) a per-blob, device_id-bound signature. It does not reveal the
signature algorithm or payload transform, and it does not isolate binding specifically to `device_id`
versus generation/calibration/another field, since the two units differ in several fields at once
(`RECOVERY_STATUS.md:1200`). No offline decode is obtained or claimed. Live request to the owner's own
SCiO cloud account using the owner's own scan plus the project's contributed fw-138 white; no device
operation, no activation.
