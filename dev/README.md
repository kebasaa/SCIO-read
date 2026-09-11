# `dev/` - offline decoding (unresolved)

Everything here belongs to one question:

> **Can a SCiO scan be turned into a spectrum without the Consumer Physics server?**

The answer today is **no**, and this directory is the record of why. It is kept
separate from `src/scio/` on purpose: the working pipeline must not depend on any
of it, and `pytest tests/` must pass with `dev/` deleted.

## The problem

A scan is three blobs (dark, sample, gradient - 1800/1800/1656 B on `-e`
firmware). Each is an 8-byte plaintext header (`u32` status/type, `u32` per-blob
value) followed by a body that is a multiple of 16 bytes and carries ~7.9 bits of
entropy per byte. The conversion happens on the device's Blackfin BF512 DSP, whose
firmware (`dsp_op`, 32628 B on this unit) we do not have and cannot read back.

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

**Compression is now the leading hypothesis.** The vendor calls the i2s tag
`compression_version`; in the un-obfuscated 2017 researcher build the parameter
carrying that value is literally named `i2sTag`, passed in the same call as the
four binning-table checksums; and the app ships an `UnsupportedCompressionConversion`
error string. You cannot convert between encryptions; you can re-bin between
binning tables. The gradient blob's length also changes with the generation
(1656 B on `-e`, 1416 B on `-o`) while the sample's does not.

**Encryption is not excluded, and cannot be excluded by software.** The device
could encrypt and the server decrypt. The Android client is a verified
byte-for-byte pass-through - BLE frames to `Base64.encodeToString` to JSON to
POST, with no arithmetic on the bytes anywhere - so it would contain no crypto
*either way*. A sweep for crypto primitives across all eight decompiled trees
(~1,500 files) finds none, but that only rules out **client-side** crypto, which
nobody proposed. Absence of evidence is close to worthless here.

The asymmetry that follows governs how to report results: **a compression hit
would be decisive; a compression miss is not.** Nothing in this directory may
conclude "therefore it is encrypted" - only "compression not demonstrated".

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
  analysis_output/       generated reports, safe to delete and regenerate
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
| `stream_hypothesis` | weak stream cipher / PRNG tests (negative) |
| `embedded_cipher_hypothesis` | look for cipher signatures embedded in firmware |
| `repeatability` | cross-capture screening: does a candidate key give *consistent* plaintext? |
| `pipeline` | the guard - refuses to export a spectrum from an unvalidated decode |
| `compression_hypothesis` | known codecs at every byte **and bit** offset, with partial-output tolerance; screens each codec against random input first and excludes any that "finds" structure in noise |
| `validation` | **the gate**: score a candidate decoder against all 92 records whose true spectrum we hold. Self-checked in both directions - truth must pass, noise must fail |

## Running it

```bash
pytest dev/tests/                      # offline, no hardware
python dev/scripts/analyze_scio.py     # neutral diagnostics over the corpus
python dev/scripts/recover_key.py      # needs dsp_op, which we do not have
```

Scripts assume the repository root as their working directory; `_bootstrap`
enforces that, so they can be launched from anywhere.

## Why it stalled, and what would unstick it

Every software-only route has been exhausted:

- **The cloud** returns firmware only through the upgrade endpoint, and the
  device is up to date (`new_version: null`).
- **The APKs** in the local decompilation set cache firmware in SharedPreferences
  but ship none, and the current Flutter app's `libapp.so` is arm64 AOT.
- **USB** has no readback path. `READ_FILE_HEADER` (0x87) returns 16 bytes and
  ignores an appended offset/length; `FILE_DOWNLOAD` (0x81) is host->device only;
  the declared-but-unimplemented opcodes do not answer. All probed on hardware -
  logs in `01_rawdata/probe_logs/`.

What is left is hardware, and it is cheap:

1. **Dump the external SPI flash** (~$15 CH341A + SOIC-8 clip). Gives
   `dsp_boot`/`dsp_dec`/`dsp_op` as stored - possibly Lockbox-encrypted.
   `dsp_op` is 32628 B on this unit; use that plus the header checksums to
   validate a dump. See `documentation/HARDWARE_ACQUISITION.md`.
2. **BF512 JTAG.** Halt the DSP mid-scan and read the key out of L1 SRAM.
   Works even if the flash image is encrypted, unless OTP has disabled JTAG.
3. **An old phone that never finished a firmware upgrade** - the consumer app
   deletes the cached blobs only after a *completed* upgrade. `firmware.py`
   already knows how to extract them.

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

**The firmware endpoint is closed too.** `GET /v1/device/{ble_id}/firmware-upgrade`
returns the table payloads themselves (`centers`, `bins`, `nPixelsPerBin`,
`deadPixelsIndices` as base64 + 4-byte checksum), which would have given the
pixel->band mapping outright. Probed with all-zero file versions - so the server
should consider every file outdated - under the real tag, each substitute tag, and
with the parameter omitted: `new_version` is **empty in all five cases**.

**Do not retry either of these.** If you want a second binning of one ciphertext
you need tables for another generation, and neither endpoint will part with them.
The remaining routes are still the hardware ones below.

## Two hypotheses worth writing down

Salvaged from `archive/notebooks/01_scio_usb.ipynb` before it was archived; both are
recorded here so nobody re-derives them from scratch, and so nobody mistakes them for
findings.

**1. `AptinaId` as an AES-256 key.** The Aptina id is 32 hex characters - 128 bits as bytes,
but 32 *characters* if taken as an ASCII string, which is exactly an AES-256 key length. That
coincidence is the reason device identifiers are in the candidate set at all.
`keyrecover.py` already tests id-derived keys (raw, ASCII, and standard KDFs over them) and
none has ever validated. The rationale was never written down, only the code - so if you are
tempted to "try the Aptina id", it has been tried.

**2. The reflectance formula is not a decoding shortcut.** `archive/more_info/decrypt.txt`
gives `R = (S - D) / (G - D)` over sample / dark / gradient. That is almost certainly the
right *physics*, and it is how the spectrum is computed - **from decrypted per-pixel data**.
Applying it to the ciphertext bytes is meaningless, and an early notebook did exactly that on
three magic u32s and got a number. Note also that `decrypt.txt` is an unverified third-party
note: it claims the three sections are "400 bytes long", where the measured sizes are
1800/1800/1656. Treat its arithmetic as plausible and its specifics as wrong.

## The bar for success

A smooth-looking curve is **not** a result. `pipeline.py` enforces the actual
bar, and it should stay enforced:

- the same key/mode must produce consistent plaintext across *different* scans, and
- the resulting spectrum must agree with a **held-out** server spectrum from
  `01_rawdata/log_extracted/` (42 canonical records carry one).

An earlier iteration of this work produced a false "hit" by sliding a window over
firmware bytes until something scored well, and another by reading random bytes
as float32. Both are why the corroboration checks exist.
