# Contributor firmware-138: exact four-key campaign

## Outcome

No firmware was offered. All four authorized firmware GETs returned HTTP 200,
51 bytes, and `new_version: null`. No empty-map offer occurred. The responses
were byte-identical to each other and to the earlier eight-key campaign:

`f7bb8314e735cf6b05f60993ae05cd2e6150ea12f65c0e6d9d0cdd3209a08a0d`

| Request | Start UTC, 2026-10-08 | Identity | Code versions | Result |
|---|---|---|---|---|
| Initial control | 09:05:22.722 | Owner | 7D / 11 / 0C / 93 | 200, null |
| Actual contributor | 09:05:45.320 | Contributor | 7C / 11 / 0C / 8A | 200, null |
| Zero contributor | 09:06:08.679 | Contributor | 00 / 00 / 00 / 00 | 200, null |
| Final control | 09:06:31.345 | Owner | 7D / 11 / 0C / 93 | 200, null |

Versions above are hexadecimal values for keys `0x57 / 0x5A / 0x5B / 0x5C`.
No calibration-table keys were sent. Contributor BLE ID was `EBA03B00004C99B4`,
with exact tag `20150812:PRODUCTION`; owner BLE ID was `01665900004C99B4`,
tag `20150812-e:PRODUCTION`. All used `Android 1.3.8.554`.

Measured completion-to-next-preparation gaps were 20.000, 20.000 and 20.016
seconds; authentication followed each gap immediately before the corresponding
GET. Four fresh authentication calls, four firmware GETs, no redirects followed,
no additional firmware requests. The initial sandboxed launch failed authentication
with `ProxyError`, sending zero firmware GETs; its separate evidence directory is
`../contributor_fw138_exact4_20261008/`. It was not a server-negative result.

## Evidence and reproducibility

- [plan.json](plan.json): exact parameters, distinct identities/header tables,
  attachment/profile hashes and evaluator hash.
- [summary.json](summary.json): status, timestamps, spacing, raw response hashes
  and private relative paths. Authentication headers are never saved.
- [artifact_manifest.json](artifact_manifest.json): four response hashes; no
  firmware artifacts. No review ZIP is created without firmware.
- [verification.json](verification.json): source/production before/after hashes
  unchanged. The same snapshot matched again after testing.
- Offline reinspection in
  `../contributor_fw138_exact4_20261008_inspection/inspection.json` checks archived
  response hashes before parsing, recovers four null states, and makes zero requests.
- Plan-only execution in `../contributor_fw138_exact4_20261008_plan/` makes zero
  requests. The command reference is [CONTRIBUTOR_FIRMWARE.md](../../CONTRIBUTOR_FIRMWARE.md).

Base Git revision: `cb95f1298ed0d8c4751081d0fb5a3e5c4ca4ba17` (new implementation
uncommitted at execution). Evaluator SHA-256:
`04e456360113e2e93538f5c4cc0a6c4dbe43fb84d94cff0a73651dcf501309fb`.
CLI SHA-256:
`bfdda3312a28cd322967c7c726da23d393de934c106336ff9b629a3fd55df4b1`.
Read-only attachment SHA-256:
`8b5d8efdb32ec2cd6e4ae7d7dd28871703b4b0bb76e13c03bb7edcb338776404`.
Attachment and evaluator hashes were independently rechecked after execution.

Exact responses are retained under git-ignored `dev/private/contributor_firmware/`.
Shareable reports contain no credentials, personal absolute paths or correspondence
content. The pre-existing user change to the root `.gitignore` is preserved;
this implementation changed only files under `dev/`.

## Tests

Research suite: **205 passed** with Python socket connections blocked, including
31 new acquisition tests. Three existing Blowfish deprecation warnings remain.
Production suite: **114 passed**, unchanged. Bytecode writes disabled; pytest
caches and temporary files restricted to `dev/`. Mocked tests exercise fresh
auth, exact identities/hex versions/tag, all stop conditions, spacing, immutable
saves, strict Base64, size limits, unknown-name quarantine, partial transport
preservation, mixed metadata, upgrade/header disagreement and offline hash checks.
The final public-safety scan passed: no credentials, user-home paths or GPS fixes
detected. `git diff --check` passed. Synthetic test token text was shortened to
avoid credential-shaped literals; all 31 acquisition tests passed again with
sockets blocked after that change.

## Decision and remaining unknowns

Close this campaign without another version ladder or broad endpoint sweep.
Successful controls show the requests reached an accepting endpoint, not that
the account can access all firmware or that the firmware store is empty.
Neither firmware bodies nor decoding code/key material were recovered.

The contributor's checksum differences do not establish a byte-sum algorithm,
a small changed region or a per-device key. Mixed-device scan rejection does
not establish a per-blob cryptographic signature or verification order.
AES, compression (including image compression), integrity and calibration remain
separate hypotheses. No offline intermediate, 331-point reflectance or absolute
sample/white vectors are validated by this campaign.

New evidence would be another explicitly authorized account or an independently
supplied cache/dump. Contributor white-reference blobs would support a matching
older-generation paired spectrum, but would not by themselves recover firmware.
Any external acquisition, outgoing correspondence or hardware session is separate.
