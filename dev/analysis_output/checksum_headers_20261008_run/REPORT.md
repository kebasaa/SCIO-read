# Checksum-informed SCIO campaign — completed 2026-10-08

## Outcome

**No offline intermediate, reflectance, absolute domain vectors or integrity
construction recovered.** All 180,266 enumerated jobs completed with network
connections blocked. No device commands, firmware installation, reset, server
requests, disassembly or outgoing correspondence.

There were 2,342 unique hypothesis keys: 1,156 per device and 30 separate
diagnostic delta keys. Identities and supplied headers were kept device-specific.
No owner AES key/configuration overlapped the prior exact bounded manifest.
This is new bounded coverage, not proof that every older search is fully recorded.

| Device/family | AES jobs | Isolated codec leads | Integrity jobs | Integrity matches |
|---|---:|---:|---:|---:|
| Owner header-derived | 57,800 | 183 | 27,744 | 0 |
| Owner diagnostic deltas | 1,500 | 2 | 720 | 0 |
| Owner random keys | 800 | 2 | 384 | 0 |
| Owner random bodies | 800 | 2 | 384 | 0 |
| Contributor header-derived | 57,800 | 192 | 27,744 | 0 |
| Contributor diagnostic deltas | 1,500 | 4 | 720 | 0 |
| Contributor random keys | 800 | 3 | 384 | 0 |
| Contributor random bodies | 800 | 2 | 384 | 0 |

Two additional direct compression-only jobs yielded no hit. The 390 lead
configurations produced 402 individual raw-deflate parses. Every parse consumed
only 4–68 bytes and left at least 1,688 unexplained trailing bytes; none had
an absent or all-zero tail. No codec signature confirmed across the owner's
three acquisitions. The contributor has only one acquisition. These outputs
are parser false-positive-like observations, not decoded spectral data.

Random-key controls produced five leads / 1,600 AES configurations; random-body
controls produced four / 1,600. No control confirmed. These finite measured
counts do not support extreme-tail significance or familywise guarantees.

## Inputs, associations and limits

Owner screening/confirmation groups: 2020-06-04, 2021-10-20 and 2023-03-29.
Sample and dark were checked independently. The integrity track used 285
deduplicated role/blob entries; repeated white references did not inflate counts.
Contributor input: its supplied sample/dark/gradient, one 2026-10-07 acquisition.
Frozen cap captures were not loaded or used to tune parameters.

The current owner checksum/header association with historical scans is
**unverified**. A miss cannot exclude derivations using unknown older checksum
fields. Contributor header provenance is reported by its owner, not independently
verified from a firmware image. All hypotheses and provenance are explicit in
the manifest. Small checksum deltas do not locate changed bytes or prove keys;
CC2540 firmware storage remains a hardware hypothesis.

## USB/BLE audit and firmware readiness

The static audit covered 39 named Java command/model/activity files in the
supplied app trees; relative source anchors and hashes are in
`../checksum_headers_20261008_final_plan/usb_ble_audit.json`.

- `0x87` reads a four-word file header; checksum field is at byte 12.
- `0x94` reads file IDs/versions, not bodies.
- `0x81` sends provided firmware bytes host-to-device. The SDK wrapper logs
  `performReadFileList entered` despite invoking `performFileDownload`; that
  misleading text is not a read operation.
- The upgrade model separates the four-byte prefix and body. Host-side comparison
  of the supplied field does not establish a byte-sum checksum algorithm.
- Reading-to-request paths serialize returned data as Base64; no KDF or decoder
  is established by the inspected metadata path.

No demonstrably read-only firmware-body operation was identified, so no USB/BLE
commands were sent. This bounds audited software paths, not undocumented device
functions. No connection is needed for the remaining local work.

The supplied-artifact inspector is ready: immutable private originals, explicit
raw/container interpretation, SHA-256/length/entropy/sum metadata, LDR parsing,
cipher-signature leads and actual-byte comparison. Header mismatch does not
discard a possible upgrade. No arbitrary constant-window key harvesting occurs.
No real firmware artifact was available to inspect or disassemble.

## Reproduction and evidence

See [CHECKSUM_CAMPAIGN.md](../../CHECKSUM_CAMPAIGN.md) for exact candidate
families, command modes, codec limits, firmware inspection and stopping rules.
The initial plan predates evaluator fixes; the final plan and run manifest are
authoritative. Older raw reports remain unchanged.

- [summary_180266.json](summary_180266.json): complete configuration counts.
- `manifest.json.gz`: immutable complete inputs, code revision/hashes,
  device profiles, key derivation labels, capabilities and configuration list.
  SHA-256 `5d4d5d8cb4d8c2073517853e9f4571fe45ad0bcff894b70ef9ebc8edec0e40dd`.
- `outcomes.json.gz`: lossless configuration-level outcomes, without key bytes
  or decoded vendor bodies. SHA-256
  `723bb242eb4bf279274aa5218e577e5d004066f7aa2f30b1d86c03d8549779b0`.
- [verification_180266.json](verification_180266.json): source/production
  unchanged, network blocked. Input, evaluator, driver and recorded helper hashes
  were independently checked again after completion.
- [EVIDENCE_LEDGER.md](EVIDENCE_LEDGER.md): findings, corrections and stage history.

SQLite checkpoints remain under git-ignored `dev/private/checksum_campaign/`.
No cross-acquisition lead bodies were created because no candidate qualified.
All changes from this session are under `dev/`; pre-existing unrelated user
changes, including the root ignore file, are preserved.

## Testing and decision

263 research tests passed with sockets disabled; 114 production tests passed
unchanged. There are 58 new campaign tests, including scalar AES/CMAC encryption
fixtures independently checked against FIPS-197/RFC4493 vectors and an independent
HMAC construction checked against RFC4231. Tests cover all seed families, framing,
packed bytes, compression/images, wrong keys/devices, weak repeatability, role
separation, stream limits/tails, optional codec absence, immutable inspection,
mixed identities, deduplication and interrupted/resumed checkpoints. Three existing
Blowfish deprecation warnings remain. Bytecode writes were disabled and test
caches/temp files kept under `dev/`.

Completed-campaign resume verification succeeded with zero new jobs and unchanged
archives. `git diff --check` and the working-tree public-safety scan passed. The
two compressed shareable artifacts were also decompressed and scanned: zero
credential/user-home/GPS findings. Private checkpoints are confirmed git-ignored.

Stop this manifest; do not expand cipher/key/endpoint families without new
evidence. The useful new inputs are an independently supplied firmware/dump,
verified historical headers, or additional matching contributor acquisitions and
white-reference data. Actual firmware bytes would permit differential code/data
analysis; checksum fields alone do not. Reflectance still requires the correct
331-band axis and numerical agreement without fitted rescaling; absolute vectors
require intermediate truth or independently supported calibration.
