# HarvestMaster / Mirus audit (2026-10-09)

> Interpretation correction: the original conclusions below are preserved as
> historical research, not current proof. The installer follow-up reconciled
> 288 payloads and traced provisioning. It did not recover the separate service;
> it does not prove that service contains a decoder, is managed/.NET8, runs
> consumer decoding offline, or is absent from every public package. See
> [updated report](../harvestmaster_service_20261009/REPORT.md).

Static audit of the public HarvestMaster (Juniper Systems) software for the **H3 GrainGage**, a
combine-mounted grain gauge with an embedded SCiO NIR sensor. No installer was run and nothing
was activated. Downloads and extracts are in `dev/private/harvestmaster/`, which is git-ignored.
The triage driver is `dev/scripts/audit_harvestmaster.py`.

## Inputs

| File | Source | Size | SHA-256 |
|---|---|---|---|
| `JS-SCiO_Troubleshooter_1.2.0.exe` | harvestmaster.com/data/support/HarvestMaster/ | 9,118,034 | `54b182c4…c598` |
| `Mirus-4.6.11.exe` | harvestmaster.com/data/files/mirus/ | 225,435,768 | `ef5d15fc…fb43` |
| `Mirus-5.0.0.exe` | harvestmaster.com/data/files/Mirus5/ | 154,683,592 | `fb1500e2…30ad` |

Extraction steps:
- The two Mirus installers are WiX Burn bundles. They were unpacked with 7-Zip: the UX payloads,
  then the attached container (a carved cab), then `Mirus.Installer.msi`.
- The plugin bundles (`.mpb` / `.mpb5`) are zip archives that contain `plugin.zip`.
- The troubleshooter is a .NET single-file bundle, decompiled with `ilspycmd --bundle-entry`.

Audit scope: 1,878 files (436 .NET assemblies). The vocabulary sweep searched ASCII and UTF-16LE
and covered vendor names, spectral terms, payload fields, firmware names, crypto and transport
terms.

## Result: outcome C (thin client), plus a new lead

**HarvestMaster code never touches SCiO data.** `HM.Devices.Scio.ScioApiClient`, in both the
Mirus 4 and Mirus 5 builds, is a REST client to a separate local process at
`http://localhost:8080/v1/`. Its endpoints:

- `POST scan`, which takes plot id, location and gauge id, and returns `{crop_name, results: {constituent: value}, scan_id, temperature}`.
- `POST connect`
- `GET status`, which returns `device_id`, `port`, `scio_is_connected`, `temperature` and `last_data_sync`.
- `GET code_version`, which returns `version` and `firmware_version`.
- `GET models` and `GET/PATCH crop`
- `POST self_test`
- `POST export_scans`, which returns a `zip_path`.
- `PATCH port` (serial port)
- `PATCH data_sync {enable}` (Mirus 5)
- `PATCH logs` (Mirus 5)

No blob, spectrum, key or calibration table crosses this interface. The Mirus 5 emulator
(`EmulatedScioApiClient`) returns random constituent values.

**The decoder lives in the "SCiO Service".** The evidence:
- HarvestMaster troubleshooting guide 31859-00 (07/23), §2.3: a Windows service named
  **"SCiO Service"**, described as *"A SCiO sensor sample analysis service. Version
  v2.011.013.5"*. It listens on `localhost:8080` and talks to the sensor over a serial-to-USB
  cable.
- Support articles 17160 and 17179: it is installed by a separate **"SCIO Services installer"**
  and needs 64-bit Windows 11 plus **.NET 8**. That points to a .NET 8 x64 build, which ILSpy can
  decompile.
- scionir.com, Hardware Integrations page: the combine product *"store[s] data locally and sync[s]
  to the cloud when connected"* and gives "results in real-time". The Mirus 5 `data_sync` toggle
  matches this.
- Article 17161: crop models arrive as "a new software build" for Premium licences.

Taken together, the service has to turn sensor output into constituent predictions **offline**.
That means it contains, or is given, the decode step and the chemometric models.

**Not public.** The service is in neither Mirus installer, nor any plugin bundle, nor the
troubleshooter. No download link exists on the harvestmaster.com support pages or the sitemap. It
is distributed to H3 customers.

## Caveats

- The H3 "SCiO Sensor" is a serial-connected OEM build. It may be a different hardware
  generation, with a different raw format or keys, from the consumer BLE units: the owner's
  fw-147 unit and the contributor's fw-138 unit. The audit does not show that its blobs match
  ours.
- Per-device key material could be fetched when the licence is activated rather than shipped in
  the binary. In that case the service would show the algorithm but not our units' keys.

## Negative side findings

- `Firmware/v7/DSP-7.58.5.enc` and `ACT-7.58.5.enc` belong to HarvestMaster's own GrainGage DSP
  and actuator modules, not to the SCiO.
- Two 4-byte matches of the fw-147 `dsp_op` checksum (4151168) sit inside large .NET DLLs
  (IronPython, 24 MB app assembly). They are coincidental.
- One 1408 B size match is Python's `email/mime/text.py`.
- No file matches any SCiO firmware or calibration-table size by content.

## Next step

Obtain the SCiO Service installer. Options:
- HarvestMaster field service (hmtechsupport@junipersys.com);
- an institution that runs an H3 GrainGage;
- an archived copy.

Then repeat this audit on it and trace `POST /v1/scan` → serial read → decode → model.
