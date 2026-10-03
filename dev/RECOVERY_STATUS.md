# Evidence-led recovery, October 2026

Completed campaign: [results](analysis_output/recovery_20261003/RESULTS.md),
[verification](analysis_output/recovery_20261003/verification.json).

## Active continuation, 2026-10-03

This section is updated during experiments, not only at handoff. Decoder research
output remains under `dev`; source data and older reports are preserved. The
separately requested power-control library additions below intentionally change
production code, documentation, and tests.

### Native AOT tooling setup (active)

#### Encoded resources / live firmware acquisition follow-up

- User requested APK/code resource inspection and server/USB firmware acquisition.
  Initial port enumeration found no SCIO; after the user connected it, the
  existing allowlisted reader completed successfully with zero captures and no
  writes/resets. [USB evidence](analysis_output/recovery_20261003_followup/usb_firmware_recheck.json)
  confirms firmware 147 and the recorded file sizes/versions/checksum words.
  BLE-ID i2s remains empty (already observed previously); preserve the raw
  response rather than inventing a current tag.
- [Firmware server recheck](analysis_output/recovery_20261003_followup/firmware_server_recheck/summary.json):
  three GET requests to the established endpoint, current versions -> one below
  -> current, using a monotonic 20-second start-based scheduler. All returned HTTP 200 with
  `new_version: null`. Requests used the **historically recorded**
  `20150812-e:PRODUCTION` tag, not a freshly read tag. This is an availability
  recheck, not a previously untested version family. No endpoint enumeration or
  installation. Authentication values were not logged; raw responses are private.
  Recorded wall-clock start gaps were 20.025 and 19.989 seconds (bookkeeping/clock
  jitter). Future runner now waits 20 seconds after each response completes,
  providing a conservative interval rather than relying on start-time timing.
- [Embedded-resource scan](analysis_output/recovery_20261003_followup/embedded_resources.json):
  all nine APK/XAPK archives, 14,471 unique inspected objects, 530 contiguous
  Base64 runs, 3,810 vendor Java files, 66 Java Base64 strings and two endian
  representations of one literal int array. Magic-guided decompression recorded
  2,630 streams; these include ordinary image/resource contents, not 2,630
  firmware candidates. No structurally complete LDR candidate at tested prefix
  offsets. The 26 leads are **size-only** matches, mostly resource metadata,
  time-zone data, an image's zlib stream and decoded ASCII runs. They are not
  verified firmware or calibration; raw leads remain private.
- [Direct DEX arrays](analysis_output/recovery_20261003_followup/dex_arrays.json):
  22 DEX files, 1,667 code-item-bounded array-reference candidates, no structural
  LDR candidates. Of 341 vendor-package occurrences, 335 are `R$` resource
  classes and six repeat the same 80-byte `C$Workshop` array. The latter is
  `Workshop.COLORS` in the supplied old consumer source, not a spectral table.
  Candidate references are bounded by method code_items but not a full Dalvik
  instruction-boundary decoder. Computed arrays remain outside coverage.
- [Three-route summary](analysis_output/recovery_20261003_followup/firmware_routes_summary.json)
  distinguishes size-only leads from firmware. All six 96-byte libapp Base64
  matches originate from 128 ASCII hexadecimal characters; treating them as
  Base64 does not make them calibration tables. A follow-up pass also decodes
  contiguous hexadecimal runs explicitly. [Resource v2](analysis_output/recovery_20261003_followup/embedded_resources_v2.json)
  inspects 14,523 unique objects including 78 hex runs. Its two additional
  size-only leads originate in a Base64 font text resource and `libc++_shared.so`,
  not a demonstrated SCIO firmware/calibration path. There are 28 size-only leads
  total and still no tested-prefix LDR match. Nothing here establishes a key.
- [Updated route summary](analysis_output/recovery_20261003_followup/firmware_routes_summary_v2.json)
  includes the hexadecimal pass; earlier reports are retained. After adding hex
  recognition, all seven targeted codec/DEX tests pass (0.44 seconds). The last
  full research run had 113 passing tests. Whitespace checks pass and targeted
  report scans found no personal absolute paths or credential assignments.
- USB: the fresh session used established metadata reads only, with zero errors,
  captures, resets or writes. READ_FILE_HEADER returns metadata; FILE_DOWNLOAD
  is host-to-device writing. No documented body-read operation was found in the
  reviewed command paths. Earlier appended-offset/header and reserved-opcode
  negatives remain bounded evidence; they were not repeated. Do not repurpose
  FILE_DOWNLOAD or guessed write/debug commands for acquisition.

Verification so far: **113 research tests passed in 69.40 seconds** with Python
network connections blocked, including synthetic bounded codec and DEX payload
tests. No APK executed. No validated firmware/calibration body or spectral
decoder recovered; proprietary containers and opaque/computed resources remain
possible. Server offers can be device/account dependent; these null results do
not establish that every firmware copy is gone.

#### Firmware container audit (completed bounded pass)

The exact Lab source distinguishes two storage mechanisms that earlier handoff
wording conflated. `ScioFirmwareFiles` is populated from a file-list response as
an array of key/version pairs. It is not the update bodies. Actual update bodies
come from `new_version` JSON fields named by the firmware enum and are cached
as bare-name strings (`dsp_op`, etc.), indexed by a per-user
`firmware.file.names` string set. Clearing that set does **not** remove the bare
strings. The checksum-prefix-to-header comparison reads U32LE values; the app
does not thereby reveal how the checksum was calculated.

[Nine hashed storage/transfer observations](analysis_output/recovery_20261003_followup/firmware_storage.json)
support that correction. Body transfers use messages of at most 192 bytes; this
is host-to-device transfer and does not expose a readback operation.

[Corrected container search](analysis_output/recovery_20261003_followup/firmware_containers_v2.json)
examined 13,246 text files/archive members (5,006 unique contents; 8,240 duplicate
occurrences), including six supplied top-level source ZIPs. Among 2,594
marker-bearing unique texts, it found **zero candidate firmware bodies** and one
actual `new_version: null` response in `log_20211020_calibration.txt`. That
recorded response supplied no update; it does not establish permanent firmware
unavailability. The first immutable report is retained; v2 broadens the marker
filter to handle single-quoted XML names as well as JSON/double-quoted XML.

Coverage: UTF-8-decoded XML/JSON/TXT/LOG, at most 16 MiB per file/member, JSON
documents or one line-prefixed object per line, bare-name XML strings. No nested
archive traversal, arbitrary Java arrays/escaped JSON strings, multiline log
fragment reconstruction, custom binary containers or firmware acquisition.
Candidates would only be named Base64 containers, not automatically valid code
or calibration. Synthetic tests cover actual prefix preservation, metadata/null
distinction, both XML quote styles, malformed and unrelated inputs. No server
requests, device commands, resets or production changes.

Verification: **106 research tests passed in 57.42 seconds** with Python network
connections blocked. The initial metadata test fixture had invalid JSON quoting;
it was corrected using JSON serialization and rerun successfully. No parser
behavior was relaxed to pass it. Whitespace checks pass; targeted new artifact
checks found no personal absolute paths or credential assignments.

### Next-artifact decision after the container audit

The missing decisive input remains a **body**, not another file header:
`dsp_dec` (recorded version 12, length 14,600), `dsp_op` (147, 32,628), `dsp_boot`
(17, 7,284), or calibration files 100..103 for the recorded device/generation.
These sizes identify comparison targets, not a restriction to only those
versions. Existing headers/checksums cannot reconstruct the contents. A firmware
body must be validated structurally before architecture or codec attribution;
a table body must have an independently supported layout and device association.

Remaining software scope: unreviewed encoded arrays/custom resources, and any
independently supplied firmware artifact. Do not repeat the completed Base64
diagnostic trace or claim all software possibilities are exhausted. The available
phone/backup route is closed. If choosing acquisition from this physical device,
the next session must first identify board/storage/debug topology and electrical
requirements without writes, reset or protection changes. That requires separate
hardware authorization; no unverified pinout, programmer choice or command is
recommended from the current evidence. Consider both BF512 and CC2540, since
the transformation's processor location remains unproven.

