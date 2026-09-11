"""Offline-decoding research (strand B) - unresolved.

These modules attempt to turn raw SCiO scan blobs into spectra *without* the
Consumer Physics server. Nothing here is on the working scan path; the working
path is ``scio`` under ``src/``. See ``dev/README.md``.

decode        candidate transforms, spectral normalization helpers
keyrecover    bounded key hypotheses and verification
firmware      obtain/triage DSP firmware + calibration tables
flashdump     carve blobs out of an external SPI flash image
evidence      neutral statistical diagnostics of opaque payloads
image_codec_hypothesis  is it a compressed image? (JPEG family, containers)
image_hypothesis / stream_hypothesis / embedded_cipher_hypothesis / repeatability
pipeline      end-to-end guard: refuses to export an unvalidated decode
compression_hypothesis  known codecs at every byte/bit alignment, self-screening
transform_class  what class of transform is it? (verdict artifact)
validation    score a candidate decoder against the 92 known spectra
"""

from . import (  # noqa: F401
    compression_hypothesis,
    decode,
    embedded_cipher_hypothesis,
    evidence,
    firmware,
    flashdump,
    image_codec_hypothesis,
    image_hypothesis,
    keyrecover,
    pipeline,
    repeatability,
    stream_hypothesis,
    transform_class,
    validation,
)

__version__ = "0.4.0"
