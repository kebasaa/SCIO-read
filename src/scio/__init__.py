"""SCIO-read: capture Consumer Physics SCiO data and turn it into spectra.

This package is the *working* pipeline: talk to the device, store a scan in a
self-contained record, and (optionally, later) have the vendor server convert it
into a 331-point spectrum. Capture needs no network.

protocol     command framing, response parsers (pure)
usb          pyserial transport, read-only capture
probe        safety-gated probing of undocumented opcodes
store        on-disk formats, fixtures, white reference / calibration policy
cloud        vendor API: login, scan -> spectrum, calibration thresholds
credentials  encrypted, machine-bound credential store
session      capture / convert / process - the high-level workflow
corpus       canonical inventory of local captures and archived spectra
reference    archived vendor CSV exports
paths        portable (non-identifying) path labels

Unresolved offline-decoding research lives in ``dev/scio_offline``.
"""

from . import cloud, corpus, credentials, paths, protocol, reference, store  # noqa: F401

__version__ = "0.5.0"
