# `dev/` - offline decoding (unresolved)

Everything here belongs to one question:

> **Can a SCiO scan be turned into a spectrum without the Consumer Physics server?**

The answer today is **no**, and this directory is the record of why. It is kept
separate from `src/scio/` on purpose: the working pipeline must not depend on any
of it, and `pytest tests/` must pass with `dev/` deleted.

## The problem

A scan is three blobs (dark, sample, gradient - 1800/1800/1656 B on `-e`
firmware). Each is an 8-byte plaintext header (`u32` type, `u32` per-scan value)
followed by a body that is an exact multiple of the AES block size and carries
~7.9 bits of entropy per byte. Repeated scans of an unchanged target share **no**
ciphertext blocks, so the body is not ECB and something per-scan varies. The
conversion happens on the device's Blackfin BF512 DSP, whose firmware
(`dsp_op`, 32628 B on this unit) we do not have and cannot read back over USB.

Nothing here has recovered a key, and no candidate decode has ever survived
validation against a stored server spectrum.

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
