# `dev/` - offline decoding (unresolved)

> **Start here:** [HANDOVER.md](HANDOVER.md) has the current state and ranked next
> tasks; the full chronological log is [RECOVERY_STATUS.md](RECOVERY_STATUS.md).
> This file was reconciled with both on 2026-10-04. Where an older measurement is
> kept below, its interpretation has been narrowed to what it actually shows.

Device IDs, command namespaces, file headers, and calibration-table evidence are
maintained in [DEVICE_FUNCTION_REFERENCE.md](DEVICE_FUNCTION_REFERENCE.md).

Everything here belongs to one question:

> **Can a SCiO scan be turned into a spectrum without the Consumer Physics server?**

This has **not yet been achieved**, and this directory records the experiments. It is kept
separate from `src/scio/` on purpose: the working pipeline must not depend on any
of it, and `pytest tests/` must pass with `dev/` deleted.

## The problem

A scan is three blobs (dark, sample, gradient - 1800/1800/1656 B on `-e`
firmware). Each is an 8-byte plaintext header (`u32` status/type, `u32` per-blob
value) followed by a body that is a multiple of 16 bytes and carries ~7.9 bits of
entropy per byte. The location and nature of the opaque transform remain unproven;
both the Blackfin DSP and BLE processor are relevant acquisition targets. The
device reports a `dsp_op` file of 32628 B, but file metadata is not firmware content.
No verified firmware-body read route has been recovered yet.

Nothing here has recovered a key, and no candidate decode has ever survived
validation against a stored server spectrum.

## Read this before forming a theory

**The transform's class is undetermined, and this directory spent years assuming
otherwise.** The assumption that the body is *encrypted* traces to one line in
`archive/more_info/IMPORTANT.txt:237` - "Indicates a 256-bit key using AptinaID" -
written against `ScioDevicePreferences.java`. The code it describes is:

```java
private String getKeyPerAptinaId(String str) {
    String aptinaId = getAptinaId();
    if (aptinaId == null) return str;
    return "***." + aptinaId + "." + str;
}
```

That is a **SharedPreferences key** - a string used to namespace a stored value
per device - not a cryptographic key. The misreading seeded both the project's
"the blobs are encrypted" framing and the AptinaId-as-AES-256 hypothesis below.
Removing the basis for a claim is not the same as refuting it, so:

**The vendor's vocabulary hints at compression.** The vendor calls the i2s tag
`compression_version`; in the un-obfuscated 2017 researcher build the parameter
carrying that value is literally named `i2sTag`, passed in the same call as the
four binning-table checksums; and the app ships an `UnsupportedCompressionConversion`
error string. You cannot convert between encryptions; you can re-bin between
binning tables. The gradient blob's length also changes with the generation
(1656 B on `-e`, 1416 B on `-o`) while the sample's does not.

**But a plain fixed-position coder is now disfavoured.** A supervised test on the
92 paired records ([leakage](analysis_output/leakage_20261003/leakage.json)) finds
no body bit, byte or 16-bit word correlated with the returned spectrum and no
held-out linear predictor, although the same detectors find a single fixed-position
count field in synthetic fixtures of this size. That leaves encryption under a
fresh nonce, or a coder whose fields shift position, as the live options.

**Encryption is neither confirmed nor excluded by software.** The device
could encrypt and the server decrypt. The Android client is a verified
byte-for-byte pass-through - BLE frames to `Base64.encodeToString` to JSON to
POST, with no arithmetic on the bytes anywhere - so it would contain no crypto
*either way*. A sweep for crypto primitives across all eight decompiled trees
(~1,500 files) finds none, but that only rules out **client-side** crypto, which
nobody proposed. Absence of evidence is close to worthless here.

The asymmetry that follows governs how to report results: **a compression hit
would be decisive; a compression miss is not.** Nothing in this directory may
conclude "therefore it is encrypted" - only "compression not demonstrated", with
the coverage of the test that missed.

## Measured facts about the corpus (97 scans, 300 unique bodies)

Established this session, so nobody re-measures them:

- **No reuse of the second header word anywhere.** 300 unique bodies map
  one-to-one onto 300 unique values. The nine apparent collisions are the three
  white references stored in 19/24/54 records each. Differential attacks that need
  a repeated nonce have no foothold.