#### 1.5.19 validation producer resolved (next continuation)

[Static trace](analysis_output/recovery_20261003_followup/validation_trace.json)
records 13 call edges checked against the hash-pinned binary and hashes of private
disassembly. `0xc74384 -> 0xc75bc0 -> 0x9c255c` reaches a per-role helper at
`0xc75cac`. The helper constructs diagnostic names from suffixes, explaining why
searching only full diagnostic labels originally found the consumer.

- `_decoded_bytes` is **Base64-decoded byte length**, not spectral values. The
  call chain reaches `0x61db14`, with six-bit accumulation and padding errors
  `Missing padding character` / `Invalid length, must be multiple of four`.
- The helper records encoded string length and preview before decoding. Preview
  retains at most 96 input code units, with `...` appended when shortened. It is
  not an image or decoded-spectrum preview.
- Nonempty decoded payloads shorter than four bytes produce `_too_small`.
  Empty required fields produce `_empty`. Recognized decoding errors produce
  `_invalid_base64` and decoded count -1. Unrelated exceptions are rethrown.
- Sample and sample-dark are required. Sample-gradient may be empty. White
  fields are examined only if their keys exist; present white sample/dark are
  required and present white gradient may be empty. A separate diagnostic flags
  an empty sample alongside a nonempty gradient.
- This helper has no exact 1800/1416-byte check, eight-byte envelope parsing,
  status/checksum verification, body decompression/decryption, calibration or
  331-band calculation. This is a bounded statement about this helper, not the
  entire app or server. Its minimum of four bytes is not a device framing spec.

These are static findings, not runtime reproduction. Exact coercion/whitespace
rules, exception class names and accepted Base64 variants remain partially
unresolved. No claim that Python Base64 has identical acceptance semantics.
No device/server requests were used. Four primitive-tool tests pass, including
new ARM BL sign-extension, conditional-call and BLX-exclusion checks.

#### Mock constants deduplicated against older source

[Comparison](analysis_output/recovery_20261003_followup/mock_constant_comparison.json)
finds all six exact Lab code constants byte-identical to both copies in the
supplied source tree labeled `2017-09-19`. The pre-existing Lab decompilation
exposes five of the six allowlisted declarations; those five also match. This
comparison is limited to three named source files, not all repository content.
The freshly extracted constants are **not new independent captures** and must
not inflate the corpus/confirmation count. The first-word-110 gradient framing
is therefore also present in those historical code fixtures. Neither matching
hashes nor the directory date establishes physical device identity or numeric
spectral truth.

Next analysis should follow a different evidence-bearing route: unresolved
firmware/calibration resource references and validated body acquisition, or a
specific new envelope/codec prediction supported by artifacts. The 1.5.19
diagnostic labels and these repeated mock fixtures no longer justify another
generic key or compression sweep. This does not exclude encryption, compression,
or an unreviewed software path. Device resets and speculative write/readback
commands remain out of scope; the historical phone/backup route is unavailable.

Continuation verification: **103 research tests passed in 37.23 seconds** with
Python socket connections disabled. `git diff --check` reports no whitespace
errors. Targeted new-report/script checks found no personal absolute paths or
password/token assignments. Production code was untouched; its last unchanged
suite result remains 53 passing tests from the preceding pass.

#### Analyzer 1.5.19 diagnostic trace (completed bounded pass)

- Exact ARM32 library extracted and hashed in `arm32_target.json`. The targeted
  Dart 3.11.4 snapshot probe validates 38,554 read-only string headers and a
  candidate 51,613-entry object pool. It is not a general snapshot deserializer.
- ARM instructions reference `sample_gradient_chars`,
  `sample_gradient_decoded_bytes`, and `sample_gradient_preview` at virtual
  addresses `0xc756cc`, `0xc75778`, and `0xc75904`. The surrounding code reads
  these values from a map and forwards them under `invalid_scan_payload_*`
  diagnostic labels. This is a diagnostic consumer, **not a recovered decoder**.
  Caller `0xc744ec` supplies phase `background_single_scan_before_upload`.
  The subsequent continuation above resolves the producer and Base64 meaning.
  All four exact DEX
  files lack these three literal labels; this narrows the static lead but does
  not prove where the map is produced.
- Raw pools/disassembly remain private. No device or server interaction.
  See [reviewed findings and format-source hashes](analysis_output/recovery_20261003_followup/app_followup.json).
  Three synthetic tests cover integer byte order, pool framing/rejections and
  ARM32 load matching. They validate those primitives, not full snapshot recovery.

#### Exact Lab Dev Toolkit 1.3.12.144 APK (completed bounded pass)

- [Full member/DEX hash inventory](analysis_output/recovery_20261003_followup/lab_1_3_12_inventory.json):
  2 DEX files, 2,585 archive members, no packaged `.so` libraries. Fresh JADX
  1.5.6 run processed 5,084 classes but exited 1 with 84 errors. Do not call this
  exhaustive decompilation. Extracted files and raw source stay under private.
- Reviewed QuickScan -> SamplesProcessor -> CommonServerAPI.newRecord ->
  ModelParser -> RecordModel. The request carries raw Base64 triplets and i2s;
  the displayed spectrum is parsed from server `spectrum_reflectance`.
  `getSpectrum()` and `getSpectrumReflectance()` return the same array.
- `ProcessOfflineTestModel` uploads queued records through `testModelMany` and
  copies returned wavelengths/spectrum. Its name does not establish local
  spectral decoding. `getSampleSpectra` sends Log, first Derivative, SelectWL
  740..1070, SubtractAvg, and `x_step=2` as server request options; this is not
  an offline implementation or a replacement for the 331-band validation axis.
- [Mock fixture audit](analysis_output/recovery_20261003_followup/lab_fixtures.json):
  six asset blobs already present in the earlier asset inventory, plus six
  different `MockSamples` code constants. All 12 are distinct. Dark/sample are
  1,800 bytes and gradients 1,416 bytes. The two code-constant gradient first
  words are 110, versus zero for the asset gradients. Meaning of 110 is not
  established; do not silently remove/rewrite it. The six code-constant hashes
  were not found in previous research JSON reports, but this does not establish
  novelty against every older raw fixture. No matching numeric spectrum or
  authenticated capture identity is established; keep these exploratory.
- Mock ID `503E5732B5EF1F35`, address `D0:B5:C2:97:83:42`, i2s
  `20150812-o:PRODUCTION`, firmware 128 are class-level canned values, not proof
  of capture identity or a key. The separate legacy service mock's spectrum and
  white-reference functions throw `Not implemented`; canned metadata is not a
  simulated decoder.
- Firmware IDs/checksum-prefix/cache/transfer paths agree with earlier SDK
  observations. No firmware bodies, actual dead-pixel indices, calibration
  tables or locally implemented payload codec were recovered in this pass.
  JPEG use in the reviewed QuickScan path is for an attached photograph, not
  SCIO bytes. This bounded result does not exclude compression of SCIO data.

The subsequent continuation above resolves the diagnostic producer and compares
the code fixtures with older source by decoded hash. Do not repeat either as an
unexamined lead. Do not spend oracle requests on mock IDs as if they were established device
identities. Any further raw-to-spectrum claim still needs paired numeric truth.

Verification for this follow-up: **100 research tests passed in 39.95 seconds**
with Python socket connections blocked, including three new ARM32 probe tests.
The unchanged production suite also passes: **53 tests in 7.09 seconds**.
`git diff --check` passes (existing line-ending notices only). A targeted scan of
new scripts/reports found no personal absolute paths or password/token assignments.
Raw source/pools remain ignored private artifacts. No production code was changed
by this follow-up, and no device/server/reset commands were issued.

#### Exact modern Android producer audit (completed bounded pass)

- Downloaded official JADX 1.5.6 into ignored `dev/private` (separate version
  numbering from Analyzer 1.5.6). Existing Java 17 is used. No system installation.
  [Tool/archive/DEX hashes](analysis_output/recovery_20261003_followup/modern_dex_inputs.json).
