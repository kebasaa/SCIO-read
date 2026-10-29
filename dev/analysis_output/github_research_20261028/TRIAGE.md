# Verification: outside research summary, checked 2026-10-29

Source: `email/SCIO_GITHUB_RESEARCH_SUMMARY.md`, an outside researcher's work of 21-24 October 2026
on another legacy SCiO. The file is git-ignored; this note records only what matters for `dev/`.
They recovered no firmware, no key and no decoder.

## Matching versions do not establish unit identity

The reported file versions (87 = 125, 90 = 22, 91 = 12, 92 = 151) and sizes (119233 / 8196 / 14600 /
32612) are identical to `email/scio-fw151-captures-20261027/file_list_*.json`. The outside unit reports
**`20150812-g:PRODUCTION`**; the owner unit is `-e` and fw-138 is bare. Shared file
versions and sizes can occur across units and do not verify the contributor's identity or tag.

The summary deliberately has no device_id. The owner has asked for it, and
`dev/scripts/ingest_fw151_captures.py` requires explicit device_id, verified i2s tag,
and a matching `scio-wr/2` white reference before replay. No unknown-target scan is
substituted as calibration. The dry-run parse is in
`../fw151_captures_20261028/parsed.json`: six parsed scans; the single scan's available raw USB stream equals its split frames (no multiscan raw stream was checked),
header word0 = 0 in every blob including the gradient (fw-138 had 110), and all second header words are unique; their role as nonces is unproven.
The corrected [parse report](../fw151_review_20261029/parsed.json) preserves source-specific multiscan IDs.

## Claim by claim

| Claim | Status | Our evidence |
|---|---|---|
| iPhone 1.5.20 analysis omits gradients after calibration with a white gradient; model results with `spectrum: null` | outside observation | distinct from local spectrum-preserving mutation tests; calibration-time use remains possible |
| 225,680 layouts (u16/u32/f32, LE/BE, 0/8-B prefix, header/device-id XOR, ratios): none reproduce spectra | outside negative result; related local tests | checksum and bounded campaigns, leakage probes; not identical coverage |
| No blob is a complete zlib/gzip/deflate stream at offset 0 or 8 | independently reproduced on the cited corpus | 402 distinct blobs, 2,412 checks, zero hits; output bounded to 1 MiB |
| Lengths after the 8-B prefix are divisible by 16; AES unconfirmed | known | HANDOVER |
| Firmware endpoint: `new_version: null` | corroborated by earlier local campaigns; outside request not reproduced | no authenticated API call in this audit; not evidence that fw-151 is latest |
| CC2540 DD P2.1 pin 35, DC P2.2 pin 34, RESET_N; lock unknown | known | HANDOVER §2 |
| Image2Spec tag is not the key or matrix | known | DEVICE_FUNCTION_REFERENCE |
| `0x87` selectors 0x58, 0x158 and 0x10058 return the same result | outside observation | consistent with low-byte selection for these cases; no arbitrary-address access established |
| Vendor SAMPLE payload `04 03 02 01 01` and empty payload both yield successful scans with the same blob lengths | outside observation | byte equality and a different readable format were not demonstrated |
| Single CDC config, no DFU or mass storage; TI sniffer vendor requests 0xC0/0xC6 stall | outside observation | not independently reproduced in this review |
| **Battery reply bytes 13-15 = previous gradient bytes 13-15 (44/44)** | **outside report; narrower local observation** | owner fw-147: byte 15 matches in 20/20 replies; opaque bytes already received ([FINDINGS](../stale_buffer_20261028/FINDINGS.md)) |
| CSI DLL 1.9.0.0 (admin manual p.22) | independently verified in rendered vendor PDF | offline client v2.018.029.1 release-note screenshot; library itself not acquired |
| `keepUpgradeFiles` in the consumer app 1.5.19 | lead | outside summary names an in-memory upgrade-model method; persistent caching and local app equivalence unverified |
| BAK / BEK / Image2Spec fields; Matlab export; storage/Docker distribution | independently verified public frontend code | field names and routes confirmed, no values/package/export obtained; Image2Spec display snippets are commented out |
| Firmware capture routes (Android HCI snoop, iPhone PacketLogger, USBPcap) | valid but blocked | needs an update to be offered; none has been |

## Scope of the outside evidence

The table distinguishes reproduced checks from outside observations. The original
225,680-layout implementation, split membership and raw remote traces were not supplied,
so their exact enumeration, RMSEs and device-specific observations remain unverified. Similar local negative results
are corroboration, not identical coverage. The selector and SAMPLE-payload tests
remain outside reports. Negative sweeps constrain only their tested layouts,
offsets, devices and inputs; they do not exclude other decoders or protocol behavior.
The local battery experiment does not close the broader buffer-disclosure question.


## Independently executed checks

Reproducer: `python dev/scripts/verify_research_summary.py --output dev/analysis_output/<new-file>.json`.
[Machine-readable results](../summary_verification_20261029/verification.json) record:

- All 266 processed JSON objects at commit `135d8915388ae64f9c6ba90bb7fdd753d21323f7`
  verified against their Git blob hashes; 197 main pairs, split 94 owner-tag / 103
  bare-tag. Every pair has 331 finite reflectances on exactly 740..1070 nm.
