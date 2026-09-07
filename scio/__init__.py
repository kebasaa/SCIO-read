"""SCIO-read: capture Consumer Physics SCIO data and investigate it offline.

Modules
-------
protocol   command framing, response parsers (pure)
usb        pyserial transport, read-only capture
store      on-disk formats, fixtures, white reference
firmware   obtaining/triaging DSP firmware + calibration tables
evidence   statistical tests of opaque scan payloads
corpus     canonical inventory of local captures and archived spectra
decode     candidate transforms and spectral normalization helpers
keyrecover bounded key hypotheses and verification
"""

from . import corpus, decode, embedded_cipher_hypothesis, evidence, flashdump, image_hypothesis, pipeline, protocol, repeatability, store, stream_hypothesis  # noqa: F401

__version__ = "0.4.0"
