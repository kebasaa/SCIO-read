# Stale reply-buffer observations: owner fw-147, USB

Reviewed offline on 2026-10-29. This replaces the interpretation of the 2026-10-28
run, not its raw evidence. `rounds.json`, `analysis.json`, and `analysis_v2.json`
are preserved. The reproducible corrected result is
[analysis_v3.json](../stale_buffer_review_20261029/analysis_v3.json).

## Evidence and coverage

The saved run contains 20 scans and 29 replies: battery 20; device status,
device ID and temperature two each; BLE ID, BLE status and unsupported file-header
one each. The post-scan BLE-config request timed out; its reply is missing.
Two pre-scan baseline replies exist for each of the eight probes.

Battery byte 15 equals the preceding gradient byte 15 in 20/20 recorded replies,
with no matches to dark or sample at that offset. This holds for direct battery
reads and the recorded intervening-command sequences. It is consistent with
retained buffer data, but does not identify buffer ownership or the mechanism.
This local run establishes the single-byte observation only for the tested fw-147 unit.

## Comparison with the outside research summary

Source: [SCIO_GITHUB_RESEARCH_SUMMARY.md](../../../email/SCIO_GITHUB_RESEARCH_SUMMARY.md),
prepared 2026-10-28 from work on 2026-10-21 through 2026-10-24. This source is
git-ignored and may not be available in a public checkout; its relevant claims
are recorded here. The full summary was checked on 2026-10-29.

| Evidence | Outside report | Saved local run |
| --- | --- | --- |
| Unit | DSP-operation file version 151; tag `20150812-g:PRODUCTION` | Owner fw-147 |
| Battery/gradient match | Offsets 13..15 in 44/44 observations | Offset 15 in 20/20 replies |
| Evidence available here | Written summary; underlying scripts/captures not supplied by the summary itself | `rounds.json`, independently replayed offline |
| Supported interpretation | Consistent with stale reply-buffer contents | Consistent with retained buffer data; ownership/mechanism unresolved |

Do not pool these counts or infer that the units share the same reply layout.
Matching file versions and sizes do not establish that the outside unit is the
fw-151 capture contributor's unit. The outside report explicitly describes the
repeated bytes as opaque, not demonstrated plaintext or key material, and says no
controllable memory-read primitive resulted. It does not claim encryption is proven
or that every possible disclosure route has been excluded.

The outside iPhone analysis omitted gradient fields, but the preceding calibration
included a white-gradient block. Its successful response contained model results
and `spectrum: null`. Consequently, that observation cannot justify dismissing
buffer data on the premise that the server never uses gradients, nor supply a
decoded spectrum for validating that unit's opaque bytes.

## Interpretation limits

The battery parser documents bytes 0..7. Bytes 8..14 are not established fields:
byte 8 varies slowly, while several others remain stable in this run. Device-ID
bytes 8..15 also lie outside the documented parser. BLE-status bytes 4..5 change
from the baseline; a status field is plausible, but its meaning remains unresolved.

The corrected classifier counts 40 unmatched bytes outside documented coverage:
19 at battery offset 8, 19 at battery offset 15, and two at BLE-status offsets 4..5.
The independent 20/20 byte-15 observation is reported separately: the generic
classifier requires a same-source adjacent match and cannot establish single-byte
residue. One byte-15 occurrence instead matches a three-byte run elsewhere in
transmitted blobs. These heuristics are observations, not proof of provenance.

No plaintext, key material, or controllable memory-read primitive was demonstrated.
The gradient bytes are opaque; encryption is not established. These measurements
neither prove that all replies contain only previously transmitted data nor exclude
other disclosures. The lead is bounded by this capture, not closed universally.

The earlier reports are historical outputs: `analysis_v2.json` counted 21
unexplained bytes after treating battery bytes 8..14 as fields. The corrected
analysis keeps those undocumented bytes in scope, giving 40 unmatched occurrences.
This difference is a coverage correction on the same capture, not a new leak or
new device measurement. A repeated byte equality and an unmatched heuristic
classification can coexist; neither alone establishes the byte's origin.

## Reproduce without hardware or network

```text
python dev/scripts/probe_stale_buffer.py --replay dev/analysis_output/stale_buffer_20261028/rounds.json --output dev/analysis_output/<new-review-directory>
```

The report hashes the source, checks scan/reply associations, reports missing
coverage, and compares each reply only with blobs transmitted up to that point.

## Review verification, 2026-10-29

- Initial uncommitted inventory: handover edit; two scripts and their two test
  files; original contributor parse report; triage; this report plus three saved
  stale-buffer JSON files; and three temporary references. All were reviewed.
- The original raw run and historical analysis JSON files remain unchanged. The
  corrected analysis reproduces exactly from the saved run. All 18 contributor
  blob hashes match both the original and corrected parse reports; only multiscan
  identifiers changed to include their source capture.
- Research suite: 335 passed with Python socket connections disabled (three
  existing Blowfish deprecation warnings). After final importer cleanup and five
  additional cases, the focused suite passed all 49 tests.
- Production suite: 125 passed, also 125 passed with research imports blocked and
  research directories removed from the import path. External sockets were blocked;
  loopback was allowed for Windows asyncio. The initial blanket socket block
  prevented asyncio setup and was corrected in the test harness, not production.
- Working-tree public-safety check (tracked and untracked files), `git diff --check`,
  and explicit untracked text whitespace checks passed.
- `temp/foods-11-01465-1.pdf` is a 53-page 2022 review of miniaturized NIR food
  spectroscopy. `temp/Quick-Reference-Guide-V1.6.pdf` is a four-page SCiO corn user
  guide. `temp/sdk.txt` contains a developer-site URL. These are background
  references, not evidence for byte provenance or contributor identity; preserved.
- No device operations, cloud submissions, canonical capture writes, commits, or
  publication occurred during this review. New result files are under `dev/`.

Unresolved: contributor device identity, processing tag and compatible white
reference are still needed for real replay. This laptop's device cannot establish
those facts for the contributor's unit. Byte meanings and buffer architecture
remain open questions; no new device experiment is required to support the
bounded conclusions above.

## Follow-up verification of the outside summary

The subsequent [independent audit](../github_research_20261028/TRIAGE.md) verified
the summary's corpus counts and complete-stream codec negatives from the cited Git
commit, and inspected the public vendor manual/frontend. It did not obtain the
outside battery traces, so 44/44 remains an attributed report. The local 20/20
result and 40 unmatched occurrences remain unchanged.

The most concrete new acquisition targets are a matched i2s Matlab export and
the offline-service/CSI package, not an inferred key in battery residue. Public
frontend routes establish that those artifact types are represented; they do not
provide their contents. No new live scan is needed for this conclusion.