- **That word looks like a fresh 32-bit random draw per blob** - not a counter
  (18/29 ascending in a burst 2.13 s apart), not time-correlated (|r| <= 0.11),
  not derived from the body (0/291 across eight checksum candidates), three
  independent draws per scan.
- **Full avalanche on real near-identical input.** Thirty captures of one
  unchanged target, spectra agreeing to 2.1 % worst case, give bodies at 0.49986
  bit distance with 1/256 byte agreement and zero shared 16-byte blocks.
  **Do not over-read this.** It is *not* evidence for encryption over compression:
  the 2.1 % is measured after binning ~2.7 pixels per band, per-pixel noise differs
  everywhere, and entropy coders avalanche on any input difference.
- **No positional structure at all.** Zero of 1792 byte offsets deviate >4 sigma
  from uniform; the pooled histogram is flat at chi-square 256.9 on df 255. This
  refutes any *plaintext* array layout, including the `400 x u32 + trailer`
  hypothesis in `archive/more_info/old_code.txt`.
- Two arithmetic premises were wrong and are corrected: 1792 bytes is **not** a
  whole number of 12-bit words (1194.667), and `nPixelsPerBin` at 1166 B **cannot**
  hold 331 fixed-width per-band counts - 331 is prime and does not divide 1166.

## What the transform looks like (2026-09-11)

Three measurements, each from a different direction, agree. Raw numbers in
`dev/analysis_output/transform_class.json` and `compression_sweep.json`.

**1. Output length never depends on content.** Across 97 captures of dark frames,
a white calibration box, bark, soil crust, skin, rock and a hand, the sample body
is *always exactly* 1792 B, the dark body 1792, the gradient 1648. Not one byte of
variation. This shows the **container** is fixed-size, not that the coding is
fixed-rate: a variable-length stream can be written into a fixed buffer and the
remainder filled (see "no visible padding" below for what that filling would have
to look like). `transform_class` schema 2 carries this correction.

**2. Scene information content leaves no trace.** Mean body entropy by scene:
dark 7.8980, calibration box 7.8937, static series 7.8933, everything else 7.8951
bits/byte - a spread of **0.0046**. A dark frame carries far less information than
a lit scene and comes out indistinguishable.

**3. There is no coder header.** The first 8/16/32/64 bytes sit at 96-99 % of the
entropy ceiling for their length, against a tail of 7.89. A container magic, a
Huffman table or a coder preamble would all show a low-entropy head. None does.

**4. Eight known codecs, 633,600 trials, nothing.** Raw DEFLATE, zlib, gzip, bz2,
lzma (auto and raw), brotli and RLE, at every byte offset 0-32 **and** every bit
offset 0-7, keeping the partial output a truncated-but-real stream still emits,
across all 300 unique bodies: **zero plausible decodes**, zero corroborated.

The harness was proven in both directions first - it recovers real compression at
byte offset 7 and at bit offset 3, and stays silent on random input - so this
negative means something. Its stated limit still holds: a proprietary range or
arithmetic coder emits a headerless stream indistinguishable from random and no
sweep over standard formats would find it.

**5. Not a plain JPEG-family stream.** The sensor is an imager (the teardown shows
12 filtered receptors over one photodiode array), so a small compressed frame is a
natural guess. A test that needs no decoder: entropy-coded image formats must **byte-stuff**
so a raw `0xFF` cannot be read as a marker, and the rule holds over the
entropy-coded segment itself, **with or without a container**. That matters
because an embedded coder would strip the header, producing a stream no decoder
would accept.

| rule | required if true | corpus | random |
|---|---|---|---|
| JPEG: byte after `0xFF` is `0x00` or a marker | ~1.0 | **0.0350** | 0.0430 |
| JPEG-LS: byte after `0xFF` is `< 0x80` | ~1.0 | **0.4995** | 0.5000 |
| JPEG 2000 (MQ): byte after `0xFF` is `<= 0x8F` | ~1.0 | **0.5659** | 0.5625 |

Every rate sits on its random baseline. The detector was verified against a real
JPEG first: a full file scores 0.60, and a **headerless entropy-coded segment -
exactly the embedded-coder case - scores 1.0000**. This excludes an *untransformed*
JPEG, JPEG-LS or JPEG 2000 entropy stream. It does not exclude one that is
encrypted or otherwise byte-transformed afterwards, a coder that does not
byte-stuff, or a proprietary DCT/wavelet scheme. A separate headerless baseline-JPEG
Huffman parse ([jpeg_entropy](analysis_output/recovery_20261003_followup/jpeg_entropy.json))
accepts real bodies at about the same rate as random controls.

