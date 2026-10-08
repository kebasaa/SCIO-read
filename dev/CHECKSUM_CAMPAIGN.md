# Checksum-informed offline campaign

## Scope and status

**Complete: all 180,266 jobs, no recovered intermediate or decoder.** Header/delta
families produced 381 isolated codec leads and random controls nine. All 402 hits
were raw-deflate parses consuming 4–68 bytes, leaving >=1,688 unexplained trailing
bytes. No owner cross-acquisition codec lead or integrity match. Contributor
confirmation remains limited to one acquisition. See the immutable
`analysis_output/checksum_headers_20261008_run/summary_180266.json` and run report.

The 2026-10-08 campaign tests 2,342 distinct hypothesis keys: 1,156 from each
device's own firmware-header material and 30 separate diagnostic delta keys.
There are 180,266 jobs: extended AES decoding, keyed integrity hypotheses,
direct compression-only checks, and random-key/random-body controls. No exact
owner AES configurations overlap the previous bounded manifest. An earlier
planning directory predates final evaluator/test fixes; use
`analysis_output/checksum_headers_20261008_final_plan/` and the run's immutable
compressed manifest, not the initial `checksum_headers_20261008_plan/`.

All work stays under `dev/`. No network/device access, resetting, installation,
disassembly or correspondence. The historical phone/backups are unavailable;
they are not assigned as a next task. Production code and source captures are
read-only. Frozen cap captures remain untouched.

## Reproduction and interfaces

