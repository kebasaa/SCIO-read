# Recovery campaign results

No offline decoder, image intermediate, or absolute sample/white vectors were
validated. This campaign repairs earlier exclusion claims and provides new
constraints. Inputs outside `dev` were not changed.

## Strongest new observation: gradients are dispensable in the tested requests

The live campaign used exactly **60 analysis requests**, serially, with fresh
controls and a minimum 20-second gap. Raw experimental payloads and responses are
in `oracle_network` (49 requests) and `oracle_gradient_followup` (11).

| Change | Observed outcome |
|---|---|
| Status bit in each of six roles | Accepted, spectrum exactly unchanged |
| Second word / beginning / middle / end of either gradient | Accepted, spectrum exactly unchanged |
| Either gradient omitted, both omitted, or both zero-filled | Accepted, spectrum exactly unchanged on the primary baseline |
| Gradient body mutations and both omitted on a second scan | Accepted, spectrum exactly unchanged |
| Second word or sampled body regions of sample/dark/white/white-dark | `400 Bad_sample_signature` |
| Four selected sample block-boundary mutations | `400 Bad_sample_signature` |
| Sample byte swap preserving byte sum and XOR | `400 Bad_sample_signature` |
| Intact same-device sample, white, or white-dark substitution | Accepted; all 331 bands changed |
| Intact same-device dark substitution | `422 InvalidScan`, `high_ambient` |

All controls passed. Error messages did not distinguish the four modified
non-gradient roles. The existing classifier returns **undetermined**.

Inference: this endpoint does not require supplied gradient blobs for these two
scans/generation. It does not prove gradients are meaningless on the device or
unused for every generation/endpoint. The protected/validated portion of the four
other blobs deserves attention. The second word could participate in framing,
checksum validation, compression state, or another transformation; it is not
proven to be an IV, signature, nonce, key, or authentication tag.

## Local searches

- Canonical corpus: 97 scans; 92 processed pairs, including historical references.
  The final manifest deduplicates 325 blobs including foreign app samples and
  preserves provenance. Twenty-four pairs (26.1%) are frozen by acquisition and
  shared-white-reference groups. This is retrospective, not genuinely unseen.
- Corrected primary-device search: 3,624 unique keys × 50 configurations =
  **181,200** configurations, followed by checks on 96 additional dark blobs.
  No independently confirmed entropy lead or consistent decompression result.
- Three foreign device/generation groups: **39,850** configurations, separately
  reported; no confirmed lead. Metadata is not pooled across devices.
- Primary search rerun with image decoders: no valid image or repeatable codec
  result. A synthetic wrapped JPEG encrypted with AES-CBC is recovered through
  the actual driver, including changing headers. This tests the harness only.
- Unkeyed integrity tests: 285 distinct paired-corpus blobs; no exact match for
  enumerated CRC32, Adler32, sums or truncated hashes in the tested fields.
- Keyed integrity tests: **173,952** HMAC/CMAC key/field/coverage hypotheses; no
  first-record match. Other integrity mechanisms and compression checks remain open.
- Compression-only: **429,000** codec/alignment configurations on 325 blobs,
  explicitly without encryption. Of 1,121 partial/completed parses, 42 ended as
  streams, all raw deflate, with at most 436 output bytes. The same configuration
  never completed on more than three blobs. Random controls also yielded parses
  (100 total; one completed across 32 random bodies). These are not spectra or
  validated intermediate layouts. No image was recovered.

The searches are bounded negatives, not exclusions of AES, global keys,
compression, JPEG, proprietary packing or layered transforms. In particular,
headerless JPEG/DCT/wavelet, predictive, Rice/Golomb, arithmetic/Huffman and
table-driven compression remain possible **without any encryption**.

## Application/firmware coverage

`apps.json` hashes nine outer archives, nested APK members and 31,056 source files.
It records Dex/native string coverage and vendor-source references. Flutter
`libapp.so` is ARM64 in 1.5.6 and ARMv7 in 1.5.19. `assets.json` inventories 173
non-visual/font asset candidates, including 36 mock-sample occurrences mapping
to six already-known unique blobs. No executable SCIO firmware was validated.

This is **not a completed control-flow audit of all versions**. Remaining work
includes Dex-to-source version correspondence, Flutter AOT scan/update paths,
encoded constant arrays/custom containers, and calibration/codec table recovery.
Generic Android signing, notification and analytics credentials were not promoted
to SCIO key candidates or exported.

## Next evidence-led work

1. Prioritize the four required blobs, with compression-only and layered routes
   kept separate. Audit the second word against whole-blob validity and recovered
   app/firmware structures. No further broad mutation sweep is justified now.
2. Trace relevant native/Dex paths and recover dimensions/tables before attempting
   headerless image or proprietary coefficient decoding. Do not assume 896 pixels
   or interpolate opaque bytes into 331 values.
3. Obtain existing phone firmware/calibration caches or backups if available;
   follow `dev/RECOVERY_STATUS.md` for provenance and structural verification.
   Hardware acquisition of BF512/CC2540 is a separate session.
4. Only then implement a supported decoder behind `DecodeInput`/`DecodeResult`.
   Require full 331-band numerical equivalence, input-sensitivity checks,
   unsupported-metadata rejection and offline verification. Reflectance alone
   cannot fix the absolute sample/white scale.

Reports are immutable; corrected versions have separate filenames. Use
`corpus_final.json` for the completed corpus manifest and the final verification
report for input hashes and test results. Earlier `corpus.json`, `corpus_v2.json`
and progress summaries are retained as superseded intermediate audit records.