Alongside that: no container magic (JPEG/PNG/GIF/BMP/TIFF/WebP/JP2/ZIP/RAR/7z)
appears above chance **at any offset** - the earlier check only tested offset 0 -
and PIL accepts nothing in 1,320 decode attempts across 40 bodies × 33 offsets.
An image wrapped in a generic compressor is covered by point 4: the wrapper would
have to decompress first, and none did.

**There is also no visible padding.** If the fixed 1792 B were a buffer holding a
shorter variable-length stream with constant fill, the slack would show. Head and
tail entropy match to three decimal places at every prefix length, and the longest
constant-byte run in 300 bodies is **3**, near the random expectation of 2.35. That
excludes zero or constant padding; random or encrypted fill would not show.

**Conclusion: fixed-size, whitened, positionally featureless, header-free, with no
constant padding and no untransformed JPEG-family stream.** That is consistent with
encryption *and* with a proprietary coder whose output fills the container. The
supervised leakage test (above) narrows the coder option to one without
fixed-position fields. The verdict stays `undetermined`.

The blind spot is the same in both sweeps: a proprietary DCT or wavelet coder that
does not byte-stuff emits a headerless stream indistinguishable from random, and
neither the codec sweep nor the stuffing test would see it.

What would actually settle it: the firmware (`dsp_op` and friends, or the CC2540
image) via a hardware read, or the four binning tables. The live
`/v1/external_sdk/intermediate_scan` route (401 on POST) was once listed here; a
2026-10-04 trace indicates "intermediate scan" means a member scan of a multi-scan
batch, not partially decoded data
([sdk endpoints](analysis_output/sdk_endpoints_20261004/sdk_endpoints.json)).

## Findings from the 2026-09-30 investigation

What was looked at, what was found, and what **not** to redo. Raw material is in
`dev/analysis_output/` (`ciphertext_oracle/`, `new_host_probe.json`).

### Corrections to earlier statements

1. **"No shared ciphertext blocks" does not exclude ECB or fixed-IV CBC.** Sensor noise makes
   every plaintext block unique, so an ECB body would show no repeats either. Only a
   chosen-ciphertext probe can separate them (see below).
2. **The first header word is a *type/status* word.** The vendor's un-obfuscated 2017 source
   names it `status` for the sample blob (`ScioInternalDevice.java:1085`, little-endian, which
   is the house byte order). A constant `110` on gradients looks like a type tag, not a status.
3. **"896 x u16" is a hypothesis from sizes, not a measurement**: 1792 = 896x2, 1648 = 824x2,
   and the `-o` gradient 1408 = 704x2. Nothing measured confirms a width or a layout.
4. **Consumer `spectro-scan` accepts a synthetic MAC and no GPS**, so neither is key material.

### Closed: nothing returns raw band intensities

Every app response is the reflectance ratio. The `sample_raw` / `wr_raw` columns in the
tech-support CSV come from a web export on the `lab.` host, belong to a *different* device
(`E036D39ADE70A12D`), and are non-integer floats - so they say nothing about plaintext bit
width. There is no `*_raw` field anywhere in any decompiled parser. The un-obfuscated
2017 researcher tree (`com.consumerphysics.researcher_2017-09-19_source_from_JADX`) is the
canonical reference for endpoints and parameter names; the 2022/23 builds lost them to
obfuscation.

### Closed: the firmware is not on this machine

60,157 files and 68,809 archive members under the decompilation folder (apk, xapk, zip, nested
three deep), and 371,229 files outside it, were matched by **exact size** (each of the eight
known sizes, +4, +8, and base64 lengths - including the 96 B and 140 B tables that an earlier
"no run >= 600 chars" search would have missed), by checksum prefix, by Blackfin LDR signature
and by toolchain strings. Zero real hits: every size match is coincidental (PNGs, XML,
timezone files). The Flutter app's `libapp.so` has none of the firmware strings; its Java layer
has only the file *names*, never payloads.

### Closed: the newest app's backend is the same service