- Extracted four DEX files from the exact supplied 1.5.6 XAPK and started two-thread
  static decompilation, with resources disabled and all configured cache/temp/output
  paths private. Full run exited 1 with 161 reported errors; output is not an
  exhaustive successful decompilation. Relevant methods were reviewed, with
  fallback output used to check the status-copy omission. No APK was executed.
- Recovered bridge `ScioReadingModel`: copies public/internal reading getters to
  `sample`, `sampleDark`, `sampleGradient`, `timestamp`. Exact APK's
  `ResponseCommand.getDataAsBase64` is a direct Android Base64 encoding of data.
  Capture completion and method-result dispatch are now connected in
  [17 reviewed observations](analysis_output/recovery_20261003_followup/modern_bridge_v2.json).
  BLE reporter -> framing parser -> whole-payload Base64 -> reading getters ->
  bridge model -> Jackson JSON -> pending `MethodChannel.Result.success`.
  `scanLightOff` uses the event channel separately. This corrects the loose
  earlier description of every scan result as an event.
- Sample status is read as U32LE at payload offset 0 but not stripped. Public
  `ScioReading` constructor does not copy the separate status field (confirmed
  in a successful single-class fallback run); bridge model omits it. An SDK
  success callback is therefore not evidence that the payload status is zero.
- Modern timeout setter accepts **seconds directly** and writes `00 00` plus
  U16LE. Older UI signed-byte minute conversion is not a demonstrated device
  requirement. Production helper is unchanged; no power command was issued.
- Mock SDK identifiers and placeholder readings documented in the device
  reference; all nested APK archives checked for `assets/mock/`, with zero files.
  Do not assign mock identity to the separate recovered Flutter fixture.
- Returned-spectrum reference at `0x6ce4ac` reads a nullable List from the
  `spectrum` field and maps it with a double-typed closure at `0x6cf004`.
  Closure checks a numeric input and dispatches a numeric method; caller expects
  doubles. This is consistent with number conversion, not a raw-data transform.
  Network-to-model caller remains untraced: do not claim the complete response
  path or a particular endpoint from a `spectrum` field alone.
- No offline numeric decoder recovered. This pass narrows the pocket-device
  Android transport path, but does not exclude another app route/version,
  compression-only firmware, or a transform in device/server code. Next useful
  software target is the newer 1.5.19 ARM32 gradient diagnostic call sites;
  they remain untraced, and their label names are not evidence of decoding.
- Full research regression after the bridge audit: **97 passed in 69.07 seconds**
  with Python network connections blocked. Extraction/audit scripts completed,
  private ignore rules verified, and new shareable artifacts checked for personal
  absolute paths. No device/server calls, reset, timeout write, production edit
  or commit in this continuation.

Prior checkpoint: [six reviewed Flutter observations and embedded triplet](analysis_output/recovery_20261003_followup/flutter_dataflow.json).
The triplet is 1800/1800/1416 bytes and not present in the canonical manifest;
no identity or spectral truth is attached. Reading parser `0x31db44` checks and
copies three strings, event parser `0x849cf8` delegates to it, and white serializer
`0x31dd48` copies them to server field names. Request builder `0xa0a09c` likewise
forwards six fields. **No offline numerical transform has been recovered.**
This closes part of the modern app's serialization path, not its native-platform
producer. New direct-reference evidence: [full executable-segment scan](analysis_output/recovery_20261003_followup/native_pool_refs_v2.json).
The then-planned platform-side trace is covered by the newer audit above; the
request consumer/returned spectrum path remains partial. Do not infer its missing
semantics from older Java versions. Four focused indexing/instruction tests passed.
Full research regression after these changes: **97 passed in 57.78 seconds**
with Python socket connections disabled. No production/source-data edits, device
commands, vendor-server requests, or new tool downloads in this continuation.
Private dump ignore rule and shareable new-file personal-path checks passed.

- Continued native export: first synthetic-class exporter compiled but crashed
  (SIGSEGV); retained under private `flutter_1_5_6_analysis_native`. Code review
  found ordinary `DartFunction::PrintHead` dereferences Function metadata, which
  synthetic functions lack. Revised exporter uses address/size-only headers for
  synthetic functions; rerun uses a separate `_native_v2` output directory.
- Added sanitized native function indexer and two regression tests (both pass).
  It exports only function metadata, direct branch targets, allowlisted exact
  scan-field references and hashes, not arbitrary constants. Initial test attempt
  hit a system temporary-directory permission error; rerun uses `dev/tmp`.
- Second exporter also crashed: `CodeAnalyzer::AnalyzeAll` had skipped the
  synthetic library too, leaving analysis data absent. Including the library
  and its separate top class in **both** analysis and export succeeded in v3.
  Some leaf-runtime IL analysis warnings remain; raw ARM64 instructions must
  arbitrate uncertain annotations. Reproducible changes are preserved in
  `scripts/blutter_native_export.patch` against the pinned upstream commit.
- New request builder recovered at `0xa0a09c`: six scan/white values are loaded
  from object fields and passed unchanged to map insertion calls. This is a
  narrow observation about this function, not the complete capture pipeline.
  `i2s_tag_config` comes through `0x6ff260`, which reads `device_i2s`; no key
  derivation is established here. Many direct callees remain absent from the
  metadata-based dump. Added bounded Capstone disassembly and full executable
  segment pool-reference scanning to follow these bodies independently.

- User authorized tool downloads after receiving the analysis/tool plan. Target:
  supplied 1.5.6 ARM64 libapp/libflutter; native version marker identifies Dart
  **3.7.2**. [Hashed extraction](analysis_output/recovery_20261003_followup/flutter_target.json).
- Blutter upstream `worawit/blutter` cloned at commit
  `4a60ac648bf448c5a7596437243bcd0b9376fdf0` under ignored `dev/private`.
  Only local change so far: bound both Ninja invocations to two build jobs.
  Objective: resolve object-pool strings to code/functions, then trace payload,
  calibration and firmware paths. Generated Frida scripts will not be executed.
- Reusing installed Ubuntu GCC 13.3 and CMake via WSL, **not MinGW**. User also
  supplied an MSVC discovery example; vswhere confirms Visual Studio 18.9 exists
  as fallback. No compiler installation. Downloaded nine Ubuntu dependency
  packages (24.5 MB) and unpacked only under `dev/private/native_prefix`; no
  system package installation. Includes ICU, Capstone, Ninja, pkgconf, pyelftools.
- Reproduction: `scripts/setup_native_tools.sh`, `scripts/run_blutter_local.sh`.
  Matching Dart runtime source/build remains in the private tool tree. No device
  or vendor-server requests and no SCIO uploads. Build/result status follows.
- Matching Dart runtime (272 actions) and Blutter (22 actions) built successfully;
  initial analysis exited successfully and generated annotated assembly/object pools.
  Found a dump-completeness hazard: case-only obfuscated library names collide on
  the Windows filesystem. Added a unique library-ID filename suffix and reran
  into a separate private output directory. Do not use the original dump for
  absence claims. [Revised tool hashes](analysis_output/recovery_20261003_followup/native_toolchain_unique.json).
  [Setup/reproduction notes](NATIVE_ANALYSIS.md) and
  [toolchain hashes](analysis_output/recovery_20261003_followup/native_toolchain.json).
- Collision-safe rerun exited successfully: **1,676 assembly files**, versus
  977 in the original output. Neither generated Frida script was executed.
  Object pool contains `sample_dark` at `0x335a0` and `sample_gradient` at
  `0x335a8`, but no direct references to those offsets or strings were found
  in the emitted assembly. This is an unresolved coverage gap, not evidence
  that the app does not process these fields.
- Next concrete tooling issue: upstream `DartApp.cpp` lines 490–500 puts
  obfuscated functions with Smi code owners into `nativeLib.topClass`.
  `DartDumper::DumpCode` walks `app.libs` and skips internal libraries;
  `nativeLib` is a separate member. Extend assembly dumping to include this
  synthetic top class, then trace the payload references before expanding key
  or compression sweeps. This route has not yet been tested.
- Concurrent full research regression run completed: **93 passed**, with Python
  socket connections disabled. This tests research code, not native-tool accuracy.

### Reversible-representation codec probe results

- User renewed device exploration for offline decoding. Keep power/reset work
  separate: no further reset, timer change, speculative write, scan or server
  request was made in this continuation. No device access was needed.
