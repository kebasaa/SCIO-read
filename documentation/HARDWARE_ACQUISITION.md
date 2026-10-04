# SCIO firmware acquisition procedure

This is the next evidence-producing step after the USB and APK routes were
exhausted. It is deliberately read-only. Do not erase, program, unlock, reset,
or alter the boot-mode straps.

## What was established before opening the device

- The connected unit exposes only one USB CDC-ACM interface (`0451:16AA`, USB
  revision `0009`, bus description `CP SCIO USB CDC`). There is no enumerated
  DFU, mass-storage, HID, or vendor-specific sibling interface.
- All inspected app generations declare the same command set. `0x81` transfers
  a file from host to device; `0x87` returns metadata only.
- The processor identified in the teardown is the plain ADSP-BF512, not a
  BF51xF part with integrated flash. The datasheet defines external SPI boot as
  BMODE `011`, using SPI0: PG15/select, PG12/clock, PG14/MOSI and PG13/MISO.
- JTAG signals are TCK, TMS, TDI, TDO, TRST and EMU. The processor must be
  halted for memory/register access.

### Added 2026-09-30, after the server was fully characterised

- **The server has returned no firmware.** `new_version` was empty in every probe (2026-09) and
  in a 2026-10 recheck, the newest app's `scionir.com` backend is the same server, no endpoint
  returns raw intensities, and no firmware was found in any supplied app or on the analysis
  machine. Offers could be device- or account-dependent; for this unit a hardware read is the
  only remaining source. (Corrected 2026-10-04: earlier wording said "closed for good".)
- **Protected blobs are bound to the device identity.** The server rejects any tested change to
  the second header word or body of sample/dark/white blobs with `400 Bad_sample_signature`, and
  a valid blob submitted under a different device_id is rejected the same way. Some per-device
  material therefore exists on the server side. Whether the device holds one secret, two
  (transform and integrity) or none of its own is **not** established (corrected 2026-10-04;
  see `dev/README.md`).
- **Which chip applies the transform is not known.** It could be the BF512 DSP or the CC2540
  BLE/USB MCU (see Route C). Identify both dumps' contents before assuming the DSP is the target.

## Teardown photo review (2026-10-04)

Source: SparkFun's teardown photos, stored with attribution (CC BY-SA 4.0) in
[`teardown/`](teardown/README.md). Datasheet:
[`adsp-bf512-514-516-518.pdf`](adsp-bf512-514-516-518.pdf) (Rev E).

### The DSP has no on-chip program flash

- The marking is `ADSP-BF512 KBCZ-3` (photo 10): the ordering-guide model ADSP-BF512KBCZ-3,
  0-70 °C, 300 MHz, 168-ball CSP_BGA. None of the nine BF512 models has a flash suffix; the
  Rev E datasheet explicitly drops the obsolete models that had 16 Mbit SPI flash.
- Boot source is set by the BMODE2-0 straps (Table 6): `001` external 8/16-bit flash,
  `011` external SPI flash/EEPROM, `100` **SPI0 host** (the BF512 is an SPI slave and is fed
  the LDR stream), `101` OTP (at most 2,560-3,072 bytes of public OTP), `110` SDRAM warm
  boot, `111` **UART0 host** (autobaud on `@`, then the host sends the stream).
- OTP is far too small for `dsp_op` (32,628 B). So `dsp_op` arrives from external memory or
  from a host, possibly in a second stage loaded by `dsp_boot`.
- Lockbox (code authentication, secure mode, private OTP, unique chip ID) exists on this
  part. Whether it is used is unknown. If it is, key material may sit in private OTP that
  no external read reaches.

### No visible standalone flash; the CC2540 may host the DSP images