The newest (Flutter) app talks to `api.scionir.com` / `auth.scionir.com`. Those, and
`api.consumerphysics.com` and `lab.consumerphysics.com`, **all resolve to 35.229.97.127 and answer
identically** (`401 {"message":null}` for the two version/rollout endpoints, `404` for `/`). It is
one backend under several names, so the firmware-store result below applies to all of them. No credential was sent to any scionir.com host. (`dev.scionir.com` is a separate AWS
address and looks like a content site; not pursued.) Our token is refused at
`GET /v1/configuration` (401): it lacks the collection/SDK scope.

### Extra ciphertext that exists but is not usable as truth

The apps embed real scan blobs from **four other devices and older generations**
(`ScioMockDevice`, `FakeJson`): tags `20150812`, `20150812-o`, `20150712`; gradient body
**1408 B**; none of their second words occurs in our corpus. They are ciphertext only - the
bundled "results" are hand-edited (a cheese and a white-chocolate spectrum are bit-identical
across different devices).

### Tried and CLOSED: the server as a chosen-ciphertext oracle (do not retry)

The idea was to change a blob, watch which spectrum bands move, and read the transform's
structure from outside. Had the transform been bit-malleable it would even have leaked
plaintext: the binning is non-negative and (W - Wd) positive, so the sign of a band's change
equals the sign of the plaintext change. `malleability.py` classifies the damage pattern and
was validated against a deliberately non-benign simulated server first (900+ runs, 540 on
held-out seeds, zero wrong labels), so a result would have meant something.

