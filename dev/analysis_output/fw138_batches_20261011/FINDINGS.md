# fw-138 fixed-target batches — ingest + further steps (2026-10-11)

Contributor (Vitaly) sent four batch files (`email/scio_fw138_batch*.txt`): 4 × 25 scans, two
targets (closed cap = bright, wood = dark), each in two independent sessions. Parser/ingest:
`dev/scripts/ingest_fw138_batches.py`.

## 1. Ingest — all 100 decoded, added to canonical
Each scan (dark/sample/gradient) was built into a `scio-scan/2` record reusing the existing fw-138
white (`20261008_1537_calibration.json`) and replayed on the server (20 s spacing). **All 100
returned HTTP 200 + 331 finite bands** — including every dark wood scan (unlike the earlier tomato).
Promoted into `01_rawdata/scans/` (100 records) + `02_processed_data/` (100 spectra). The fw-138
corpus group is now **103 records** (was 4). Append-only honored: only successful decodes were
written to `01_rawdata/`; nothing deleted. (The run summary's "4 failed" are the 4 pre-ingested
test-run scans, skipped as already present — zero real failures.)

## 2. Cap scans stored as raw white references
All 50 cap scans were also stored as raw `scio-wr/2` white-reference records for the fw-138 device
(dark/sample/gradient → white slots) in `01_rawdata/scan_json_calibration/` (4 → 54 calibration
records). Manifest: `fw138_cap_whiterefs_20261011/cap_white_refs.json`.

## 3. Independently verified Vitaly's raw claims (`probe_fw138_batch_leakage.py`) — all confirmed
- **Nonce uniqueness:** 300/300 header `word1` values unique.
- **No keystream reuse:** XOR of same-role bodies at full entropy (bit-balance ≈0.50); no identical bodies.
- **No positional leak:** 0 constant byte positions across the 25 same-target scans.
- **Gradient false alarm:** the single-session cap-vs-wood mean-difference signal (gradient max-z 5.72)
  does **not** generalize — cross-session nearest-centroid accuracy gradient 0.46 / sample 0.46 /
  dark 0.60 (≈chance), session control (cap s1 vs s2) clean. Session-confounded artifact, as he said.

## 4. Supervised byte-vs-spectrum leakage on the enlarged corpus (`probe_leakage.py`)
48 tests (role × view × target) on the 103-record fw-138 group: lowest univariate p = 0.028,
lowest ridge p = 0.020 — **above the Bonferroni threshold (0.05/48 ≈ 0.001)**. No significant
leakage; ciphertext bytes do not predict the spectrum. (The run aborted on the *owner* group's
synthetic power check — a low-`power-perm` fixture artifact, not a finding.)

## 5. Aptina-keyed AES decrypt attempt (`probe_aptina_decrypt.py`) — NO KEY FOUND
Actually run (not just documented), per the owner's request to try the inverted/256-bit aptina key.
Key candidates from the fw-138 aptina `2ee0f4607c6b5fd5`, its inverted form = `device_id
E02E60F46B7CD55F`, reverse, ascii — derived to 16/24/32 bytes (raw-pad, repeat, **sha256 = the
256-bit form**, md5, sha1-pad). Ciphers: AES-128/256 in ECB/CBC/CFB/OFB/**CTR**, with the
header/`word1`-nonce IV schemes (`decode.decrypt`). Scored by same-target plaintext repeatability
(25 cap + 25 wood) vs 30 random-key controls. **Every candidate scored at the random-control level
(~0.12 baseline); none ≥ control+0.1.** A real key would score ~0.9+. Negative. Consistent with the
key being a firmware KDF secret, not the raw/simply-hashed aptina.

Honest prior: word-swap/reverse/sha256 forms were already negative for the **owner**
(`bounded_identity_20261004`); this is the genuine retry for the fw-138 device's own aptina, the
CTR+`word1`-nonce case, and high same-target power.

## Premises (grain of salt on Vitaly's claims)
- **Verified by us:** aptina `2EE0F4607C6B5FD5` byte-pair-swapped = `E02E60F46B7CD55F` = device_id.
- **Not verified:** the app string *"Indicates a 256-bit key using AptinaID"* was **not found** in the
  decompiled apps we hold; `com.consumerphysics` contains **no scan crypto at all** (only third-party
  AES in libraries), consistent with decode being server-side. Treated as his claim, unconfirmed here.

## Net
These batches add real **corpus statistical power** and 50 **white references** for the fw-138 unit,
and independently confirm "no offline leak". No decode break: the key remains a firmware secret
= KDF(aptina). Scripts: `ingest_fw138_batches.py`, `probe_fw138_batch_leakage.py`,
`probe_aptina_decrypt.py`, `probe_leakage.py`.
