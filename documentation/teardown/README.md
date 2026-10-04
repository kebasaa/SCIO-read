# SCiO teardown photos (SparkFun)

All of these photos are shown and explained in the hardware reference,
[`../HARDWARE.md`](../HARDWARE.md). This file is the folder's attribution and licence
record.

**Source:** "SCiO Pocket Molecular Scanner Teardown" by JOEL_E_B, SparkFun Electronics,
<https://learn.sparkfun.com/tutorials/scio-pocket-molecular-scanner-teardown-/all>
(photos taken 2017 according to their EXIF data).

**Licence:** SparkFun publishes its tutorials under
[Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/).
These files are unmodified copies of the full-resolution images on SparkFun's CDN
(`cdn.sparkfun.com/assets/learn_tutorials/6/5/7/`), downloaded 2026-10-04. They stay under
CC BY-SA 4.0, not under this repository's GPLv3. Any modified version you publish must
credit SparkFun and carry the same licence.

The tutorial's app screenshot (credited to the iTunes App Store) and its phone image
(credited to IEEE Spectrum) are not SparkFun's own photos and are deliberately **not**
copied here.

## Photos

| File | Shows |
|---|---|
| [SCiO_Teardown_00.jpg](SCiO_Teardown_00.jpg) | Unboxing |
| [SCiO_Teardown_01.jpg](SCiO_Teardown_01.jpg) | SCiO on its calibration/scanning stand |
| [SCiO_Teardown_02.jpg](SCiO_Teardown_02.jpg) | Opening the housing |
| [SCiO_Teardown_03.jpg](SCiO_Teardown_03.jpg) | First layer of parts: battery housing, PCB |
| [SCiO_Teardown_04.jpg](SCiO_Teardown_04.jpg) | Heatsink wrapped around the PCB and sensor |
| [SCiO_Teardown_05.jpg](SCiO_Teardown_05.jpg) | Sensor module on its heatsink; flex labelled `P/N:CP-PC00048B1`, `ichia 1650`, sticker `FW:9216` / `SF421601JN` |
| [SCiO_Teardown_06.jpg](SCiO_Teardown_06.jpg) | Heatsink and the flex cable's board-to-board connector |
| [SCiO_Teardown_07.jpg](SCiO_Teardown_07.jpg) | Sensor module out of the front housing (magnets, screws) |
| [SCiO_Teardown_08.jpg](SCiO_Teardown_08.jpg) | **Bare PCB, top:** S/N label over the BF512, SDRAM (U700), small QFNs, test pads |
| [SCiO_Teardown_09.jpg](SCiO_Teardown_09.jpg) | **Bare PCB, bottom:** sensor connector, CC2540 under a "9A" label, USB, battery connector |
| [SCiO_Teardown_10.jpg](SCiO_Teardown_10.jpg) | **Close-up:** ADSP-BF512 KBCZ-3 next to the SDRAM |
| [SCiO_Teardown_11.jpg](SCiO_Teardown_11.jpg) | **Bottom side with the label removed:** CC2540 F256 |
| [SCIO_Teardown_Images-12.jpg](SCIO_Teardown_Images-12.jpg) | Sensor module off the heatsink: LED window and red-filtered sensor window |
| [SCIO_Teardown_Images-13.jpg](SCIO_Teardown_Images-13.jpg) | Epoxy cut open: 3 × 4 filter array (left); LED, driver IC `U2` and the 12-aperture window over the wire-bonded array (right) |
| [SCIO_Teardown_Images-14.jpg](SCIO_Teardown_Images-14.jpg) | Diffuser sheet, 12-filter layer (3 × 4, visibly different filters), aperture plate with differing hole sizes |
| [SCIO_Teardown_Images-15.jpg](SCIO_Teardown_Images-15.jpg) | All optical layers, including the 12-lens array, beside the module |
| [SCIO_Teardown_Images-16.jpg](SCIO_Teardown_Images-16.jpg) | Close-up: 12-aperture window, wire bonds, LED and `U2` |

## Markings read from these photos (2026-10-04)

| Part | Marking | Identification |
|---|---|---|
| DSP | `ADSP-BF512 KBCZ-3`, `3643601.1 0.2`, `#1644 CHINA` | ADSP-BF512KBCZ-3: 0–70 °C, 300 MHz, 168-ball CSP_BGA; **no on-chip program flash** (datasheet Rev E ordering guide) |
| SDRAM (U700) | `ALLIANCE MEMORY AS4C8M16SA-7BCN 1534` | 128 Mbit SDRAM |
| BLE SoC | `CC2540 F256 TI 6AJ PCND G4` | TI CC2540F256: 256 KB flash, USB, AES engine, 2-wire debug on P2_1/P2_2 |
| U341 | `5062 2 #1641 36040` | Probably ADI **ADP5062** Li-ion charger (ADI-style date code `#1641`); not confirmed |
| QFN near U341 | `LGQ #629` | Unidentified (ADI-style branding/date code) |
| QFN near C318 | `BDT 52W Z25K` | Unidentified |

No 8-pin SOIC/WSON device resembling a standalone SPI flash is visible on either face at
this resolution. That is a photo-resolution observation, not proof of absence. The analysis
built on these markings is in
[`../HARDWARE_ACQUISITION.md`](../HARDWARE_ACQUISITION.md#teardown-photo-review-2026-10-04).
