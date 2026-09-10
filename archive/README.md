# `archive/` - superseded material, kept for provenance

Nothing here is part of the working project. It is kept because it records *how*
things were figured out, and because a superseded file occasionally turns out to
be the only place some detail was written down.

**Archived files are frozen.** Do not edit them, and do not run them. Two are
actively unsafe to execute:

- `notebooks/02_extract_log_scan.ipynb` writes into `01_rawdata/`, which is now
  **append-only** (see `documentation/HANDOFF.md`).
- `notebooks/01_scio_usb.ipynb` opens the serial port with no timeout, which is
  the exact failure `src/scio/usb.py` was written to fix.

The one exception to "frozen" is redacting a secret. A long-expired Consumer
Physics access token was found in a notebook here and replaced with
`<REDACTED-EXPIRED-TOKEN>`; the value is still in git history, but it died
seconds after it was issued in June 2020 (SCiO tokens carry `expires_in=14`).

## What is here, and what replaced it

| file | what it was | replaced by |
|---|---|---|
| `notebooks/01_scio_usb.ipynb` | the original all-in-one USB driver: framing, every parser, scan and calibration drivers | `src/scio/usb.py` + `src/scio/protocol.py`. Its unique content was lifted out first: the app symbol names into README §3, the decompilation provenance into `documentation/firmware_notes.md`, the AES-256 hypothesis into `dev/README.md` |
| `notebooks/01_scio_usb_orig.ipynb` | an even earlier version of the same | as above |
| `notebooks/01b_scio_usb.ipynb` | the first safety-gated opcode-probing experiment | `src/scio/probe.py` + `03_scio_probe.ipynb` |
| `notebooks/02_extract_log_scan.ipynb` | parsed app logcat dumps into per-scan JSON | `src/scio/logscan.py`, which is strictly better: the notebook only emitted scans the server had answered, so it silently dropped 17 |
| `notebooks/05_scio_ble_devel.ipynb` | an unfinished `bleak` BLE client, plus unrelated Apogee-sensor code | nothing - BLE was never finished. The protocol facts are in README §2, and §2 also records *why* this attempt failed (it read replies from the control characteristic instead of subscribing to the reporter) |
| `notebooks/test_*.ipynb` | ad-hoc scratch experiments | nothing |
| `process_scio.py` | a one-off processing script | `src/scio/session.py` |
| `scio lsusb output.txt` | raw USB enumeration capture | README §2 (VID:PID `0451:16AA`) |
| `more_info/` | notes, vendor correspondence and third-party advice gathered while reverse-engineering | still the only source for some of it - `ble.txt` has the device BLE MAC, `decrypt.txt` has the `R = (S-D)/(G-D)` reflectance formula |

`more_info/` is **unverified third-party material**, not project findings. Some of
it is wrong: `decrypt.txt` states the three blob sections are "400 bytes long"
where the measured sizes are 1800/1800/1656. Treat it as leads, not facts, and
check anything from it against README before relying on it.

## Convention

- Archive with `git mv`, never by copying - history should follow the file.
  (The original contents of this folder were added rather than moved, and their
  provenance is weaker for it.)
- Lift any unique knowledge into the README, `documentation/`, or `dev/README.md`
  **before** moving the file, and note here what went where.
- Keep original filenames. Root notebook numbers were reassigned by role in
  September 2026, so a number in this folder refers to the old scheme.
