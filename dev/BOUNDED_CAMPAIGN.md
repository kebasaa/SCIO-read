# Bounded identity and layered-codec campaign

## Final outcome

**Complete: 422,419 configurations; no confirmed intermediate or offline decoder.**

| Stage | No codec hit | Unvalidated codec parse |
|---|---:|---:|
| Six missing AES keys | 299 | 1 |
| Identity gaps | 155,361 | 488 |
| Layered-codec coverage | 262,859 | 803 |
| Random-key controls | 1,304 | 0 |
| Random-body controls | 1,303 | 1 |

Zero codec signatures repeated consistently for sample alone or dark alone across
the three acquisitions. No gradient requirement was used to veto those same-role
checks. The separate all-role check also yielded zero candidates. The 1,292
identity-key parses are not decoded intermediates; one random-body parse further
illustrates the risk of accepting parser success alone.

Evidence: `analysis_output/bounded_identity_20261004_run/assessment.json`,
`summary_422419.json`, `capabilities.json`, and `manifest.json.gz` with its digest.
The 100 MB raw manifest and configuration-level SQLite results remain local;
the lossless compressed manifest is approximately 2 MB. Original reports are
preserved. A SQLite-reader timeout interrupted stage 3; WAL-backed resume completed
the unchanged manifest, including previously uncommitted jobs.

Verification: 114 production tests passed unchanged; 167 research tests passed
with sockets disabled; all 34 final campaign-specific tests passed (including the
subsequently added resume regression). Input and evaluator hashes match the
manifest; source/production before-after hashes matched on the completed run.
The repository public-safety scan passed; the artifact audit also covers the
compressed manifest. No changed files are outside `dev/`.

Remaining unknowns: a custom/headerless codec, a different key or construction,
unrecovered calibration geometry and absolute domain values. This campaign does
not exclude those hypotheses. Do not repeat the same manifest; firmware or
calibration artifacts and evidence-led new layouts are the useful next inputs.

## Boundaries and reproduction

Only `dev/` is written. Source captures, production code and tests are read-only.
No network, serial, BLE or firmware operations are used. The driver denies Python
network connections. Run with bytecode writes disabled in the existing environment:

```text
python dev/scripts/bounded_identity_campaign.py --mode synthetic-test
python dev/scripts/bounded_identity_campaign.py --mode plan --output dev/analysis_output/<new-plan>
python dev/scripts/resume_bounded_campaign.py --mode offline-run --output dev/analysis_output/<new-run>
```

For concurrent report reads, use `resume_bounded_campaign.py` with the same
arguments. This wrapper changes SQLite connection settings (WAL and a
30-second busy timeout) and normalizes configuration tuples to their JSON list
representation before exact resume comparison. It leaves configuration values,
the evaluator and the saved manifest unchanged. The first
run stopped during stage 3 when a progress reader held a database lock longer
than the default timeout. Committed checkpoints were retained; the resume repeats
only unfinished jobs. No scientific outcome from the interruption is inferred.

An identical offline-run command resumes only if the complete manifest matches.
Local SQLite checkpoints record configuration-level results and exceptions,
committing every 250 jobs; an interruption may repeat the uncommitted batch.
`--max-jobs` supports bounded interruptions. The current output directory ignores
the large database; portable JSON manifests retain hashes and derivation labels.

Screening uses sample/dark from 2020-06-04, then ten additional blobs from
2021-10-20 and 2023-03-29 for exploratory confirmation of any codec lead. These
are not unseen validation data. The six frozen cap captures remain untouched.

## Coverage

The generator preserves full Aptina byte orders, halves and serial prefix as
explicit fields for raw/text/hash and bounded pairwise forms. Aliases no longer
shadow each other; byte-identical keys retain all derivation labels.

| Stage | Configurations |
|---|---:|
| Six missing Aptina keys × extended AES configurations | 300 |
| Remaining identity/configuration gaps | 155,849 |
| New layered-codec coverage for previously tested keys | 263,662 |
| Random-key controls | 1,304 |
| Random-body controls | 1,304 |
| Total | 422,419 |

There are 5,067 deduplicated identity keys. Stage 3 includes existing AES keys:
the old codec stage lacked bzip2/xz and two-role screening. This is not new-key
coverage. Old non-AES reports retain best configurations, not every attempted
outcome; their detailed historical coverage remains partly reconstructed.

The actual run manifest is `analysis_output/bounded_identity_20261004_run/manifest.json`.
The earlier plan-only artifact predates random-body controls and is superseded.

Every tested plaintext reaches codec checks without a smoothness/repeatability
gate: zlib/raw-deflate/gzip/bzip2/xz at offsets 0/4/8/16, and marker-guided images
at every matching offset. Only one decompression layer followed optionally by
image decoding is allowed. Limits: 1 MiB decompressed, 65,536 image pixels.
Stream consumption and trailing bytes are recorded. Image extents are explicitly
unverified: Pillow successfully reading pixels is not a validated container.

## Historical progress checkpoints

Stage 1: 299 misses and one raw-deflate parse consuming 20 bytes, leaving 1,772
nonzero trailing bytes, and failing all ten additional confirmation blobs.
This is an unvalidated accidental parse, not a decoder.

At the first saved checkpoint, 61,000 configurations were complete: 190 codec
leads, no common codec signature across all confirmation records. Remaining
stages and controls were still running at that checkpoint.

Stage 2 has now completed: 155,361 no-codec-hit outcomes and 488 unvalidated
codec parses. The second checkpoint (164,750 total jobs) contained no common
codec signature across all confirmation records. The final assessment also
checks sample and dark separately across acquisitions, so a different gradient
format cannot veto a sample-only candidate.

Verification so far: 114 production tests passed unchanged; the network-blocked
research run passed 157 tests. Three subsequent additional synthetic tests also
passed (26 campaign-specific tests total). All six image plugins and required
compiled image backends are available in this environment; see `capabilities.json`.

## Acceptance and limits

Heuristic leads, structural intermediates, reflectance and absolute domain
vectors are separate milestones. No arbitrary pixel interpolation or per-scan
rescaling is allowed. Reflectance requires 331 finite bands on the correct axis
at `atol=rtol=1e-6` on frozen records after candidate parameters are fixed.
Domain vectors additionally need intermediate truth or supported calibration.

Controls are deterministic and use the same screening/confirmation logic. Their
small sample does not establish extreme-tail or familywise significance.
A codec miss cannot exclude a correct key followed by an untested custom codec.
Encryption, key architecture and mandatory teardown are not established.
Externally supplied firmware/cache artifacts remain a separate acquisition route.