- Every legible package on both faces is identified in
  [`teardown/README.md`](teardown/README.md#markings-read-from-these-photos-2026-10-04):
  BF512, SDRAM, CC2540F256, a probable ADP5062 charger (`5062 #1641`), and two small
  unidentified QFNs (`LGQ #629`, `BDT 52W Z25K`). There is no 8-pin SOIC/WSON part that
  looks like a standalone SPI flash at this photo resolution. That is not proof of absence:
  a small QFN or WSON flash, or a part under the S/N label or the heatsink, is still possible.
- **Hypothesis, unverified:** the CC2540 stores the DSP images and boots the BF512 as an
  SPI0 or UART0 host. This is consistent with the evidence:
  - Every file the device reports (BLE runtime 119,233 + `dsp_boot` 7,284 + `dsp_dec`
    14,600 + `dsp_op` 32,628 + four tables 3,116 = **176,861 B**) fits in the CC2540F256's
    256 KB flash.
  - The file list, file headers and `FILE_DOWNLOAD` are all served over the CC2540's own
    USB/BLE link.
  - The CC2540 carries a hand-written "9A" label in photo 09, typical of a programmed part.
- If the hypothesis holds, two routes would give the DSP images: reading the CC2540 flash
  (see below), or passively recording the boot traffic between the two chips.
- The sensor module's flex carries its own `FW:9216` sticker (photo 05). It may identify a
  module firmware or calibration revision. Its meaning is unknown.

### CC2540 debug-lock status: cannot be determined without hardware

- The CC2540's two-wire debug interface uses P2_1 (DD, pin 35) and P2_2 (DC, pin 34) plus
  RESET_N (CC2540F256 datasheet, pin table). No labelled debug header is visible near the chip
  in photos 09/11. The four castellated edge pads by `TP802` (photo 08) are a candidate
  programming connector, but they are not traced to these pins.
- Neither the photos nor the USB protocol reveal the lock state. It needs a separately
  planned, authorised hardware session:
  1. Open the enclosure. The teardown notes the housing is not designed to be reopened, so
     expect damage.
  2. Trace DD/DC/RESET_N/GND/VDD to accessible pads with a continuity meter, with the board
     unpowered.
  3. Connect a CC Debugger-class tool and use only its status/ID readout. The debug
     status byte reports the lock bit (TI SWRU191, debug interface chapter: verify the
     command against the guide before use).
  4. **Never accept a "chip erase" prompt.** On a locked part, erase-then-read destroys the
     only copy. If it reports locked, record that and stop.

### Revised order of hardware routes

1. **Passive boot-traffic capture.** With a logic analyzer on the BF512's SPI0 or UART0 lines
   (or the bus to any flash), record power-on. Whatever source BMODE selects, the LDR stream
   must cross a bus unless it comes from OTP. This is read-only and needs no unlocking.
   Identifying the right nets from the photos alone is not possible, because the BF512 is a BGA.
2. **CC2540 lock-status readout** (above). If it is unlocked, a read-only flash dump would also
   cover the hypothesis that the CC2540 hosts the DSP images.
3. Routes A (if an SPI flash is found) and B (BF512 JTAG) below, unchanged.

## Route A - external SPI flash (if one is found)

1. Photograph both PCB faces sharply before touching anything. Include the
   orientation mark and readable top markings of every 8-pin device.
2. Identify each candidate using its datasheet. Do not assume that every
   SOIC-8 is flash; regulators and EEPROMs often use the same package.
3. Determine the flash I/O voltage from the exact part number. Never attach a
   5 V CH341A output. Use a verified 3.3 V programmer or the correct 1.8 V
   adapter as required by the chip.
4. Disconnect USB and the battery. Check that the board is unpowered. Connect
   common ground first, then CS, CLK, MOSI, MISO and the correct supply.
5. Perform only JEDEC-ID and read operations. Read the complete address space
   twice into `dump_a.bin` and `dump_b.bin`, power-cycling the programmer
   between reads.
6. Require identical SHA-256 hashes. A mismatch usually means marginal clip
   contact, incorrect voltage/part selection, or another device driving the
   bus. If in-circuit reads remain unstable, stop; do not compensate by writing
   status registers. Isolating chip-select or removing the flash is safer.
7. Analyze both dumps:

   ```powershell
   <USER_HOME>\.conda\envs\tp\python.exe dev\scripts\analyze_flash_dump.py `
     dump_a.bin dump_b.bin `
     --output dev\analysis_output\flash_dump_report.json `
     --extract-dir 01_rawdata\device_files\flash_carved
   ```

The analyzer searches for this unit's exact 16-byte metadata headers, checks
candidate body sizes and byte sums, compares independent dumps, and extracts
only a unique body adjacent to an exact header whose checksum also matches.
A rolling byte-sum-only match is labelled weak and is never auto-extracted.

## Route B - BF512 JTAG (second choice)

Use a Blackfin-compatible Analog Devices emulator and its supported software;
a generic ARM J-Link/OpenOCD setup is not sufficient merely because the port
is IEEE 1149.1.

1. Locate an unpopulated test header or pads with TCK, TMS, TDI, TDO, TRST,
   EMU, RESET, GND and target-reference voltage. Confirm by schematic or
   continuity; do not probe BGA balls directly.
2. Power the target normally and let the probe sense its I/O voltage. Do not
   back-power it from the emulator.
3. First test TAP identification and halt/resume only. If security prevents
   debug, record that fact and stop; do not attempt OTP programming or an
   unlock/erase sequence.
4. If halt succeeds, dump external memory, L1 instruction/data SRAM and the
   readable OTP/public pages. Capture once shortly after boot and once during
   a scan. A runtime dump may reveal decoded tables, firmware code, or transient
   transform keys even when the boot image is opaque.
5. Preserve the raw dumps unchanged and analyze them with
   `analyze_flash_dump.py`; separately run `scio_offline.firmware.triage_blob` on carved
   `dsp_op` candidates.

## Route C - CC2540 BLE/USB MCU (consider before assuming the DSP)

The Sparkfun teardown places a TI CC2540 on the board, and the USB VID `0451` is Texas
Instruments, so the CC2540 - not the BF512 - is what enumerates as the USB CDC device and
speaks the `0xBA` protocol. It has a hardware AES-128 engine and 256 KB of internal flash.
This matters because the per-blob **signature** (and possibly the payload transform) could be
applied by the CC2540 as the data passes through it, rather than by the DSP. If so, the CC2540's
flash holds the signing/transform key and the DSP dump would not.

- The CC2540 debug interface is a two-wire (DD/DC) protocol, read with a CC-Debugger or a
  compatible flash-programming tool. Datasheet: `documentation/CC2540F256.pdf`.
- Internal flash read-out is blocked when the debug-lock fuse is set; TI parts commonly ship
  locked, and read-back then requires a full chip erase, which destroys the contents. **Do not
  erase.** If the part is locked, treat this route as closed rather than erasing to unlock.
- What to look for in an unlocked dump: an AES key schedule or 16/32-byte constants near the
  code that drives the AES engine; the string/table handling for `i2s_tag_config`; and any
  routine that computes the signature checked as `Bad_sample_signature`.
- Decide the order by evidence, not assumption: dump whichever chip is cheapest/safest to reach
  first, identify what each holds, and only then commit effort. A during-scan JTAG/SRAM capture
  (Route B) can also reveal *which* chip touches the pixel data, by showing where it appears in
  the clear.

## Exact validation targets for this unit

| Name | Type | Size | Version | Header checksum |
|---|---:|---:|---:|---:|
| BLE runtime | 87 | 119233 | 125 | 12925168 |
| dsp_boot | 90 | 7284 | 17 | 688456 |
| dsp_dec | 91 | 14600 | 12 | 1548938 |
| dsp_op | 92 | 32628 | 147 | 4151168 |
| deadPixelsIndices | 100 | 1714 | 3 | 97267 |
| centers | 101 | 96 | 3 | 6080 |
| bins | 102 | 140 | 3 | 13587 |
| nPixelsPerBin | 103 | 1166 | 3 | 36371 |

The checksum algorithm has not been proven from device firmware. The analyzer
tests the simple unsigned byte sum because every observed value is compatible
with that magnitude, but it requires header adjacency as stronger evidence.

## After a valid body is recovered

1. Keep the original dumps immutable and work on copies.
2. Run LDR parsing, entropy profiling, string extraction and cipher-signature
   searches already implemented in `scio_offline.firmware` and `scio_offline.keyrecover`.
3. If `dsp_op` is a plaintext Blackfin LDR, disassemble it and trace the code
   handling the sample command and the four image-to-spectrum tables.
4. If it remains opaque, prioritize a during-scan JTAG SRAM capture over more
   identifier-derived key guessing.
5. A proposed decoder is accepted only when it recovers repeatable 331-point
   `sample_raw` and `wr_raw` vectors and reproduces archived
   `spectrum = sample_raw / wr_raw` results on held-out scans.
   `dev/scio_offline/validation.validate()` scores a candidate `decoder(bytes) -> 331 floats`
   against all 92 stored (blob, spectrum) pairs in seconds (self-checked: a perfect decoder
   scores Pearson 1.0, noise fails). Wire the recovered decoder into it; do not accept a decode
   on a single scan or by eye.

## Route D - another owner's cached firmware (no hardware, no teardown)

Both apps cached the firmware in Android SharedPreferences after an over-the-air upgrade, so any
SCiO owner whose phone ran the app **and never completed a later upgrade** may still hold the
blobs the server no longer serves. `dev/scio_offline/firmware.py` already extracts them from a
SharedPreferences XML or an `adb backup`. This needs no hardware and no risk to this unit.

Outreach text for the repo issue tracker / SCiO communities:

> Looking for cached SCiO firmware to enable offline spectral decoding of a discontinued device.
> If your phone ran the SCiO or SCiO Lab app, it may hold the device firmware and calibration
> tables in app data (`/data/data/com.consumerphysics.*/shared_prefs/`, or an `adb backup`).
> The files are `dsp_op`, `dsp_boot`, `dsp_dec`, and the tables `centers`, `bins`,
> `nPixelsPerBin`, `deadPixelsIndices`. Even a single device's set would help. No account
> details or personal data are needed - just those files.

Note the author of `archive/more_info/decrypt.txt` describes an older 400-value-generation unit
and is a natural first contact.