From the repository root, in the existing Python environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python dev/scripts/checksum_campaign.py --mode synthetic-test
python dev/scripts/checksum_campaign.py --mode plan-only --output dev/analysis_output/NEW_PLAN
python dev/scripts/checksum_campaign.py --mode offline-run --output dev/analysis_output/NEW_RUN
```

Plan-only and offline-run disable Python socket connections. `--max-jobs` limits
new work for interruption tests; repeat the same offline-run command to resume.
Resume requires identical manifests, including input, evaluator, driver and
helper hashes. The private SQLite checkpoint uses WAL and commits every 250
jobs. Public `manifest.json.gz` and `outcomes.json.gz` are lossless; summaries
are immutable by completed-job count. Raw checkpoint databases and any decoded
cross-acquisition leads stay git-ignored under `dev/private/`.

An optional `--apps <local-app-root>` records a static source audit after the
selected mode. It does not communicate with a device. Do not reuse an audit
output directory; its result is exclusively created.

## Enumerated hypotheses

For each device, seeds are boot checksum, dec checksum, their ordered pair,
complete boot header, complete dec header, and ordered BLE/boot/dec/op checksums.
Representations are U32 LE/BE and colon-separated decimal/eight-digit lowercase
hex text. Only the first three seed families are combined with the same device's
device/DSP/Aptina identifiers, in observed raw/reversed raw/lowercase/uppercase
forms, in both concatenation orders without separators.

Derivations: legal 16/32-byte raw seeds; zero-pad/repeat to 16 bytes for shorter
seeds; MD5, SHA256 first 16 bytes, full SHA256. Diagnostic deltas -673 and -26
use signed LE/BE integers and decimal text. Byte-identical keys retain all labels.
The 4,096 limit covers the union across both devices and delta keys, not controls.
Missing identity fields are reported; mixed known identities are rejected.

Only existing extended AES configurations are used. Actual eight-byte headers,
embedded IV removal and declared 16-byte trailers are explicit. ECB/CBC lengths
are checked before the existing decryptor, preventing silent truncation.

Codec checks mirror the earlier bounded families: zlib/raw deflate/gzip/bzip2/xz
at offsets 0/4/8/16; marker-guided JPEG/JPEG2000/PNG/TIFF/GIF/WebP; one generic
decompression layer followed optionally by image decoding. Limits are 1 MiB and
65,536 pixels. Missing Pillow does not prevent generic decompression. Image
exceptions, generic codec outcomes, completion, consumed/trailing bytes and
output hashes are recorded. Image extents remain unverified, never promoted
automatically to structural validation.

Integrity tests enumerate AES-CMAC/HMAC-SHA256, body/word0+body/raw-device-ID+body,
first/last four digest bytes, and little/big endian. Header word1 is excluded
from the message. Ten distinct same-role matches across three acquisition groups
are required, with all selected blobs matching that unchanged construction.
Reused white-reference blobs are deduplicated; foreign single-scan matches cannot
meet this gate. A mismatch does not exclude encryption or establish the field's role.

## Inputs and interpretation limits

Owner identities come from a verified owner scan; current header fields come
from the existing owner profile. Decode screening uses sample/dark from one
historical group, then independently checks the same roles in two other groups.
The integrity track contains 285 deduplicated role/blob records. Current headers
on historical captures have an **unverified firmware association**; failures
cannot exclude derivations using unavailable historical checksums.

The contributor track uses its own supplied headers/identities and three checked
blobs from one acquisition. No owner's identity or white reference is injected.
Missing contributor repeats/white data limits confirmation, not owner progress.

Random controls use 16 deterministic keys per profile, alternating 16/32 bytes,
and the same configurations and confirmation logic. Random bodies preserve the
observed headers and lengths. These finite controls cannot establish extreme-tail
significance or familywise guarantees.

Codec signatures repeated across acquisitions are **unvalidated leads** until
layout and boundaries are supported. No arbitrary interpolation, lookup replay
or fitted per-scan scaling. Reflectance needs 331 finite bands on the correct
axis at `atol=rtol=1e-6`; absolute vectors additionally need supported calibration
or intermediate truth. All campaign summaries default to no validated recovery.

## USB/BLE audit and firmware handoff

The static audit covers 39 named Java command/model/activity files in the
supplied app trees; the report saves relative source anchors and content hashes.
It distinguishes header/list reads from outbound file transfer. Crucially, the
Lab toolkit's `performFileDownload` logs `performReadFileList entered`, but
passes supplied bytes into the write operation. A log search alone can misclassify
that route. No demonstrated body-read operation was found. Therefore zero device
commands are authorized or sent by this driver; no USB/BLE connection is needed.

For a newly supplied artifact:

```text
python dev/scripts/checksum_campaign.py --mode inspect-firmware --artifact <supplied-file> --artifact-format raw --name dsp_boot --output dev/analysis_output/NEW_INSPECTION
```

Use `--artifact-format container` only for an explicitly identified binary
four-byte-prefix container, not Base64 text or an assumed raw flash dump. Add
`--compare <second-file>` for actual byte differences. Original, prefix and body
files remain private; public inspection reports hashes, sizes, entropy, checksum
comparisons, LDR structure, cipher-signature leads and up to 256 difference ranges.
Upgrade/header disagreement never discards an artifact. Raw images have no
invented checksum prefix. Artifacts over 32 MiB are rejected.

No arbitrary constant-window harvesting occurs. Cipher tables alone do not
identify an implemented transform. If genuine executable bodies arrive, the
next work is instruction/control-flow analysis linking acquisition, packing,
identity/calibration inputs and transport/integrity. CC2540 firmware storage
and boot/dec personalization remain hypotheses pending actual bytes.

## Evidence ledger

| Claim | Status / limit |
|---|---|
| Equal sizes/versions and checksum deltas locate a small key region | Not established; checksum algorithm and body bytes are missing. |
| CC2540 stores and boots the DSP firmware | Plausible hardware hypothesis; storage capacity and absent visible flash are not a traced boot path. |
| Header-derived candidates were already covered | New enumerated keys; no exact owner AES overlap with prior manifest. |
| A method logging ReadFileList retrieves firmware | Invalid for the inspected download wrapper; its data flows host-to-device. |
| Checksum prefix reveals byte-sum calculation | Not established; inspected code splits/compares the field, not computes it. |
| Historical owner failures exclude current-header KDFs universally | No; historical header association is unverified. |
| Any successful codec parse is a decoder | No; boundary/layout and numerical validation are additional gates. |

Update the run's report and this handover after each completed stage. Stop when
the manifest is exhausted. Another header family, cipher, key expansion, server
campaign or device opcode requires new evidence and a separate bounded plan.