- Identified coverage gap: the corrected compression-only sweep did not test
  word-swapped/bit-reversed representations. Added keyless `representation_codecs`
  probe: identity control, swap16, swap32, per-byte bit reversal; offsets 0–32;
  raw DEFLATE, zlib, gzip, bzip2, LZMA containers; bounded output below 65536 bytes.
  Misaligned word swaps are skipped, never silently truncated. Complete EOF is
  required; trailing bytes are recorded rather than treated as an automatic failure.
- 225 exploratory canonical blobs, **148,500 actual configurations**; 75 distinct
  blobs associated with the frozen confirmation records (including shared white
  components) excluded. Fresh cap captures, foreign samples and spectral targets
  were not used. [Reproducible result](analysis_output/recovery_20261003_followup/representation_codecs.json).
- **12 complete parses**, all raw DEFLATE, producing 45–606 bytes after consuming
  only 8–41 bytes; at most two blobs share a successful representation/codec/offset.
  Random controls also produced four complete parses. These are unvalidated
  parses, not intermediates or spectra; no new decoder established. Counts alone
  do not constitute a statistical test or exclude other representations/codecs.
- Corrected `transform_class.py` to schema 2: fixed container size does not
  exclude variable-rate compressed streams with padding; entropy does not prove
  whitening or absence of packing. Removed unsupported pixel/binning ratio,
  exhaustive app-coverage and endpoint assertions. Prior reports remain intact.
- End-to-end synthetic fixtures recover zlib streams in fixed containers under
  all four representations. Tests cover output limits, nontruncating alignment,
  and the variable-compression/fixed-container counterexample. Initial tests
  caught an uncaught LZMA exception; corrected before the recorded corpus run.
  Final focused regression run: **8 passed, 44 deselected**. This is not a claim
  that the full research suite was rerun. Production code and source data were
  not modified in this continuation.

### Power-control investigation and library additions

#### Reset request sent before authorization was withdrawn

- User first explicitly authorized reset, then withdrew authorization and
  requested documentation only. The single 0x83 request had already been sent
  before the cancellation arrived. No further device work is authorized under
  that request; do not resume reconnection or reset testing without new direction.
- `validate_reset_once.py` saved identity, timer and file headers 100–103 before
  attempting exactly one reset. It made **zero timer writes**. Reset response
  timed out (`ScioTimeout`); three bounded read-only reconnect attempts each
  failed with `SerialException`. No reset retry occurred, and no after snapshot
  was obtained. On cancellation the process was already complete; an interrupt
  request returned its completed result. No subsequent device commands sent.
- Evidence: [reset validation directory](analysis_output/recovery_20261003_followup/reset_validation_01/),
  especially `before.json`, `reset_result.json`, and `comparison.json`.
  Transport loss is consistent with a reset/disconnection but does not prove
  restart, sustained power-off, or preservation/erasure of settings. Do not mark
  reset behavior hardware-validated. Current action is documentation only.

- **User constraint on reset:** permitted only if it restarts without resetting
  settings. Reviewed rename, onboarding and firmware-upgrade callers: they
  strongly support restart intent, but the firmware handler and comprehensive
  settings-retention evidence remain unavailable. No reset or timer write sent;
  hold this test under the user's condition. Added library warning and
  [source-hashed caller evidence](analysis_output/recovery_20261003_followup/reset_semantics.json).

#### Read-only hardware validation prepared

- **Live follow-up succeeded after the user connected the unit:** exactly three
  reads, ID/timer/ID; both 28-byte identity payload hashes match, firmware 147.
  READ_BLE 0x9B returned four bytes `00 00 68 01`, interpreted by the inspected
  app layout as **360 seconds (6 minutes)**. No settings writes, reset, or scans.
  [Live read evidence](analysis_output/recovery_20261003_followup/power_read_live_01.json).
  This validates USB timer-response reading on this unit, not physical timeout
  duration, persistence, writes, reset outcome, or wake capability. The earlier
  timeout was not sufficient to conclude this command is unsupported.
  Added the observed four-byte response as a parser regression fixture:
  **57 tests passed** (53 production plus four read-only-probe tests).

- No SCIO USB port was detected during this continuation. Asked the user to
  connect and fully wake the unit; no device commands were attempted.
- Audited both supplied btsnoop logs for complete 0x83/0x9A/0x9B frames: zero
  occurrences. This is a capture-bounded absence, not a capability exclusion.
  [Traffic report](analysis_output/recovery_20261003_followup/power_traffic.json).
- Added `scripts/probe_power_readonly.py`: explicit `--live` required; exactly
  one detected device; at most ID/read-timer/ID, three-second transport timeout,
  no retries or settings writes. Failed initial control stops the probe; timer
  failure still permits a final awake control. Unexpected response opcodes are
  rejected, identity bytes are hashed rather than exported. A successful read
  would still not validate writes, shutdown timing, reset, or remote wake.
  [Frozen read plan](analysis_output/recovery_20261003_followup/power_read_plan.json).
- **21 focused tests passed**: 17 production power tests plus four mocked
  read-only probe tests. No production code changes in this continuation.

- User requested USB/BLE on/off investigation and library support if evidenced.
  Found app-supported automatic-off timing, not immediate-off or remote-on.
  READ_BLE 0x9B reads U16 seconds at offset 2; WRITE_BLE 0x9A sends `00 00` plus
  seconds LE. The activity resets with 0x83 after success. No live commands sent.
