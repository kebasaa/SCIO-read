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
  scio_offline/     the research modules (import as `scio_offline`)
  scripts/          CLI drivers; import `_bootstrap` first, which fixes sys.path + cwd
  notebooks/        exploratory notebooks 03, 04, 06, 08, 10 (evidence pipeline)
  tests/            pytest for this strand only
  analysis_output/  generated reports, safe to delete and regenerate
```

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

## The bar for success

A smooth-looking curve is **not** a result. `pipeline.py` enforces the actual
bar, and it should stay enforced:

- the same key/mode must produce consistent plaintext across *different* scans, and
- the resulting spectrum must agree with a **held-out** server spectrum from
  `01_rawdata/log_extracted/` (42 canonical records carry one).

An earlier iteration of this work produced a false "hit" by sliding a window over
firmware bytes until something scored well, and another by reading random bytes
as float32. Both are why the corroboration checks exist.
