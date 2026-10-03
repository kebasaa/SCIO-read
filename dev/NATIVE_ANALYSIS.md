# Local Flutter analysis setup and evidence rules

## Target and purpose

Analyze the supplied SCiO Analyzer 1.5.6 ARM64 app with its matching Dart 3.7.2
runtime. Resolve object-pool strings to annotated native functions and trace:

1. Capture buffers to request serialization: Base64/framing versus numerical decode.
2. Calibration and wavelength tables: their consumers, types and device scope.
3. Firmware responses and transfer: content decoding versus opaque pass-through.

This is static local analysis. No SCIO binary or data is uploaded. No app, Frida
script, firmware update, device reset or other device operation is executed.
The supplied 1.5.19 build is ARM32 and is not covered by this ARM64 tool run.

## Tools and provenance

- [Blutter](https://github.com/worawit/blutter), commit
  `4a60ac648bf448c5a7596437243bcd0b9376fdf0`.
- Matching [Dart runtime source](https://github.com/dart-lang/sdk), tag `3.7.2`.
- Existing Ubuntu GCC 13.3/CMake via WSL, not MinGW. Existing Visual Studio 18.9
  was confirmed through vswhere as a fallback; no compiler was installed.
- Ubuntu package dependencies unpacked into `dev/private/native_prefix`, not
  installed system-wide: ICU 74.2, Capstone 4.0.2, Ninja 1.11.1, pkgconf 1.8.1,
  pyelftools 0.30 and their associated runtime packages.

[Toolchain manifest](analysis_output/recovery_20261003_followup/native_toolchain.json)
records source revisions, downloaded package SHA-256 hashes and modified tool
script hashes. [Target manifest](analysis_output/recovery_20261003_followup/flutter_target.json)
records source archive and extracted library hashes. These manifests do not
claim that compilation or native interpretation has succeeded.

## Reproduction

Keep all downloaded source, dependencies, build files and full native dumps under
the Git-ignored `dev/private`. Verify the ignore rule before generating dumps:
constant pools can contain credentials, endpoint configuration and build paths.

1. Clone the pinned Blutter source into `dev/private/blutter`.
2. From the clean pinned tool checkout apply
   `git apply --ignore-space-change ../../scripts/blutter_native_export.patch`.
   It bounds Ninja to two jobs, prevents case-colliding assembly filenames, and
   includes the synthetic native library/top class in analysis and export.
   Synthetic functions use address-only headers rather than dereferencing absent
   Function metadata. Reverse `--check` with the same whitespace option verified
   that the recorded patch matches the modified sources.
3. Run `prepare_flutter_target.py --apps <local-app-root> --output <new-dev-report>`.
   It extracts only ARM64 libapp.so/libflutter.so from the supplied 1.5.6 XAPK
   and validates an existing extraction before reuse.
4. In Ubuntu, run `bash dev/scripts/setup_native_tools.sh`. It uses `apt-get
   download` and `dpkg-deb -x`, not `apt install`. Package indexes must already
   offer the required packages; package versions can change, so preserve hashes.
5. Run `bash dev/scripts/run_blutter_local.sh`. It sets a private dependency
   search path and builds against the detected Dart version. Output directory:
   `dev/private/flutter_1_5_6_analysis_native_v3`. The wrapper forces a Blutter
   rebuild to include the fixes; existing Dart build products are reusable.
   The initial unsuffixed dump is retained but must not support absence claims.
6. Record a new toolchain manifest if dependencies, source revisions or local
   tool patches change. Never overwrite older evidence reports.

Do not run the unrelated WorldForge build script supplied as a compiler-location
example. It describes an available MSVC setup, not work authorized for that project.

## Interpretation and reporting

- Wait for successful completion before calling a native dump complete.
- A string hit, method name or parser acceptance is not proof of a payload codec.
- Annotated call paths must connect opaque SCIO buffers to transformations.
- Generic JPEG, crypto, archive and image packages can serve unrelated app UI.
- Preserve function addresses, relevant instruction/call observations and input
  binary hashes in sanitized reports under `dev/analysis_output`.
- Do not publish full object pools or arbitrary constant values. Do not promote
  account credentials, Android package signatures or SDK snapshot hashes to
  device-key candidates without a code-connected reason.
- Finding a transform is still only a lead: implement it independently and test
  full numerical equivalence on the paired corpus with its frozen confirmation
  partition. Do not use native-tool output as a spectrum by itself.

Current progress and findings belong in [RECOVERY_STATUS.md](RECOVERY_STATUS.md).

## Completed runs and remaining coverage gaps

Both builds and the collision-safe analysis completed successfully. The latter
produced 1,676 assembly files (original case-colliding output: 977). This is not
a complete payload dataflow recovery. Known scan-field strings appear in the
object pool but not the emitted assembly. Upstream stores some obfuscated
functions separately in `nativeLib.topClass`; the normal library dump does not
walk that synthetic class. The v3 patch now includes these functions, and exposes
the request builder at `0xa0a09c`. Two failed intermediate outputs are retained
(`_native` and `_native_v2`); neither supports completeness claims. V3 completed
with leaf-runtime IL warnings, so instruction-level checking remains necessary.

Many called code addresses still have no exported body. Use
`scripts/scan_native_pool_refs.py` for a bounded instruction-pattern search over
ELF executable segments, and `scripts/disassemble_arm64_local.py` under WSL for
bounded raw ranges using the existing private Capstone library. Ranges are not
automatically function boundaries. Only direct PP loads and adjacent ADD/LDR
pairs are annotated; dynamic dispatch and general register dataflow are unresolved.
Raw output is restricted to `dev/private` and created exclusively.

Reviewed paths and the allowlisted embedded fixture are recorded by
`scripts/record_flutter_findings.py` in
[Flutter dataflow](analysis_output/recovery_20261003_followup/flutter_dataflow.json).
The native-tool patch and latest source hashes are separate from this evidence:
[toolchain](analysis_output/recovery_20261003_followup/native_toolchain_synthetic.json).
The fixture has no associated device identity or spectral truth and must not
be used as a validation spectrum. Its raw triplet was absent from the canonical
manifest at extraction time.

## Exact-APK Android bridge follow-up

[JADX 1.5.6](https://github.com/skylot/jadx/releases/tag/v1.5.6) was downloaded
from the official release and unpacked into `dev/private/jadx-1.5.6`. Archive
SHA-256: `545ea2be9c242511bc145755cf4bda2485ade42966e096f8b4d3da2a230e8974`.
Uses existing Java 17; tool version happens to equal app version but is unrelated.
No extra plugins or analyzed-app execution.

`prepare_modern_dex.py --apps <local-app-root> --output <new-dev-report>` extracts
four DEX inputs from the exact XAPK. `run_jadx_local.ps1` uses two threads, disables
resource extraction/config loading, and confines cache/temp/source output to
private paths. It refuses to overwrite an existing output directory.

Full decompilation completed with exit 1 and 161 reported errors. Relevant SCIO
methods were reviewed separately; status-copy omission also checked with
`--decompilation-mode fallback --single-class com.consumerphysics.android.sdk.model.ScioReading`
against `input_1.dex`, writing to the private `_fallback` directory. That run
exited 0. Decompiled files can contain personal source paths and app constants;
keep them ignored. Reports contain curated anchors, relative class paths and hashes.

`audit_modern_bridge.py` validates reviewed anchors, hashes sources, checks the
fallback constructor, and inventories mock assets without publishing full code.
See [17 observations](analysis_output/recovery_20261003_followup/modern_bridge_v2.json).
The inspected chain preserves opaque bytes into Flutter; the response-side
numeric-list parser is only partially traced. This is not an offline decoder.

## ARM32 1.5.19 and Lab Toolkit follow-up

`prepare_arm32_target.py` extracts the hash-pinned ARM32 library.
`probe_arm32_strings.py` is a narrow Dart 3.11.4 RO-string/object-pool probe,
not a complete deserializer. It uses 64-byte data-image alignment, 8-byte RO
allocation units, distinct little-endian varints versus big-endian reference
groups, and the ARM32 tagged PP convention. Private `pool_strings.json` can
contain sensitive constants; do not publish it. `trace_arm32_diagnostics.py`
scans adjacent ADD-from-r5/LDR instructions and can use existing WSL Capstone for
bounded private disassembly. It does not cover every pool-load construction.
The matching-format source hashes are in `app_followup.json`. An earlier-version
ARM assembler source was used as a lead; actual matching instruction bytes and
synthetic tests support the selected load pattern, not all ABI assumptions.

`prepare_additional_dex.py` inventories/extracts the exact 1.5.19 and Lab APKs.
The Lab two-DEX JADX run used the existing private tool with resources disabled,
two workers and private cache/temp/output directories. Exit 1, 84 errors over
5,084 classes: preserve partial output and use fallback for unresolved methods.
`audit_lab_fixtures.py` extracts only allowlisted mock assets/constants and records
hashes/headers without exporting raw decompiled files. `record_app_followup.py`
records 14 reviewed observations with source anchors. No compilers installed,
APKs executed, server requests sent, or device/reset operations performed.

### Validation producer continuation

`trace_arm32_diagnostics.py --callers 0xc75cac` now finds immediate ARM BL callers
with correct PC+8/sign extension; BLX/indirect calls are excluded. Binary hash is
checked before scanning/disassembly. `record_validation_trace.py` verifies 13
selected edges directly in ELF code and records reviewed findings. Dynamic
suffix construction (`_decoded_bytes`, etc.) is why full-label string-reference
search was insufficient. The traced decoder is Base64, not the opaque-body
transform. Exact string preparation/exception-type semantics remain incomplete;
do not present this static trace as runtime-equivalent emulation.

### Firmware text-container follow-up

`scio_offline.firmware_containers` recognizes named firmware candidates in JSON
and SharedPreferences XML while keeping `ScioFirmwareFiles` version metadata
separate. `find_firmware_containers.py` scans source data, supplied text resources
and top-level source ZIP members without extracting archives or exporting values.
Latest report is `firmware_containers_v2.json`; v1 had a narrower literal marker
filter. The zero-candidate result is limited to the recorded text formats and
size cap. `record_firmware_storage.py` hashes nine reviewed exact-Lab source
anchors, correcting the earlier cache description. No payload recovered.

### Binary resources and DEX arrays

`probe_embedded_resources.py` uses bounded gzip/zlib/bzip2/xz decoding, contiguous
Base64/hex extraction and explicit numeric Java arrays across supplied APKs and
vendor sources. Raw size-only or LDR candidates stay private. Reports record
signature caps and limits; do not confuse compressed PNG content or multimedia
libraries with a SCIO codec. `probe_dex_arrays.py` separately walks class_data to
actual code_items and finds bounded fill-array-data reference candidates; this
does not implement complete Dalvik instruction-boundary validation. Synthetic
tests cover bounds, negative references, malformed payloads and codec limits.
`firmware_recheck.py --live` is an explicit three-GET known-endpoint recheck,
with stop-on-error/no redirects/no installation and private raw responses.
It uses historical metadata; current empty i2s is not silently replaced in USB
evidence. The latest scheduler cools down for 20 seconds after each response.