- Documented the exact signed-byte adjustment in consumer and researcher source,
  observed 1–30 minute UI range, manual button instructions, and limitations in
  [device function reference](DEVICE_FUNCTION_REFERENCE.md#power-control-usb-and-ble).
  Six source-hashed anchors: [power dataflow](analysis_output/recovery_20261003_followup/power_dataflow.json).
- Added pure `src/scio/power.py`, `ScioUSB.read_power_saver`, guarded
  `set_power_saver`, and separate guarded `reset_device`. Setter does not reset
  automatically; timeout does not cause retry. Probe denylist remains unchanged.
  These USB write operations are explicitly marked hardware-unverified.
- **52 production tests passed** (17 new parameterized power tests). Source data
  untouched. Earlier 453-file no-change attestations apply to their historical
  runs, not this authorized production-code change. Flutter tooling permission
  remains a separate pending question; no external tools downloaded.

### Acquisition constraint confirmed by user

The original 2015 Android phone and its app-data backup are unavailable. Do not
keep suggesting recovery from that phone or backup. Continue with the supplied
apps/archives/logs and existing device; a new phone session would not recreate
historical cached firmware. Physical/debug acquisition remains a separate session.

### Native-path inventory and calibration-flow continuation

#### Phone-integrated service boundary follow-up

- Checked existing Ubuntu tooling: its installed GNU objdump lists x86 targets;
  Python lacks capstone/elftools/lief/darter. No packages installed. Asked whether
  isolated open-source tooling and matching Dart sources may be obtained under
  `dev/private`; this would not upload SCIO artifacts.
- Inspected `ScioPhoneInternalDevice`: it loads `android.hardware.ISCiO` by
  reflection and obtains `SCiO_service` through Android ServiceManager. Its
  `takeSample` wrapper Base64-encodes three returned byte arrays, not numerical
  spectra. This is a distinct phone-integrated hardware route, not evidence that
  the unavailable original phone had an offline decoder.
- Added a bounded DEX class-definition audit to distinguish references to that
  external interface from a packaged implementation. All 22 DEX files in nine
  archives parsed: nine caller-class occurrences, zero definitions of the exact
  `ISCiO`/`ISCiO$Stub` descriptors. Three parser tests passed, including a fixture
  where the descriptor string exists but no class definition does.
  [DEX evidence](analysis_output/recovery_20261003_followup/phone_service_boundary.json).
- Documented phone-wrapper selectors/buffer roles and placeholder values in the
  device-function reference. Constant firmware 128 and temperatures 20/25 are not
  measurements of the connected pocket device. These seven method observations
  have [source-hashed anchors](analysis_output/recovery_20261003_followup/phone_wrapper_dataflow.json).
- This batch's focused DEX/native audit tests: **5 passed**. All 453 input hashes
  unchanged; no personal-path/credential-pattern matches in new batch artifacts.
  Full research-suite result of 80 below belongs to the preceding continuation,
  not a rerun including the three newly added DEX tests. No network analysis,
  device, or firmware-write commands were sent. Native AOT tracing is pending
  the requested tooling choice; no external tools have been downloaded.

- Added `scripts/audit_native_paths.py` to inventory every packaged native library
  across the nine supplied archives, retaining duplicate provenance by hash.
  It records exported JNI names, snapshot-format headers, and narrowly selected
  SCIO payload/calibration literals without exporting arbitrary string contents.
  Completed inventory: **9 archives, 50 library occurrences, 27 unique hashes**,
  no ELF parse errors. [Native evidence](analysis_output/recovery_20261003_followup/native_paths.json).
- The 1.5.19 ARM32 snapshot includes `sample_gradient_decoded_bytes`,
  `sample_gradient_preview`, and `sample_gradient_chars`. Their nearby strings
  are unrelated translations/type labels: string proximity is not a call graph.
  These are tracing targets, not evidence that the app decodes a spectrum.
- No ARM disassembler or Dart snapshot parser was found in the checked Python
  runtimes or command path. Full AOT control-flow tracing remains incomplete;
  identifying snapshot versions and object-pool requirements is preparatory work,
  not a substitute for tracing callers. No new server or device requests.
- Added eight source-hashed calibration-flow observations. The local checksum
  loop only interprets the server-supplied four-byte prefix; it does not reveal a
  checksum algorithm. Device header word at offset 12 supplies the comparison
  value. I2S is passed as `compression_version` in checksum reporting, not derived
  as a key. [Calibration evidence](analysis_output/recovery_20261003_followup/calibration_dataflow.json).
- Per user request, maintain [DEVICE_FUNCTION_REFERENCE.md](DEVICE_FUNCTION_REFERENCE.md)
  for functional findings, not just decoding experiments. It now records every
  observed file-header word, file IDs 87/89–92/99–103, relevant wire commands,
  the distinct internal task-ID namespace, table roles, checksum flow, and
  unresolved formats. Actual dead-pixel indices and binning values remain missing.
- Added four more hashed observations for identifier parsing, temperature
  conversion, and wire command IDs. The reference distinguishes the Java
  temperature handler's integer truncation from the repository's float variants,
  and notes that its BLE handler does not read the repository-labeled serial
  fragment. [Identity/temperature evidence](analysis_output/recovery_20261003_followup/identity_temperature_dataflow.json).
- Verification for this continuation: **80 research tests passed with Python
  socket connections disabled**; 453 production/source-data hashes unchanged.
  New batch artifacts had no matches in the bounded personal-path/credential
  pattern scan. No new network requests, firmware writes, or hardware actions.

### Dark-affine and local plate follow-up

- Froze a per-band affine dark-change model using the two prior sample responses,
  then completed a user-authorized seven-request test on two other 2020 historical
  samples plus a third self-reference. The two-point fit is not evidence by itself:
  new combinations must satisfy its predictions without refitting. Both fresh and
  retrospective confirmation sets are excluded. All seven requests returned valid
  spectra and the historical controls passed; minimum request-start spacing was
  **20.893 seconds**. No further requests were used for the offline checks below.
- The affine model fails on both out-of-fit combinations: 172 bands fail for the
  additional needle sample (max error `0.013909501975982286`), and 310 for the soil
  crust sample (max error `0.05754657100942495`). Do not describe the dark change
  as a fixed per-band gain plus offset. This does not distinguish nonlinear from
  cross-band or sample-dependent processing. Raw results and frozen coefficients:
  [dark-affine evidence](analysis_output/recovery_20261003_followup/dark_affine/comparison.json).
- The third self-reference matches the previously recovered C curve on all 331
  bands, max error `2.220446049250313e-16`, without refitting. Its applicability
  is still limited to the tested device/tag and intact input configurations.
- Read-only spreadsheet-skill audit of `calibration_plate_Polypen.csv` found 256
  points over 324–790 nm, only 30 exact wavelengths shared with the 331-band factor.
  Neither C nor 1/C matches those measurements numerically: RMSE approximately
  0.04073 and 0.06031 respectively, with no fitted rescaling or interpolation.
  The file does not identify the SCIO/reference or measurement conditions, so this
  does not disprove a physical association. It cannot supply the full-band factor.
  The CSV remains unchanged. Evidence:
  [plate comparison](analysis_output/recovery_20261003_followup/plate_factor_comparison.json).

### Offline response-structure checks

- Tested the broader hypothesis `a_i X_i - b_i Y_i = V(lambda)`: per-sample
  scalar gains might explain the dark swaps through one shared per-band difference.
  Anchored the first gain to one to exclude the trivial zero solution, fitted
  remaining gains on even-index bands, and evaluated the other bands too.
  All three comparisons fail `atol=rtol=1e-6`: 253, 254, and 239 failed bands,
  with maximum absolute errors about `1.0882e-5`, `1.0697e-5`, and `1.3565e-5`.
  This approximate fit is not a recovered transform. The data were already
  inspected; alternating-band evaluation is not independent confirmation, and
  these exploratory gains must not become fitted rescaling in decoder validation.
- Polynomial shape checks of C and 1/C at degrees 1, 2, 3, 4, 6, 8, and 12
  also fail numerical equivalence (maximum errors remain above `0.0014`).
  Finite differences through order four have no entries below `1e-12` in
  magnitude. This does not exclude generated, encoded, or other calibration
  representations; it only bounds these simple curve hypotheses.
- Reproduction: `scripts/analyze_response_structure.py`; source hashes and
  numerical results: [response structure](analysis_output/recovery_20261003_followup/response_structure.json).
- Research regression suite: **78 passed**, with Python socket connections
  disabled; unchanged production suite: **35 passed**. All 453 source-data and
  production file hashes match the earlier input snapshot. A bounded scan of
  this batch's new scripts/reports found no personal absolute-path or credential
  pattern matches (not a guarantee about the entire repository).
  No intermediate blob decode or absolute sample/white vectors have
  been recovered. The next useful software step is deeper native calibration/
  payload-path tracing, not another unstructured mutation sweep. The unavailable
  historical phone/cache route remains closed.

### Symmetry and dark-model follow-up

- Existing intact white/white-dark responses already test the inverse-spectrum
  additive identity: `1/Rwd - 1/Rw = 1/Rd - 1/R0`. It **fails** the declared
  `atol=rtol=1e-6` gate: maximum residual about `9.298e-6`, versus maximum dark
  effect `7.8624e-4`. This constrains a simple additive white-domain model in this
  configuration; it does not exclude dark correction with other scaling or
  nonlinear operations. No extra requests were needed for this check.
- User-authorized `probe_symmetry.py` completed eight requests, spaced
  at least 20 seconds: three historical controls, two self-references, one complete
  triplet exchange, and at most two sample-dark substitutions. The second dark
  substitution is skipped if the first yields no valid spectrum. It does not
  repeat the previously rejected dark alternative or use the fresh holdout set.
- All eight returned HTTP 200 with valid spectra, all controls passed, and the
  minimum request-start gap was **20.911 seconds**. No dependent request needed
  skipping. Evidence and predeclared hypotheses:
  `analysis_output/recovery_20261003_followup/symmetry/`.
- Predeclared unity and uncorrected reciprocity hypotheses failed on all 331
  bands. Sample-side additive-dark identity failed on 321 bands, max error
  `4.577674380390473e-4`; both dark substitutions were accepted, so this is a
  numerical mismatch, not a quality-rejection artifact.
- **New response factor:** both self-reference pairs yield the same non-unity
  curve `C(lambda)`, differing by at most `2.220446049250313e-16`. Its range is
  1.0223501318382036–1.054725644460159 on 740–1070 nm. Using this observed factor,
  `R(B,A) = C(lambda)^2 / R(A,B)` holds with max error `4.440892098500626e-16`.
  This corrected formula is a post-observation hypothesis check, not the original
  predeclared test. It supports a common-factor ratio model for these inputs;
  it does not prove calibration meaning, universality, physical units or absolute
  sample/white values. See [self-response factor](analysis_output/recovery_20261003_followup/symmetry/self_response_factor.json).
- Used that numerical lead for a bounded APK table search: 33,060 unpacked members
  across nine archives, 32 exact four-value patterns (four band anchors; float32/
  float64; both byte orders; C and 1/C), **zero hits**. This does not exclude
  generated, quantized, interleaved or encoded tables. Evidence:
  [factor-table search](analysis_output/recovery_20261003_followup/factor_table_search.json).

### Java path tracing (scoped, not an exhaustive native audit)

- Recorded twelve source-hashed method observations in
  [Java dataflow evidence](analysis_output/recovery_20261003_followup/java_dataflow.json).
  Scope is the supplied `classes-dex_out` source tree; its APK/version mapping was
  not newly established. Flutter AOT instruction/object-pool tracing is still open.
- In the inspected BLE/SDK scan path, response payloads are Base64-encoded, stored
  as sample/dark/gradient strings, copied into public reading objects, and inserted
  directly into analysis JSON. These method bodies contain no numerical decode.
  The consumer spectro wrapper posts its supplied JSON to the analysis endpoint.
- `OfflineSampleScansAnalyzeWorker` requires network availability and delegates
  pending scans to server analysis. Its name is not evidence of an offline decoder.
- The firmware model Base64-decodes a response value, separates the first four
  checksum bytes, and exposes the remainder as file data. The update activity
  chunks those bytes for outbound FILE_DOWNLOAD. This corroborates the write
  direction; no update or firmware-read command was issued during this work.
- These traced wrappers do not establish where the opaque transform runs, nor
  exclude an untraced app/server/device path. The table search and source audit
  supply no new evidence-backed key or compression algorithm.
- Verification after these changes: **75 research tests pass with Python socket
  networking disabled**. Production/source-data hashes remain unchanged. The
  follow-up JSON reports contain no detected personal absolute paths. No device
  settings, firmware or physical connections were changed.
- Next concrete leads are the origin/scope of the observed self-response factor
  and non-additive dark handling, plus the still-untraced native paths. Do not
  assume `F(S,D)=decode(S)-decode(D)` or promote C to an absolute calibration table.

### Confirmed device connection

- SCIO was initially absent, then the user connected it over USB. It enumerated
  with VID:PID `0451:16AA` on COM5 and answered identification queries.
- Firmware is still 147. File sizes, versions and checksums match the earlier
  metadata; they are not firmware bytes or proof of the checksum algorithm.
- `READ_BLE` timed out; `READ_BLE_STATUS` returned `000000001004`. No interpretation
  beyond raw status bytes is established. Do not promote these bytes to key material.
- No parameter, firmware, calibration or protection writes were performed.
- Reproduction: `scripts/read_usb_evidence.py --output dev/analysis_output/<fresh>/usb.json`.
  Evidence: [USB metadata](analysis_output/recovery_20261003_followup/usb_metadata.json).
  After the user confirmed placement in the calibration cap and woke the unit,
  six captures succeeded; see the fresh-reference campaign below.

### Unknown-polynomial CRC test

- Implemented `scio_offline/crc_recovery.py` and `scripts/recover_crc.py`.
- This uses GF(2) polynomial GCDs of equal-length codeword differences. Fixed CRC
  initialization/finalization constants cancel, so the test does not guess a key,
  CRC polynomial or fixed device-specific seed.
- For each eligible device/generation/role group it tests 800 layouts: bounded
  prefixes/trailers, byte/bit order, and virtual placement of the second header word.
- Primary sample, dark and gradient groups each contain 97 distinct blobs. No
  degree-32-or-higher common polynomial was found in these layouts. Groups with
  fewer than four independent blobs are explicitly skipped, not called negative.
- Synthetic tests recover a CRC-32 with an unknown fixed XOR constant and reject
  random headers. Raw evidence: [unknown CRC](analysis_output/recovery_20261003_followup/unknown_crc.json).
- Limit: a CRC over unobserved decompressed plaintext, a variable seed, other
  coverage/layouts and nonlinear checksums remain possible. This is not evidence
  that encryption must exist.

### Support-export check

- Re-inspected `01_rawdata/app_researcher_output/SCIO_scans_from_tech_support.csv`
  read-only using the spreadsheet skill. Its 145 records explicitly contain three
  331-band sections: reflectance, `wr_raw`, and `sample_raw`, wavelengths 740–1070.
- Device ID is `E036D39ADE70A12D`, not the currently connected device. These are
  reference-stage examples, not paired plaintext for this unit's opaque blobs.
- Maximum absolute discrepancy in `sample_raw / wr_raw - spectrum` is about
  `9.76e-10`. This corroborates the existing ratio finding, not a new blob decode.
- There are 145 unique sample-domain vectors and 49 unique white-domain vectors.
  An exploratory SVD shows gradual singular-value decay, not an obvious sharp
  low-rank cutoff identifying a small fixed interpolation basis. No 24-knot or
  896-pixel assumption is justified by this check. The plotted Raw WR image is not
  independently digitized calibration truth.
- Reproducible statistics and column provenance are saved in
  [support-vector audit](analysis_output/recovery_20261003_followup/support_vectors.json).

### Unknown-seed non-cryptographic checksum test

- `recover_checksum_seed.py` inverts MurmurHash3-32, FNV-1, FNV-1a and DJB2 to
  recover the seed implied by each observed body/header pair. A fixed seed must
  agree across independent records; no dictionary or encryption key is assumed.
- 1,600 layouts per role × three eligible primary-device roles = 4,800 tested
  configurations. No fixed-seed screen match was found. White-reference groups
  with fewer than four distinct blobs were not tested as independent negatives.
- Four synthetic CRC/checksum tests pass, including the known Murmur3 `foo`
  vector, arbitrary seeds, non-word-aligned lengths and random-header rejection.
- Evidence: [seed recovery](analysis_output/recovery_20261003_followup/unknown_checksum_seed.json).
  This still says nothing about checksums of hidden decompressed plaintext.

### Fresh-reference campaign and current limits

- Initial cap-capture attempt stopped before sending commands because USB had
  disappeared. After the user woke the unit, all **six captures succeeded**, each
  status 0 and lengths dark/sample/gradient = 1800/1800/1656 bytes. Each scan was
  saved immediately, as well as in the completed batch
  [six cap scans](analysis_output/recovery_20261003_followup/usb_white_cap_six.json).
- Live BLE-ID metadata returned an empty i2s tag. Preserve that fact. The completed
  reference-spectrum request uses the uniquely documented historical tag for the
  same device and firmware, with explicit provenance. It does not edit captures.
- `pair_usb_captures.py` completed a distinct **eight-request reference campaign**:
  an unchanged historical control, six intact fresh scans using capture 0 as the
  white reference, and a final control. Minimum spacing remains 20 seconds. This
  is not a continuation of the already-completed 60-request mutation pilot.
- All eight requests returned HTTP 200, including both historical controls and
  all six fresh cap scans. The run completed without a control-failure halt.
  Responses and provenance are preserved in
  [fresh reference evidence](analysis_output/recovery_20261003_followup/fresh_reference/summary.json).
- The expanded research suite passed **67 tests**, with Python socket networking
  disabled (`scripts/test_without_network.py`). This verifies the implemented
  tests, not the existence of a working offline decoder.
- The unchanged production suite passed **35 tests**. Two initial invocations
  failed in temporary-directory setup (restricted default temp, then missing
  parent directory), not in application assertions. The successful run used a
  fresh directory under ignored `dev/tmp/`, with pytest caching disabled.
- Fresh spectra are reserved for prospective confirmation, not algorithm tuning.
  No offline transform is validated by collecting server-produced reference data.
- `verify_fresh_reference.py` verified all eight responses have 331 finite values
  on 740–1070 nm, matching controls at `atol=rtol=1e-6`, and a minimum request
  start gap of 20.947 seconds. All 18 fresh blobs have distinct hashes. This is
  **one shared acquisition/calibration group**, not six independent calibrations.
  The frozen [validation manifest](analysis_output/recovery_20261003_followup/fresh_reference_validation.json)
  records request/response hashes without inspecting or fitting fresh truth.
  Production/source-data hashes are unchanged from the initial campaign snapshot.
- The USB device was no longer enumerated after reference collection. No further
  device command was attempted. A next read-only metadata run will also preserve
  the raw BLE-ID response: an empty parsed tag alone cannot distinguish missing
  bytes from string-parser behavior. No production parser change is justified yet.
- Full Flutter AOT paths, codec/calibration tables and the opaque transform remain
  unrecovered. Do not describe software routes as exhausted or a decoder as solved.

### Next programmer actions

1. Keep the six fresh responses frozen until a candidate transform is fixed;
   validate amplitudes and per-band errors without fitting per-scan scales.
2. On a future USB session, inspect the saved raw BLE-ID field at bytes 66–129
   before interpreting the missing live i2s tag. The capture helper now preserves
   this response, but that additional query has not been exercised on hardware.
3. Continue the incomplete native/Dex control-flow audit for framing, transforms,
   firmware decoding and calibration tables. Neither checksum negatives nor
   random-looking bodies discriminate encryption from custom compression.
4. Original phone/cache/backup acquisition is unavailable per the user. Focus on
   supplied artifacts and separately planned device acquisition. File headers do
   not supply firmware contents; do not use host-to-device download operations as
   a read route. Hardware/debug access needs its own session.

### Historical Bluetooth logs (continuation)

- Added strict offline H4 btsnoop → ACL/L2CAP → ATT → SCIO frame reassembly.
  Three synthetic tests cover both fragmentation layers, sequence gaps, truncated
  records and exclusion of unrelated ATT values.
- The main supplied log contains 1,692 records, 1,349 ACL packets and four scan
  requests with twelve complete scan-response messages. No command `0x81`
  firmware transfer or BLE-ID response occurs in the reconstructed messages.
  The shorter prior log has 161 records and no ACL packets. There are no
  incomplete ACL/SCIO assemblies in either log. These logs do not supply firmware.
- The audit exports hashes/lengths rather than unrelated Bluetooth traffic or
  device names. Evidence: [Bluetooth audit](analysis_output/recovery_20261003_followup/bluetooth_audit.json).
  It does not rule out other phone logs, backups or cached firmware.
- A second immutable extraction preserves all twelve complete scan blobs with
  source-log hash and packet indices. All twelve are distinct and absent from the
  prior 325-blob manifest. Lengths repeat 1800/1800/1656 across four acquisitions.
  Identity, target, calibration association and processed truth are unestablished;
  do not silently add these to the primary device's key search or validation set.
  Evidence: [recovered historical blobs](analysis_output/recovery_20261003_followup/bluetooth_blobs_v2.json).

### Flutter snapshot triage and headerless image route

- `audit_flutter.py` reads the two native libraries directly from the supplied
  nested APKs, preserving hashes, ELF sections, five exported snapshot symbols
  per library and located relevant strings. It does not extract credentials.
  Evidence: [Flutter ELF inventory](analysis_output/recovery_20261003_followup/flutter_elf.json).
- Both libraries expose snapshot regions, not named SCIO decoding functions.
  JPEG/Huffman/EXR and encryption-related strings coexist with vendor strings;
  no call-site association establishes that these codecs or cryptographic
  routines process scans. Version 1.5.19 also contains gradient-preview/decoded-
  bytes labels; those names alone do not establish decompression or pixel layout.
- A bounded headerless baseline-JPEG entropy probe completed. It tests default
  luminance/chrominance Huffman tables with/without JPEG byte stuffing, six
  prefixes, four trailers and eight bit alignments. It requires complete block
  parsing and valid final padding, not spectral smoothness. Synthetic grayscale
  JPEGs pass through the actual probe with stripped headers and added envelopes.
  Custom tables, restarts, progressive/lossless/arithmetic JPEG remain untested.
- Completed sweep: 285 distinct paired-corpus blobs, 109,824 actual entropy
  decode attempts; 65 blobs admit at least one full parse (3,481 configurations).
  Random controls: 7/32 blobs admit a parse (432 configurations, 12,288 attempts).
  Blob-level acceptance is approximately 22.8% versus 21.9%; this descriptive
  comparison is not an independence-adjusted statistical test or an exclusion.
  Of the real-data hits, 3,433 use no stuffing and 48 use JPEG stuffing rules;
  output lengths span 519–672 DCT blocks. The most recurrent configuration parses
  only 23/285 blobs. No geometry, quantization, sample values or wavelength mapping
  is recovered. **Syntactic Huffman parsing is not a validated intermediate.**
  Evidence: [headerless JPEG sweep](analysis_output/recovery_20261003_followup/jpeg_entropy.json).
- The expanded research suite passes **73 tests**, with Python socket networking
  disabled. Two slow JPEG sweeps were stopped before they wrote results;
  the sweep was restarted using an integer-based bit reader and compiled Huffman
  lookups. All three JPEG tests pass again with this final implementation. Do not
  count stopped runs as additional completed searches or bounded negatives.

### Intact-combination prediction and authorized live run

- `probe_separability.py` constructs six requests: historical control, intact
  sample+white and sample+white-dark combinations, white+white-dark, all three,
  and final historical control. No fresh holdout spectra are used.
- If sample and white domains separate multiplicatively, a combined response
  should equal the product of the two corresponding single-substitution responses
  divided by the baseline. Predictions are frozen before sending; the three-way
  prediction additionally uses the white+white-dark response. No per-scan fit.
- The runner now stops immediately if the initial historical control has drifted
  from saved truth. Existing rate limits and serial spacing remain unchanged.
  A mocked-transport test verifies that drift sends only the control and prevents
  the next job. Seven targeted tests (guard, JPEG, Bluetooth) pass after these edits;
  the preceding full network-disabled suite had 73 passing tests.
- Execution was rejected by the approval check before process launch because
  these historical raw payloads would be sent to an external endpoint. **Zero
  requests were sent.** Explicit user permission for this transfer is required;
  do not work around the rejection. The offline-only plan and predictions are in
  [separability plan](analysis_output/recovery_20261003_followup/separability_plan/plan.json).
- Agreement would constrain the spectral calculation, not recover the opaque
  vectors or fix their absolute scale. This is not another ciphertext mutation sweep.
- Subsequent explicit user approval authorized the six planned historical-scan
  requests to the existing analysis endpoint, with 20-second spacing. The live run
  completed in `recovery_20261003_followup/separability_live`: **six HTTP 200
  responses**, each 331 finite bands on 740–1070 nm, and both controls match the
  historical spectrum. Predictions are identical to the saved pre-approval plan.
- Minimum measured request-start gap: **21.283 seconds**. The timer waits 20 seconds
  after response handling; the saved response timestamp is recorded slightly
  later during file serialization (minimum saved finish-to-start gap 19.992 s).
  All request-start gaps exceed the user's required 20 seconds. No further requests
  were sent. The mocked historical-control stop test also passes.
- All three predicted combinations match all 331 bands with no fitted scaling:
  sample+white max absolute error `3.3306690738754696e-16`; sample+white-dark
  `2.220446049250313e-16`; all three `4.440892098500626e-16`. Each also passes
  the stricter `atol=rtol=1e-10` comparison. Full per-band residuals, hashes and
  timing evidence are in [verification](analysis_output/recovery_20261003_followup/separability_live/verification.json).

#### What the composition result establishes and does not establish

For the two tested sample choices (sample dark held fixed) and four combinations
of white/white-dark, the eight available spectra form a multiplicatively separable
2×4 response table at every wavelength. The tested identity is
`R(S1,W1) = R(S1,W0) * R(S0,W1) / R(S0,W0)`; white-dark variations obey it too.
Here `W` means the complete selected white-side configuration, not the gradient.
The all-three prediction uses the measured white+white-dark response as declared
before the run; only the first two predictions were entirely numerical in advance.

This strongly supports independent sample-side and white-side processing for these
inputs and fixed metadata. It does not prove a particular internal order, dark
subtraction, physical units, or a direct unmodified ratio rather than another
multiplicatively separable function. Cross-band processing inside either domain is
not excluded. Absolute domain values remain unidentified: per-band common scaling
can leave every ratio unchanged. No blob intermediate, key, compression format or
offline decoder has been recovered by this test.

Next decoding work should use the cross-configuration consistency as an additional
candidate check, alongside absolute spectral errors and held-out confirmation.
Do not mislabel server-derived relative response factors as decoded domain vectors.

This document supersedes interpretive claims in older research reports; the
original results are preserved. No offline decoder or absolute sample/white
vectors have yet been established.

## Evidence ledger

| Prior claim | Classification | Actual evidence and limitation |
|---|---|---|
| Identifier keys excluded by dark rescreen | Invalidated by implementation | `scripts/rescreen_dark.py` fed the 8-byte header into the cipher and derived IVs from zeros. It now dispatches to `rescreen_v2.py`. Synthetic known-key fixtures exercise the replacement driver. |
| First ciphertext block tested as embedded IV | Invalidated by implementation | Passing IV bytes discarded the instruction to remove the embedded block. Fixed in `plaintext_oracles.screen_key`; explicit framing in `search_v2`. |
| Random-key cutoff controls extreme-tail familywise errors | Invalidated statistical claim | Hundreds of random keys cannot measure that tail. New runs store the empirical distribution and resolution, without familywise guarantees. |
| Bad_sample_signature proves a MAC, two secrets, or no global key | Untested | It identifies request rejection only. Existing ciphertext-oracle reports cover selected mutations, not all regions or roles. |
| Device binding proves per-device encryption keys | Untested | Wrong-device rejection is compatible with calibration lookup, signatures, packing versions, and several other mechanisms. |
| Lack of PKCS padding excludes encryption | Bounded negative | Fixed-length, stream, counter, explicit-length and layered formats need not use PKCS padding. |
| Firmware unavailable by software | Bounded negative | Earlier endpoint/device-file probes did not retrieve a validated executable. They do not exhaust phone caches, backups, older packages, encoded arrays or all firmware generations. |
| Server processing order established by HTTP errors | Untested | Errors do not locate checks within the implementation. |
| Entire transform is on BF512 | Untested | Local patent suggests DSP compression followed by communication-circuit encryption; actual firmware may differ. Include CC2540 in a future acquisition session. |
| High correlation establishes decoding | Invalid acceptance criterion | Wrong amplitude can correlate perfectly. New gate compares all 331 finite bands and exact wavelength axis, without per-scan rescaling. |
| All APKs/architectures already searched | Incomplete | New archive/member hashes and native/Dex string coverage are reproducible. String inspection is not complete native or Dex control-flow analysis. |
| Standard image codecs excluded | Overstated bounded negative | Original decoder sweep covered 40 bodies and offsets 0–32; byte-stuffing on opaque bodies cannot exclude encrypted JPEG, headerless/custom codecs, omitted tables or transformed bytes. The corrected search tests real image decoders after candidate decryption and after generic decompression. |

## Reproducible tools

Run from the repository root using the `tp` environment, with bytecode writes
disabled and `PYTHONPATH` containing `src` and `dev`. Choose a fresh output path:

```text
python dev/scripts/audit_recovery.py --apps <local-app-material-directory> --output dev/analysis_output/<new-run>
python dev/scripts/rescreen_v2.py --extended --output dev/analysis_output/<new-run>/key_search.json
python dev/scripts/compression_only.py --output dev/analysis_output/<new-run>/compression_only.json
python dev/scripts/oracle_v2.py --output dev/analysis_output/<new-run>/oracle --live
python -m pytest tests -o cache_dir=dev/.pytest_cache
python -m pytest dev/tests -o cache_dir=dev/.pytest_cache
python dev/scripts/test_without_network.py
```

Without `--live`, the oracle only saves a plan. Existing output paths are never
overwritten. A failed run is not silently resumed. Review its halt and request
count before explicitly starting another campaign. The live runner logs requests
before transmission, excludes authentication headers, uses 20-second minimum
spacing and stops on a failed control, authentication/rate-limit response, or two
consecutive server/transport errors. Its current plan fits within 60 requests.

`scio_offline.research.DecodeInput` requires device/generation metadata and accepts
calibration artifacts. `DecodeResult` distinguishes intermediate data, domain
vectors and reflectance. It is an interface, not a pretend implementation of an
unknown transform. Numerical agreement alone still cannot exclude memorization.

The retrospective split groups acquisitions and shared white references. All
existing data were previously inspected; new acquisitions are needed before
claiming genuinely unseen validation. Foreign generations must be evaluated
separately. Unknown calibration, wrong metadata, swapped roles and shuffled input
must be rejected by any future candidate before it can be called a decoder.

### Image-compression route

The search now attempts marker-guided JPEG, JPEG 2000, PNG, TIFF, GIF and WebP
decoding at every matching offset in candidate plaintext. It also checks images
inside successful deflate/zlib/gzip outputs. A synthetic JPEG behind a wrapper and
AES-CBC is recovered through the actual search driver with changing headers.
This verifies the harness, not the real SCIO transform.

Headerless JPEG needs supported dimensions, Huffman and quantization tables,
component layout and scan parameters. Inventing those until something draws a
picture is not sufficient. Search relevant firmware/app constants for those
tables, then require valid stream termination, consistent geometry across scans,
and numerical agreement after independently recovered calibration/binning. A
proprietary DCT or wavelet representation remains a separate hypothesis. An image
decode, if found, would be the intermediate milestone, not automatically a
331-band spectrum.

## Firmware acquisition handoff

### App trace established in the 2017 researcher source

Paths below are relative to that decompiled tree's `sources/com/consumerphysics`:

- `android/sdk/sciosdk/ScioInternalDevice.java:1088–1100`: response commands
  become dark/sample/gradient Base64 strings; sample status is separately read
  from the first word. This path does not numerically decode the opaque body.
- `android/scioconnection/protocol/ResponseCommand.java:43`: direct Base64
  encoding of received bytes, rather than a spectral transformation.
- `android/common/model/FirmwareUpgradeModel.java:33–43`: Base64 decoding,
  four-byte prefix separation, and intact firmware data after that prefix.
- `android/sdk/config/ScioDevicePreferences.java:395–408`: file-version JSON
  metadata under `ScioFirmwareFiles`, **not firmware bodies** (corrected by the
  container audit above).
- `researcher/activities/FirmwareUpgradeActivity.java:436–475`: successful
  completion clears the file-name index; bare-name payload strings are not
  removed by that routine. Transfer reads body and checksum separately,
  interpreting the latter little-endian.
- `common/serverapi/CommonServerAPI.java:350–358`: firmware requests use
  compression-version metadata and a separate binning-table-checksum request.

This trace is not a proof about every app version or firmware implementation.
The two Flutter builds require AOT control-flow work beyond the saved strings.
The 1.5.6 bundled environment files name notification/analytics credentials, not
evidence-linked scan keys; their values were neither printed nor exported.

The original phone and its backups are unavailable (confirmed by the user).
For any independently supplied future cache artifact, seek bare enum-name strings
and the per-user `firmware.file.names` index. `ScioFirmwareFiles` supplies version
metadata only; do not request the missing historical backup again.
The reviewed Java `FirmwareUpgradeModel` decodes Base64 and
separates a four-byte checksum prefix from the bytes transferred to the device.
Preserve the complete encoded value and raw prefix; do not discard it based on an
assumed checksum algorithm. Preserve app version, device/generation association,
timestamps and file hashes. Seek calibration/binning tables as well as `dsp_op`,
`dsp_boot`, `dsp_dec` and BLE firmware.

Verify exact lengths, internal structure, executable architecture, load ranges,
and checksum algorithm against independent evidence. A size match, cipher table
or filename is not validation. Decompile verified images to trace acquisition →
packing/compression → transport and recover table references and any key inputs.
Then implement that exact chain behind the metadata-aware interface and test it
against the frozen paired corpus. Absolute sample and white vectors need their
own intermediate truth or independently supported calibration calculation.

If caches do not provide these artifacts, prepare a separate read-only hardware
session covering external storage, BF512 and CC2540. Physical opening, electrical
connections, debug access, writes and protection changes are outside this session.