**It is closed by an integrity check on four of the six blobs.** Against a baseline whose
untouched control returns `200`, every tested change to the **second header word or the body**
of a sample, dark, white or white-dark blob - down to one flipped bit - returns
`400 {"error_type":"Bad_sample_signature"}` (8/8 in the pilot; the October campaign confirmed it
for all four roles, block boundaries and a sum/XOR-preserving byte swap). Two things are
**not** checked: the status bit in header word 0 can be changed in all six roles, and gradient
blobs can be mutated, zero-filled or omitted - in every case `200` with the spectrum exactly
unchanged ([RESULTS](analysis_output/recovery_20261003/RESULTS.md)). Whole unmodified blobs
pass (A0's white-swap of intact blobs returned `200`). No altered protected blob is ever decoded,
so there is no bit-flip oracle and no sign-of-delta plaintext route. **Do not send modified
blobs to the server.**

The error name does not establish what the check is (MAC, signature, checksum over hidden
plaintext, or a decode-time consistency test), nor the order in which the server applies it
relative to the physics-range check (`422 high_ambient`, found in A0).

A0 did establish, with valid inputs only, that `R` is separable into a sample-side and a
white-side factor (agreeing to 1e-15), that timestamps are inert and nothing is cached. Later
tests sharpened this: the table of intact sample/white combinations is multiplicatively
separable to ~1e-16, role swaps expose a stable non-unity factor C(λ), and dark handling is
*not* a simple subtraction (the additive identity fails on 321 of 331 bands), so do not read the
white side as literally `W - Wd`. See [HANDOVER.md](HANDOVER.md).

**A blob is rejected under a non-matching device_id.** The app-embedded mock blobs (real captures
from three other devices and older generations, in `FakeJson.java` / `assets/mock/`) all decode
natively when submitted unmodified under their own device_id + tag - `200`, 331 bands, generations
`20150812`, `-o` and `20150712` alike. But the *same* foreign blob under our device_id returns
`Bad_sample_signature`. So acceptance depends on the request's device_id matching the blob; a blob
only decodes under the identity that produced it, and the server holds or derives per-device
material for arbitrary devices. The mechanism is not isolated - a cryptographic device binding, a
per-device key, or rejection of the foreign content against the mismatched identity's calibration
are all consistent. (`dev/scripts/extract_mock_scans.py`, `ciphertext_oracle.py foreign`,
`FOREIGN_VERDICT.json`.)

**Why this matters beyond the dead end:** validity depends on the device_id the blob is
submitted under, so some per-device material exists on the server side (stored or derived).
That raises the prior that the payload is device-keyed rather than public compression, but it
is compatible with several designs: a per-device key, a global key with the device_id as a
tweak, a master key with per-device derivation, or a per-device calibration lookup that a
foreign blob fails. Whether the device holds one secret, two (transform and integrity) or
none of its own is not established. The class stays `undetermined`; the most informative
remaining route is the firmware, which needs a hardware read.

## Layout

```
dev/
  scio_offline/          the research modules (import as `scio_offline`)
  scripts/               CLI drivers; import `_bootstrap` first, which fixes sys.path + cwd
  notebooks/
    01_scio_evidence_pipeline.ipynb   corpus inventory + neutral transform statistics
    02_scio_keyrecovery.ipynb         the current key-recovery attempt
    superseded/                       earlier attempts, each labelled, kept as the record
  tests/                 pytest for this strand only
  analysis_output/       saved evidence, including live server/device runs that cannot be
                         regenerated - treat as append-only; write new runs to new paths
  HANDOVER.md            current state and ranked next tasks (keep it current)
  RECOVERY_STATUS.md     chronological research log
  DEVICE_FUNCTION_REFERENCE.md, NATIVE_ANALYSIS.md   device facts; native-tooling notes
```

The root notebooks (`01`-`03`) deliberately import **only** `scio`, never
`scio_offline` - the same separation `pytest tests/` enforces for the code.

Modules:

| module | what it does |
|---|---|
| `decode` | candidate transforms (AES modes, IV schemes), spectral normalisation |
| `keyrecover` | bounded key hypotheses from firmware constants, serials, ids, version tags - **no key-space brute forcing** |
| `firmware` | extract/triage DSP firmware + calibration tables from a phone's SharedPreferences or an adb backup |
| `flashdump` | carve blobs out of an external SPI-flash image |
| `evidence` | hypothesis-neutral statistics over every local capture |
| `image_hypothesis` | is the body a raster frame? (negative) |
| `image_codec_hypothesis` | is the body a *compressed* image? Byte-stuffing statistics test the whole JPEG family at once, headerless variants included (negative) |
| `stream_hypothesis` | weak stream cipher / PRNG tests (negative) |
| `embedded_cipher_hypothesis` | look for cipher signatures embedded in firmware |
| `repeatability` | cross-capture screening: does a candidate key give *consistent* plaintext? |
| `pipeline` | the guard - refuses to export a spectrum from an unvalidated decode |
| `compression_hypothesis` | known codecs at every byte **and bit** offset, with partial-output tolerance; screens each codec against random input first and excludes any that "finds" structure in noise |
| `malleability` / `malleability_sim` | **chosen-ciphertext probing of the live server**: flip a bit in a blob, read which bands move. The classifier separates stream / block-transform / delta / ECB / CBC-CFB / adaptive-coder and can answer `undetermined`, but has no label meaning "encryption excluded". Validated against a simulated server, not the real one |
| `transform_class` | what *class* of transform is this? Size-invariance, entropy-by-scene and coder-header tests, emitting a verdict that structurally cannot say "encryption ruled out" |
| `validation` | score a candidate decoder against all 92 records whose true spectrum we hold. Self-checked in both directions - truth must pass, noise must fail |
| `research` | auditable corpus contexts (white/acquisition groups), the metadata-aware `DecodeInput`/`DecodeResult` interface, and **the gate** `numerical_check`: all 331 bands, exact axis, `atol=rtol=1e-6`, no rescaling |
| `search_v2` / `plaintext_oracles` | framing-correct bounded key searches with order-independent oracles (replace the flawed dark rescreen) |
| `compression_only` / `representation_codecs` | keyless codec probes, including word-swapped and bit-reversed representations |
| `jpeg_entropy` | headerless baseline-JPEG Huffman parse probe |
| `crc_recovery` / `seeded_checksum` | unknown-polynomial CRC and seeded non-cryptographic checksum recovery for the second header word |
| `leakage` | supervised test: do body bits/bytes/words carry information about the spectrum? (negative) |
| `response_models` | server-response hypotheses (separability, dark models), not blob decoders |
| `snoop` | offline btsnoop -> ACL -> ATT -> SCIO frame reassembly |
| `firmware_containers` / `resource_probe` / `native_index` / `arm64_refs` | bounded static scans of app archives, resources and AOT dumps for firmware/table material |

## Running it

```bash
python dev/scripts/test_without_network.py   # dev/tests with sockets blocked
python dev/scripts/analyze_scio.py           # neutral diagnostics over the corpus
python dev/scripts/probe_leakage.py --output dev/analysis_output/<new-run>/leakage.json
python dev/scripts/recover_key.py            # needs dsp_op, which we do not have
```

More drivers and their exact invocations are in
[RECOVERY_STATUS.md](RECOVERY_STATUS.md#reproducible-tools).

Scripts assume the repository root as their working directory; `_bootstrap`
enforces that, so they can be launched from anywhere.

## Why it stalled, and what would unstick it

The software and server routes tried so far are bounded negatives, not proofs of absence
(each is listed with its evidence in [HANDOVER.md](HANDOVER.md#do-not-repeat)):

- **The cloud** has returned no firmware through the upgrade endpoint: `new_version` was
  empty in every probe (2026-09) and in a 2026-10 recheck, and `needs_params_upgrade` stays
  false even for wrong checksums. Offers could be device- or account-dependent, so this is
  not proof that the store is gone. The newest app's `scionir.com` backend is the same server.
- **The server will not decode a modified protected blob** (`Bad_sample_signature`), so it
  cannot be turned into a decoding oracle, and a blob only decodes under its own device_id.
- **The APKs** cache firmware in SharedPreferences but ship none. Static traces of every
  supplied app (Java, Lab, Flutter ARM64 and ARM32 AOT) find only Base64 pass-through, and
  bounded archive/resource/DEX/container scans found no firmware body or table.
- **USB** has no known readback path (`0x87` returns 16 bytes; `0x81` is host->device only).
- **Identifier-derived keys** are negative under the corrected framing search and
  order-independent oracles.
- **Body statistics**, unsupervised and supervised, cannot separate encryption from a
  position-shifting coder.

What is left is a hardware read, and the full procedure with validation targets and safety
rules is in **`documentation/HARDWARE_ACQUISITION.md`**. In brief:

1. **Boot flash** (if external: ~$15 CH341A + SOIC-8 clip): `dsp_boot`/`dsp_dec`/`dsp_op` as
   stored, validated against this unit's header table (`dsp_op` 32628 B, checksum 4151168).
   First confirm from the teardown photos which chip it is, and whether the DSP is an `F`
   variant with in-package flash (HANDOVER task 1).
2. **BF512 JTAG**: halt mid-scan, read the key from L1 SRAM; may be OTP-disabled.
3. **CC2540** (the TI BLE/USB MCU that enumerates as `0451:16AA`, has hardware AES-128): the
   signature and possibly the transform may be applied *here*, not on the DSP - so identify
   what each chip holds before committing. Its debug port may be locked (do not erase to unlock).
4. **Another owner's cached firmware** - no hardware needed; `firmware.py` extracts it from a
   SharedPreferences dump or `adb backup`. Outreach text is in the hardware doc.

If the device does hold key material (for the transform, the integrity check, or both),
a firmware or memory read is the only known way to reach it.

## Closed avenue: the i2s tag is not a chosen-binning oracle

Tested 2026-09-10, `dev/scripts/i2s_tag_oracle.py`, results in
`dev/analysis_output/i2s_tag_oracle/`.

**The idea.** The i2s tag (`i2s_tag_config`, which the firmware endpoint calls
`compression_version`) selects the image-to-spectrum generation: which
`centers`/`bins`/`nPixelsPerBin` tables apply and which reconstruction algorithm
runs. The client never parses or validates it - it is an opaque 64-byte string
read from the device and passed straight through - so an arbitrary tag can be
sent with otherwise byte-identical blobs. If the server returned a *different*
spectrum for the same ciphertext under a different tag, each spectrum would be a
different projection of the same hidden pixel vector: overlapping binnings can be
subtracted against each other to recover finer detail, and in the limit per-pixel
plaintext. That would have been the first known-plaintext material this project
has ever had.

**It does not work.** One tag, one decode:

| tag | provenance | result |
|---|---|---|
| `20150812-e:PRODUCTION` | this device's own | **200**, 331-point spectrum |
| `20150812-o:PRODUCTION` | `ScioMockDevice`, consumer 1.3.8.554 / Lab 1.3.12.144 | 500 |
| `20150812:PRODUCTION` | `ScioMockDevice`, 1.1.0.320 / 1.2.6.476 / researcher 2017 | 500 |
| `20150712:PRODUCTION` | `FakeJson.FAKE_WHITE_CHOCOLATE_SCAN` - a different generation | 500 |
| `20150812-a:PRODUCTION` | invented probe | 500 |
| `20150812-E:PRODUCTION` | control-tag, letter upper-cased | 500 |
| `20150812-e:production` | control-tag, suffix lower-cased | 500 |
| `not-a-tag`, `` (empty) | malformed | 400 `InvalidUsage`, "not a valid i2s tag config" |

What that tells us, which is worth keeping even though the answer is no:

- **The server is bit-deterministic.** Two identical requests returned
  byte-identical spectra (`max|diff| = 0`). The noise floor is exactly zero, so
  any future differential experiment against this API has a clean baseline. The
  control also reproduced the spectrum the server returned for the same scan in
  2020 to `5.1e-15`.
- **Two distinct failure modes.** Malformed tags are rejected by a validator
  (400, specific message). Well-formed tags of another generation pass validation
  and then **crash the analysis** (500, generic "Server error"). So the tag is not
  checked against the device up front - it is used as an **exact-string key** into
  something that only exists for this device's own generation. Case-sensitivity
  confirms the literal-lookup reading: `-E` and `:production` both 500.
- **The generation letter is not a free parameter.** It behaves as part of a
  composite key, not a selector the caller can steer.

**The firmware endpoint gave nothing either.** `GET /v1/device/{ble_id}/firmware-upgrade`
returns the table payloads themselves (`centers`, `bins`, `nPixelsPerBin`,
`deadPixelsIndices` as base64 + 4-byte checksum), which would have given the
pixel->band mapping outright. Probed with all-zero file versions - so the server
should consider every file outdated - under the real tag, each substitute tag, and
with the parameter omitted: `new_version` is **empty in all five cases**, and again in a
2026-10 recheck under the recorded tag.

**Do not retry either of these** without a genuinely new input (another device's identity,
or a tag the device itself reports). If you want a second binning of one ciphertext
you need tables for another generation, and neither endpoint will part with them.
The remaining routes are still the hardware ones below.

## Two hypotheses worth writing down

Salvaged from `archive/notebooks/01_scio_usb.ipynb` before it was archived; both are
recorded here so nobody re-derives them from scratch, and so nobody mistakes them for
findings.

**1. `AptinaId` as an AES-256 key.** The Aptina id is 32 hex characters - 128 bits as bytes,
but 32 *characters* if taken as an ASCII string, which is exactly an AES-256 key length. That
coincidence is the reason device identifiers are in the candidate set at all.
`keyrecover.py` and the corrected `search_v2` test id-derived keys (raw, ASCII, and standard
KDFs over them) and none has ever validated. (An earlier dark-frame rescreen fed the header
into the cipher and is superseded; `rescreen_dark.py` now dispatches to `rescreen_v2.py`.) The rationale was never written down, only the code - so if you are
tempted to "try the Aptina id", it has been tried.

**2. The reflectance formula is not a decoding shortcut.** `archive/more_info/decrypt.txt`
gives `R = (S - D) / (G - D)` over sample / dark / gradient. That is almost certainly the
right *physics*, and it is how the spectrum is computed - **from decrypted per-pixel data**.
Applying it to the ciphertext bytes is meaningless, and an early notebook did exactly that on
three magic u32s and got a number. Note also that `decrypt.txt` is an unverified third-party
note: it claims the three sections are "400 bytes long", where the measured sizes are
1800/1800/1656. Treat its arithmetic as plausible and its specifics as wrong.

## The bar for success

A smooth-looking curve is **not** a result, and neither is high correlation: a wrong
amplitude can correlate perfectly. The bar, enforced by `research.numerical_check` and
`pipeline.py`:

- the same key/mode must produce consistent plaintext across *different* scans;
- the resulting spectrum must match the server's on **all 331 bands**, on the exact
  740-1070 nm axis, at `atol=rtol=1e-6`, with no per-scan rescaling. Reference truth is the
  92 records in `02_processed_data/` (42 of them also carry the 2020/21 server answer);
- it must then pass on the six **frozen** fresh cap scans
  ([manifest](analysis_output/recovery_20261003_followup/fresh_reference_validation.json)),
  and reject wrong metadata, swapped roles and shuffled input.

`validation.validate`'s median-Pearson >= 0.90 is a floor for spotting near-misses, not
acceptance.

An earlier iteration of this work produced a false "hit" by sliding a window over
firmware bytes until something scored well, and another by reading random bytes
as float32. Both are why the corroboration checks exist.