- 1,182 blob size/Base64/hex checks pass. Four analysis roles yield exactly 402
  distinct blobs. All 2,412 complete-stream zlib/gzip/raw-deflate checks at offsets
  0 and 8 fail. Truncated streams and streams with trailing bytes are rejected.
- All six supplied fw-151 scans parse; 18 distinct blobs, all first words zero,
  all second words unique. An additional 108 codec checks give zero hits.
- Saved local battery evidence reproduces 20/20 at offset 15, with one missing
  post-scan BLE-config reply. This is not verification of the outside 44/44 count.

These checks reproduce concrete subclaims without claiming to reproduce the entire
outside layout search. No newly validated decoder or plaintext was recovered.

## New observations and implications

**Repeatability is not a universal key detector.** A deterministic synthetic
control encrypts two compressed, nearly identical sensor-like signals with a known
AES key. Exact decryption plus decompression recovers both original signals.
Signal correlation is 0.9999995, but the correct compressed plaintext's best
integer-repeatability score is only 0.0271. The existing detector's best score with
that correct key is 0.1388, and it selects an incorrect mode. This invalidates a
universal reading of the older assertion that a correct key must score about 0.9.
It does not establish that SCiO uses AES or zlib, or rehabilitate a particular key.
The existing `bounded_campaign.py` and `checksum_campaign.py` already include
cipher-to-codec checks: this is a detector-coverage correction, not a reason to
repeat all completed generic sweeps.

**The CSI library reference is concrete.** The [vendor manual, page 22](https://admin.consumerphysics.com/docs/cp-admin-manual.pdf)
visibly associates CSI DLL 1.9.0.0 with offline client v2.018.029.1 and mentions
logging levels/DEBUG. The rest of the release note is clipped. Ask for the full
release notes and matched package dependencies; do not infer plaintext dumps from
that clipped text. Pages 21 and 36 describe offline clients and per-device builds.

**The Matlab export is a distinct authenticated operation.** Public app code calls
`/admin/logstream/<recordId>?is_py2s=true` with authorization headers, then opens
`logstream_url` from the response. The ordinary log export uses `false`. This
confirms two export modes, not the contents of either. No endpoint was called.
The public template also uses `installation_blobkey.bucket/key` or `docker_image`
from installation records, without embedding a usable package location.

**Identity/tag alone is unlikely to be the full input contract.** The frontend
maps separate `bak_op_hex`, `bek_op_hex` and Base64 `image2spec_params`, and checks
compression and post-processing compatibility separately. Image2Spec display
blocks in the fetched template are commented out, so claiming a currently visible
UI for them is too strong. Field names neither expand BAK/BEK nor prove AES keys.
Inference: any acquired library must be evaluated together with matching device
parameters, processing versions and calibration; a DLL alone may not suffice.

[Public evidence manifest](../summary_verification_20261029/public_evidence.json)
records asset URLs, SHA-256 hashes, relevant line numbers and the visual manual
check. Downloaded source/PDF copies are kept under ignored
`dev/private/summary_audit_20261029/`; no account data or authentication was used.

## Practical route forward, in priority order

1. Obtain an authorized i2s Matlab export with the exact raw scan, white reference,
   spectrum, device tag and processing version. Inspect the export schema for
   intermediate arrays/parameters; validate any transformation on held-out scans
   and distinct calibration groups. This is the most targeted potential bridge
   between opaque blobs and the reconstruction pipeline.
2. Obtain the actual offline-service package and matching CSI dependency/full
   release notes from an authorized holder. Inspect it statically for entry points,
   input formats, device-parameter dependencies and supported hardware revisions.
   Public frontend metadata is not the executable or its keys. HarvestMaster's
   [installation guide](https://harvestmaster.com/data/support/31360%20H2%20NIR%20Upgrade%20Installation%20Guide.pdf)
   documents per-sensor activation; legacy handheld compatibility is unproven.
3. If a genuine update is offered, preserve its API response before any forwarding
   to a device. Local historical `FirmwareUpgradeModel` code confirms Base64 data
   with a four-byte checksum prefix. The exact 1.5.19 `keepUpgradeFiles` method was
   not found in the searched local trees. A null update offer is not a firmware
   image; do not repeat polling without a new trigger.
4. Hardware acquisition remains conditional on a verified pad map and non-destructive
   access. TI's [sample guide, sections 15-16](https://www.ti.com/lit/ug/swru297c/swru297c.pdf)
   requires flashing its example bootloader; it is not evidence of a universal SCiO
   readback command. [Apple PacketLogger](https://developer.apple.com/videos/play/wwdc2019/901/)
   and [Android HCI snoop](https://source.android.com/docs/core/connect/bluetooth/verifying_debugging)
   are documented capture methods, but require traffic containing the sought data.

A candidate must ultimately recover all 331 bands on independently held-out real
pairs (the summary's 1e-6 criterion is a useful minimum), not merely look smooth,
produce a short decompression prefix or match a repeated byte. No new device
connection is needed to complete this audit. The next bottleneck is missing
artifacts, not additional ordinary scans from the owner's device.

Verification: 53 focused tests passed (four new codec/counterexample cases plus
49 importer/stale-buffer cases). No live device operations, authenticated API
calls, firmware writes or outreach occurred. The outside source remains unchanged.
