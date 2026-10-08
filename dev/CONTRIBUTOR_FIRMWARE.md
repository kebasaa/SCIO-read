# Contributor firmware acquisition, 2026-10-08

This implementation isolates firmware acquisition from decoding and installation.
All outputs stay under `dev/`; the contributed attachment in `email/` is read-only.
No device command, reset, installation, endpoint enumeration or external message
is part of this workflow. Vendor binaries and exact responses remain git-ignored.

## Reproduction

Use the existing Python environment with production dependencies installed:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python dev/scripts/contributor_firmware.py --mode plan-only --output dev/analysis_output/NEW_PLAN
python dev/scripts/contributor_firmware.py --mode live-download --output dev/analysis_output/NEW_CAMPAIGN
python dev/scripts/contributor_firmware.py --mode offline-inspection --campaign dev/analysis_output/NEW_CAMPAIGN --output dev/analysis_output/NEW_INSPECTION
```

Each output directory must be new. Live mode reads the existing cached account;
it does not prompt for, print or persist credentials. A new token is obtained
after the completion cooldown and immediately before each firmware GET. Live
mode is not an invitation to repeat a completed campaign without new evidence.

The immutable `plan.json` records identities, actual headers, attachment/profile
hashes, evaluator hash and exact requests. `summary.json` and
`artifact_manifest.json` report outcomes without authentication headers.
`verification.json` checks source-data and production hashes before/after.

## Scope and request distinction

The earlier `foreign_fw138_20261008` campaign sent eight version keys in its
contributor requests: four code IDs plus four calibration-table IDs. Preserve
those responses; they do not cover the exact four-key app form. This follow-up
uses only `0x57`, `0x5A`, `0x5B`, `0x5C`, in that order, with hexadecimal values.
Device ID, firmware-endpoint BLE ID and runtime file IDs remain distinct.

The sequence is owner actual control; contributor actual;
contributor four code versions zero; owner actual final control. The contributor
tag is exactly `20150812:PRODUCTION`, without a suffix. Client is
`Android 1.3.8.554`; requests use the established firmware-upgrade endpoint.
There are at most four firmware GETs, at least 20 seconds from completion to
preparation of the next request, and fresh authentication for each. Stop on
the first offer, any non-200 status, redirect, authentication/transport error,
oversized response or malformed schema/container. Null and empty maps differ.

## Preservation and interpretation

Raw response bytes are saved before interpretation, capped at 32 MiB with any
truncation explicitly labelled. Canonical Base64 containers must contain a
four-byte prefix plus nonempty body. Each known filename is saved exclusively as
container, prefix and body. Unknown names never become paths; their entries are
quarantined privately and halt the campaign. Valid parts of malformed mixed
offers are still preserved. Bodies differing from installed headers are retained:
an upgrade need not match the installed size/checksum.

Metadata records SHA-256, lengths, entropy, unsigned-byte sums, prefix and both
devices' header comparisons. Blackfin LDR parsing and wrapper/table tests are
structural leads only; they do not verify code identity or an integrity algorithm.
The `ble` name is compared to observed runtime file 87; enum file 89 is absent.
If files are obtained, a checksummed private review ZIP is created. Nothing is
sent to the contributor automatically.

Checksum-field differences at equal sizes/versions do not locate differing
bytes, establish a small per-device region or establish AES/a key. Equal sums
do not establish identical tables. Mixed-device `Bad_sample_signature` responses
establish rejection of the tested combinations, not per-blob verification order
or a cryptographic signature bound specifically to a device ID.

## Campaign results

The initial sandboxed launch failed authentication with `ProxyError` before any
firmware GET. Its preserved record is
`analysis_output/contributor_fw138_exact4_20261008/`. The separately permitted
network launch is `analysis_output/contributor_fw138_exact4_20261008_network/`.
Its result and the offline reinspection will be recorded in that campaign's
`REPORT.md` and `EVIDENCE_LEDGER.md` after completion.

Successful controls plus two null contributor responses close only this exact
account/device/tag/client/version campaign. They do not prove a globally empty
firmware store or mandatory teardown. An independently supplied cache/dump or
another authorized account is new evidence; broad version sweeps are not.
