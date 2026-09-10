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

## Route A - external SPI flash (first choice)

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
