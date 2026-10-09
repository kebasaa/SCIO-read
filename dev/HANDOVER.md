# Offline-decoding handover

The short, current answer to "where is the offline decoder, and what should I try
next?". The full chronological record is [RECOVERY_STATUS.md](RECOVERY_STATUS.md);
device facts are in [DEVICE_FUNCTION_REFERENCE.md](DEVICE_FUNCTION_REFERENCE.md);
how to work in this repository is in
[`../documentation/HANDOFF.md`](../documentation/HANDOFF.md).

> **Maintenance rule.** Whoever starts a work session updates this file *first*:
> delete tasks that are finished (move their one-line result into "Current state"
> or "Do not repeat"), revise the remaining ones, and fix any other document the
> new work invalidates. This file must describe the present, not the history.

## Current state

**Changhong H2 discovery completed, 2026-10-09:** 40 bounded web search/page
operations found no verified H2 ROM/OTA, sensing APK, native service or SDK archive.
Primary ADI material confirms its sensor module and a sensor-to-cloud platform;
this does not locate the raw-to-spectrum conversion. Exact launch press-kit URL
was attempted privately: zero bytes, transport failure; HTTPS and public archive
index also could not be inspected through the web tool. These are unresolved
access/availability results, not proof that historical artifacts do not exist.
ZOL's H2 download tab failed; its sparse catalogue does not establish retail
availability or a hardware codename. Do not download Allwinner H2 boxes or XGIMI
H2 projector firmware. No vendor software obtained/executed, no device/activation
operations. Full findings, request ledger and artifact priorities:
[H2 report](analysis_output/changhong_h2_20261009/REPORT.md).

**Other SCIO integrations research completed, 2026-10-09:** verified Changhong H2
embedded SCIO/ADI integration; Cargill Reveal, Eurofins and DietSensor apps/services;
and cloud/mobile reseller offerings. No second packaged offline decoder verified.
Best distinctive artifact lead is legitimate Changhong H2 firmware/system sensing
apps; Reveal has identified Android/iOS packages but cloud/deferred-results evidence.
Existing Analyzer 1.5.6/1.5.19 inventories already contain Cargill Reveal assets;
compare code hashes before repeating analysis. CropX announced SCIO acquisition
on August 26, 2026; not proof of legacy support or restored consumer services.
39 research web operations, no packages/endpoints/accounts/activation/outreach.
See [partner report](analysis_output/scio_partners_20261009/REPORT.md).

**Renewed installer search completed, 2026-10-09:** 20 additional public operations
(80 combined with the earlier campaign), no installer acquired. Current SCIO Q&A
says requested models are included in a new customer software build; this is not
proof of device-specific binaries or consumer compatibility. Concrete uncompleted
leads: the known troubleshooting-guide Filecamp share, error-1060 screenshot and
complete linked H3 installation documentation. Guide/image failures are tool
limitations, not absence/access-control evidence. H3 licence warning has no
download action. No activation bypass, vendor credential use, downloads or outreach.
See [renewed search report](analysis_output/harvestmaster_search2_20261009/REPORT.md).

**Embedded dependency/resource audit completed, 2026-10-09:** 170 payload records,
160 distinct hashes (93 new to the prior inventory), 26 vendor assemblies
statically decompiled. Inspected 13,488 resx entries; 25 binary occurrences,
12 distinct hashes, no nested ZIP. Script-hash resources are JSON catalogs,
not firmware. SCIO clients still delegate scans/self-test to localhost service;
generic licensing/update code supplies no SCIO-specific package location.
No decoder, service installer or supported key recovered. Third-party machine
instructions and opaque serialized graphics are not exhaustively audited.
Source/payload hashes reverified; 9 socket-blocked research tests and 116 unchanged
production tests pass. No downloads, activation, vendor execution, device commands
or deletions. See [resource report](analysis_output/harvestmaster_resources_20261009/REPORT.md).
Safety finding: service export_scans is documented to delete history after ZIP
creation; do not classify it as read-only.

**Archive follow-up bounded run complete, 2026-10-09:** checked public archive
interfaces and the H2 NIR installation guide for service package references. User
cannot pursue HarvestMaster outreach; no correspondence will be sent. The
campaign retains the cumulative 60-discovery-operation ceiling and existing
five-package/2 GiB download limits. Access failures are not absence evidence.
Ordinary browser Wayback access now works (337 HarvestMaster data URLs, 205
support URLs). The retrieved 32-page H2 NIR guide explicitly describes separate
service installation and sensor-specific activation links. Its renewal route
is a contact/device-serial request form, not an exposed download. No form sent.
No service installer found in the enumerated archive filters; recorded budget
is 60 cumulative operations (conservatively including local filters/recovery).
Eight prefix indices inspected; unknown hosts/opaque names and every page body
remain outside coverage. Generic installer availability is still unresolved;
sensor-specific activation does not prove device-specific binary distribution.
One 19,075,308-byte guide retained, zero executable downloads/deletions.
See [archive report](analysis_output/harvestmaster_archive_20261009/REPORT.md).
*Result:* the H2 NIR Upgrade Installation Guide **31360** §1.7 names the
acquisition mechanism — the SCiO Service is installed per sensor via an
**activation link** obtained through **harvestmaster.com/support → My Product →
SCiO License Renewal**, not a public download (see "Acquisition mechanism found"
below). The decompile shows host-side delegation to the PC service and bypass
of the GrainGage moisture calculation (`MoistureDisable = MoistureCurve.IsScio`),
with additive constituent offsets downstream. It does not establish whether
the absent service or OEM sensor holds every transform, nor consumer-device
compatibility. A blind live-filename HEAD probe of
`harvestmaster.com/data/{files,support}` returned no package (do not repeat —
guessed-filename requests are against the campaign's own rule).

**HarvestMaster installer follow-up, 2026-10-09:** reconciled 288 Burn payloads
(all present; declared hash/size checks pass), decompiled installer-specific
code, plugin managers, both service helpers and supplied troubleshooting utility.
Seven MSI custom actions each; no service-registration tables. Traced plugin
installation copies local ZIP files. No concrete SCIO installer download found.
The supplied utility matches the prior 1.2.0 hash; fresh decompile confirms
localhost API calls plus GrainGage CAN diagnostics, not a consumer decoder.
Public/archive coverage has explicit limits; zero new downloads/removals.
Verification: 278 socket-blocked research tests, six targeted audit tests and
116 unchanged production tests passed. Original package/payload hashes unchanged.
See [campaign report](analysis_output/harvestmaster_service_20261009/REPORT.md)
and its evidence ledger/coverage manifests.
All new artifacts remain under `dev`; private vendor code is not published.
No installer execution, service installation, activation or device operations.
Earlier thin-client observations do not establish where decoding occurs or
consumer-device compatibility; a service absence claim requires bounded coverage.

**Completed checksum-informed follow-up, 2026-10-08:** 2,342 unique hypothesis
keys and all 180,266 jobs. No structural intermediate, reflectance, domain vectors
or keyed-integrity match. There were 390 lead configurations, including nine in
random controls; all 402 codec hits were raw-deflate parses consuming 4–68 bytes
and leaving >=1,688 unexplained trailing bytes. No owner cross-acquisition lead;
the contributor has one acquisition only. Current owner headers on historical
scans remain an unverified association, limiting negative conclusions.
The 39-file static audit found no supported USB/BLE firmware-body read operation;
zero device/server operations. Offline firmware inspection and actual-byte
comparison are prepared for newly supplied artifacts. Frozen captures untouched.
See [CHECKSUM_CAMPAIGN.md](CHECKSUM_CAMPAIGN.md) and
[report](analysis_output/checksum_headers_20261008_run/REPORT.md).
Verification: 263 socket-blocked research tests and 114 unchanged production tests
passed. Complete-checkpoint resume, public-safety and compressed-artifact scans
passed. Do not repeat these candidates without new header/firmware evidence.

**Completed 2026-10-08 follow-up:** contributor firmware acquisition using the
exact four app firmware version keys, fresh authentication per request, and
bracketing owner controls. All four GETs returned HTTP 200 with byte-identical
51-byte null offers; no firmware obtained. Completion-to-next-preparation gaps
were 20.000, 20.000 and 20.016 seconds. The sandboxed first launch failed auth
before any firmware GET. The earlier eight-key contributor results remain
preserved. See [CONTRIBUTOR_FIRMWARE.md](CONTRIBUTOR_FIRMWARE.md) and
[campaign report](analysis_output/contributor_fw138_exact4_20261008_network/REPORT.md).
No device operation or external message occurred. Do not repeat this route without
new evidence such as another authorized account or an independently supplied dump.
Verification: 205 socket-blocked research tests and 114 unchanged production tests
passed; 31 acquisition tests rechecked after final cleanup. Public-safety scan passed.

**Completed follow-up:** bounded identity/layered-codec campaign under `dev/`.
The prior non-AES gap manifest contains six Aptina byte keys absent from the
corrected AES manifest. New identity fields were not all included in hashed or
paired derivations. These are coverage gaps, not evidence of a key. Frozen cap
captures remain excluded; no device or server access is part of this campaign.
All 422,419 configurations completed: 300 six-key AES, 155,849 identity-gap,
263,662 layered-codec, and 2,608 controls. There were 1,292 identity-key codec
parses and one random-body-control parse, but **zero same-role cross-acquisition
candidates**. No intermediate, reflectance or absolute vectors were recovered.
Stage 1's sole parse consumed 20 bytes and left 1,772 unexplained trailing bytes;
it failed all ten additional exploratory confirmation blobs. See
`analysis_output/bounded_identity_20261004_run/assessment.json` and
`BOUNDED_CAMPAIGN.md`. Do not repeat this manifest without a new hypothesis.

**Established**

- The server computes reflectance as a sample-domain quantity divided by a
  white-domain quantity. The response table is multiplicatively separable to
  ~1e-16 with no fitted parameters, and swapping roles exposes a stable non-unity
  self-response factor C(λ) (1.022–1.055 over 740–1070 nm).
  [separability](analysis_output/recovery_20261003_followup/separability_live/verification.json),
  [symmetry](analysis_output/recovery_20261003_followup/symmetry/self_response_factor.json)
- Dark handling is not additive, not a per-band affine map, not a shared scalar gain,
  and C is not a low-order polynomial.
  [dark affine](analysis_output/recovery_20261003_followup/dark_affine/comparison.json),
  [response structure](analysis_output/recovery_20261003_followup/response_structure.json)
- Sample, dark, white and white-dark blobs are integrity-protected: any tested
  change to the second header word or the body gives `Bad_sample_signature`. The
  status bit in header word 0 is not covered (accepted in all six roles), and
  gradient edits, omission and zero-fill are accepted, all with an unchanged
  spectrum. ([`ciphertext_oracle/`](analysis_output/ciphertext_oracle/),
  [RESULTS](analysis_output/recovery_20261003/RESULTS.md))
- Blob = 8-byte header (word 0 type/status, gradients carry 110; word 1 fresh per
  blob) + fixed-size body: 1792 B sample/dark, 1648 B gradient on `-e` firmware,
  1408 B gradient on `-o`. Body ≈ 7.9 bits/byte, positionally featureless; 30 captures
  of an unchanged target are at 0.49986 bit distance from each other.
- **No supervised leakage.** Sample and dark bodies carry no fixed-position
  information about the server spectrum: 96 permutation tests (bits, bytes, u16
  LE/BE × mean, log-mean, slope, PC1–3 × max-|r| scan and grouped-CV ridge, 92
  records, 10,000 within-acquisition permutations) give 4.2% below p = 0.05,
  median p 0.50, best held-out R² below zero. The same detectors find a single
  fixed-position u16 field carrying the signal level at p ≈ 0.002 on synthetic
  fixtures of this size, and never flag the encrypted twin.
  [leakage](analysis_output/leakage_20261003/leakage.json). This points away from
  a plain fixed-rate coder of counts and toward encryption (or a coder whose
  fields do not sit at fixed positions); it is not proof of encryption.
- **The gradient is just as opaque.** Its body matches sample/dark on every statistic
  (entropy at the random expectation, flat histogram, no positional or run structure,
  no repeated blocks), sits 0.4999 bits from the same scan's sample body (this does
  not establish independence or exclude derivation), and shows no spectral leakage
  (48 tests, Bonferroni p 1.0). The
  server simply does not use it. [gradient](analysis_output/gradient_20261004/gradient.json)
- **Size arithmetic** ([size constraints](analysis_output/size_constraints_20261004/size_constraints.json)):
  no table or body is a whole number of 331 entries at any width, so the tables are
  not plain per-band arrays. `centers` (96 B) splits into 12 × 8 B, consistent with
  one record per receptor. No body splits 12 ways at ≥16-bit width or fits 12-bit
  packing; all are multiples of 16 B. The `-e`/`-o` gradient difference is 240 B
  (15 blocks).
- **"Intermediate scan" means a batch member, not partial decoding.** No DEX method
  references `/external_sdk/intermediate_scan` (a `Config` constant named
  `API_V1_UPLOAD_SCAN`, beside `API_V1_BATCH_ANALYSIS`). In 1.5.19 the consumer
  route `/v1/consumer/intermediate_scans/batch/` goes through the generic API helper
  next to an Applet flag `show_intermediate_results` and the `batch_id` /
  `analyze-batch` / `aggregated-result` workflow: per-scan results within a
  multi-scan batch. Name/co-location inference, not a traced response model.
  [sdk endpoints](analysis_output/sdk_endpoints_20261004/sdk_endpoints.json)
- **Device identity is constant; encoding works with blank BLE-ID text fields.**
  `0x89`/`0x93` write the BLE-ID serial prefix / i2s tag (README §3). An empty-payload
  probe wiped both on 2026-09-07 and they were restored on 2026-10-04. Blobs captured
  while they were blank (2026-09-07 18:50 series) were decoded by the server, given
  the real `device_id` and tag in the request. This does not exclude cached identity
  or a separately stored copy entering the transform. `device_id`, `dsp_id`, the Aptina
  field, `ble_id` and the BLE MAC `B4:99:4C:59:66:01` are identical from 2023 to
  2026-10-04 (`01_rawdata/probe_logs/ble_id_restore_20261004_*`). The phone MAC is
  not a key: USB captures sent with a synthetic MAC decode.
- Every supplied app path (Java 2017, Lab 1.3.12, Flutter 1.5.6 ARM64, 1.5.19 ARM32)
  is a Base64 pass-through. No client-side decoder exists in any supplied APK.
- No firmware body is available: USB exposes file headers only (`0x81` is a
  host-to-device write); the upgrade endpoint returns `new_version: null`, including
  when asked as a firmware-135/136 device (dsp_op `0x88`/`0x87`, all four files old,
  and the 1.2.6.476 app client; 2026-10-04,
  [old-firmware probe](analysis_output/firmware_old_version_20261004/campaign_summary.json)).
- Reference truth: 92 records in `02_processed_data/` carry a spectrum the server
  returned for exactly those bytes; 42 of them additionally carry the 2020/21
  spectrum. Six fresh cap scans (18 blobs) are **frozen** for prospective
  confirmation ([manifest](analysis_output/recovery_20261003_followup/fresh_reference_validation.json)).

**Not established**

- Whether the body is encrypted, or coded with position-shifting (entropy-coded)
  fields. Plain fixed-position coding is now disfavoured (see leakage above).
- Where the transform runs: BF512 DSP, CC2540 BLE SoC, or (decoding side) the server.
- Key architecture, absolute sample/white domain vectors, pixel geometry, table contents.

**Hardware** (full reference with all photos: [`../documentation/HARDWARE.md`](../documentation/HARDWARE.md);
desk review in
[`HARDWARE_ACQUISITION.md`](../documentation/HARDWARE_ACQUISITION.md#teardown-photo-review-2026-10-04)):

- **DSP:** `ADSP-BF512 KBCZ-3`, 300 MHz BGA, with **no on-chip program flash** (datasheet
  Rev E ordering guide). It boots via BMODE straps from external parallel/SPI flash, an
  SPI0 or UART0 host, ≤3 KB OTP, or SDRAM. OTP cannot hold `dsp_op`. Lockbox exists;
  whether it is used is unknown.
- **No standalone flash chip visible** on either face. Legible parts: SDRAM, CC2540F256
  (labelled "9A"), probable ADP5062 charger, two unidentified small QFNs.
- **Hypothesis (unverified):** the CC2540 stores the DSP images and boots the BF512 as a
  host. All reported files together (176,861 B) fit in its 256 KB flash.
- **CC2540 debug-lock state is unknown.** It cannot be read from photos or over USB.
  Debug pins: P2_1 = DD (pin 35), P2_2 = DC (pin 34), plus RESET_N. No labelled header is
  visible; four castellated edge pads by `TP802` are a candidate.
- **Sensor:** 12 receptors in a 3 × 4 grid (filters, apertures of differing size, lenses)
  over a wire-bonded array. The module flex carries its own `FW:9216` sticker.

## Open tasks, ranked

### 0c. HarvestMaster / Mirus software audit (in progress, started 2026-10-09)

New non-teardown route, never examined before. HarvestMaster (Juniper Systems) sells the
**H3 GrainGage**, a combine-mounted grain gauge with an embedded SCiO sensor, driven by the
Windows application **Mirus** plus an **H3 plugin** and a public **SCiO Troubleshooting
Utility** (harvestmaster.com support articles 14646, 14648, 17012).

- **Hypothesis:** a combine often has no connectivity, so this vendor integration is the most
  plausible place for an offline decoder, an embedded key, or shipped SCiO firmware images
  (which would close the firmware gap). A Windows build is likely .NET and decompiles cleanly,
  unlike the Flutter AOT apps.
- **Method:** bounded automatic evidence-linked downloads are now authorized (five packages,
  512 MiB each, 2 GiB cumulative); static extraction only (no installer
  run, no activation or registration); workspace `private/harvestmaster/` (git-ignored).
  Triage with `scripts/audit_harvestmaster.py` (vocabulary sweep, firmware-header size and
  checksum match, calibration-table and body-size constants), then decompile and trace one
  capture path.
- **Stop conditions:** (A) local decoder or key → port it and validate (`validation.py`, 92 owner
  pairs + 3 fw-138 pairs, 1e-6, then the frozen cap scans); (B) firmware bodies → compare with the
  known headers, then disassemble with a Blackfin target; (C) cloud pass-through, same as the
  phone apps → record it under "Do not repeat" and check for cached known-plaintext pairs.
- **Result so far** ([FINDINGS](analysis_output/harvestmaster_20261009/FINDINGS.md)):
  - Mirus 4.6.11, Mirus 5.0.0 and the SCiO Troubleshooter 1.2.0 are thin REST clients to a
    separate local Windows service, **"SCiO Service"** ("A SCiO sensor sample analysis service",
    v2.011.013.5, `localhost:8080/v1/`, serial-to-USB to the sensor).
  - Vendor support recommends .NET 8. The actual service runtime and location of
    spectral processing remain unverified; local storage does not prove local decoding.
  - It has not been found in inspected payloads or through the bounded public search.
    This does not exclude an uninspected archive, dependency or customer distribution.
  - **Next:** obtain the "SCIO Services installer" (HarvestMaster field service, an H3 owner, or
    an archive), then audit it with the same script.
  - Caveat: the H3 sensor may be a different hardware generation from our BLE units.

#### Acquisition mechanism found (2026-10-09)

The H2 NIR Upgrade Installation Guide **31360** (`harvestmaster.com/data/support/31360 H2 NIR
Upgrade Installation Guide.pdf`), §1.7 "Connect to Mirus", documents how the service is installed:

> 1. Download and install Mirus 4.5.0 or above. 2. Enable the H3 Plugin. **3. Install the SCiO
> Service for the sensor. Note: Each sensor has its own activation link. If you have not yet
> received your link: a. Go to harvestmaster.com/support. Tap My Product. b. Tap SCiO License
> Renewal.**

So the installer is **not a public file**: it is delivered **per sensor via an activation link**,
self-served through the HarvestMaster support portal (**My Product → SCiO License Renewal**). This
is consistent with the campaign's and the filename-probe's failure to find any public URL. On
`harvestmaster.com/support`, "My Product" → **SCiO License Renewal** links to
`/products/software-request`, which is a **"SCiO Software Request" form** (inspected 2026-10-09 via
the browser pane, not submitted). Its fields: name, company, email, phone, **SCiO Sensor Serial
Number**, **GrainGage Serial Number**, desired license start date, combine name. There is **no
generic installer download** on the portal — it is a human-processed request gated on both a SCiO
sensor serial and an H3 GrainGage serial; HarvestMaster then emails back the per-sensor activation
link. Submitting it is outreach (off-limits here) and needs H3 serials we do not have. So the
self-service web route is a dead end for our consumer BLE units. Our consumer BLE units (fw-138/fw-147) are not H3 GrainGage OEM sensors, so this
self-service route likely does not apply to them without an H3 registration. Realistic paths now
narrow to: (a) an H3-owning institution that already holds the installer/activation link, or (b) if
an H3 sensor serial is available, the SCiO License Renewal flow itself (delivers the per-sensor
link). Not attempted here per the no-outreach constraint.

#### Ways to obtain the SCiO Service (still open)

Identifiers to search for:
- Windows service name **`SCiO Service`**, described as *"A SCiO sensor sample analysis service"*;
  the version seen is `v2.011.013.5`.
- HarvestMaster calls the installer the "SCIO Services installer".
- The REST API at `localhost:8080/v1/` exposes the JSON fields `scio_is_connected`,
  `port_defined_by`, `last_data_sync` and `client_reasons`.
- The vendor may name it differently: try Consumer Physics, `scionir`, `CP`, `SCiONIR`,
  `ScioAgent`, `scio-edge`, or "sample analysis".

1. **Wayback Machine.** Scripted access is blocked from the agent, so run these in a browser.
   - Open the URL index queries:
     - `https://web.archive.org/cdx/search/cdx?url=harvestmaster.com/data/&matchType=prefix&fl=timestamp,original,length&collapse=urlkey&limit=50000`
     - The same with `url=` set to `junipersys.com/`, `junipersystems.filecamp.com/`, `scionir.com/`,
       `consumerphysics.com/` and `dev.scionir.com/`.
   - Search each result page (Ctrl+F) for `scio`, `.msi`, `.exe` and `.zip`.
   - The browser UI does the same: `https://web.archive.org/web/*/harvestmaster.com/data/*`, then
     filter by "scio".
   - Also open the archived copies of support articles 17160 and 17179. Older revisions may have
     linked the installer directly.
2. **Ask HarvestMaster field service** (hmtechsupport@junipersys.com, +1 435-753-1881). The owner
   sends this, not the agent. Ask for the "SCIO Services installer" for the H3 GrainGage. They
   may require an H3 serial number.
3. **Find an institution that runs an H3 GrainGage.** Typical users are seed breeding programmes,
   agricultural universities and research stations with plot combines; an ETH or Agroscope field
   station is worth asking. On their tablet the installed service can be copied without
   reinstalling:
   - Find its path with `sc qc "SCiO Service"` or
     `Get-CimInstance Win32_Service -Filter "DisplayName like '%SCiO%'" | Select PathName`.
   - With permission, copy the service executable and referenced libraries and
     shareable models/calibration assets only. Do not copy credentials, licence
     secrets, customer/GPS databases or unrelated logs indiscriminately.
   - Note that the local scan store may itself pair raw blobs with results, which would be known
     plaintext.
4. **Ask SCiO / Consumer Physics directly** (scionir.com contact or support) for the Windows
   service or an offline SDK for legacy units. Frame it as e-waste and legacy-device support.
5. **Code and file search engines:**
   - GitHub code search for `scio_is_connected`, `"SCiO Service"` and `localhost:8080/v1/scan`;
     an integrator may have published a client or a copy.
   - VirusTotal search by name (`name:ScioService`, `"SCiO Service"`). Metadata such as file
     names, signer and version is visible without a premium account, even if the download isn't.
   - Web search for `"v2.011.013"` and `"sample analysis service"`.
6. **Juniper filecamp shares.** Customer-facing installers are distributed as
   `junipersystems.filecamp.com/s/d/<token>` share links. Watch for a share link in any manual,
   support article or reply from support.
7. **Do not** run the installer once it is obtained. Use static extraction only, then
   `scripts/audit_harvestmaster.py` and `ilspycmd`. Trace `POST /v1/scan` → serial read →
   decode → model. Never activate a licence or register.

### 0b. Cross-device decode push (done 2026-10-08)

Three probes on the cross-device paired data (RECOVERY_STATUS §"Cross-device decode push"):
**two-time-pad** — no keystream reuse (the one no-key break-chance, closed); **cross-device
fingerprint** — identical random-like body statistics across 5 devices / 4 generations (one
global algorithm); **fw-138 separability** — the server's sample/white separability generalises
to the contributor's unit (role-swap accepted, C≈1.00). Net: **no offline decode**; the body is
confirmed consistent with per-blob-randomised encryption; the decisive input stays firmware or
known plaintext (raw intensities), neither obtainable offline without disassembly. The
software-only route is exhausted on present evidence. A *powered* second-device leakage test
awaits ≥20–30 fw-138 scans (requested from the contributor); even then it needs a plaintext
handle to decode. Scripts: `probe_twotime.py`, `probe_cross_device.py`, `probe_fw138_separability.py`.

### 0. fw-138 unit: ingested, replayed, included (done 2026-10-08)

A second owner contributed an older **fw-138** unit (see
[`analysis_output/foreign_fw138_20261008/FINDINGS.md`](analysis_output/foreign_fw138_20261008/FINDINGS.md)).
Firmware request → `null` (below). White reference + three samples (pine/tomato/skin) were
ingested as canonical records and replayed. After a window-covered re-take, the corpus now has
**3 fw-138 pairs: skin + 2 pine wood** (both pine re-take attempts decoded, 200). **Tomato
still fails** the physics/quality gate (422 InvalidScan, first take and both cut-flesh re-takes)
— a material limit; its raw record is kept. The foreign device is included across the
multi-device research readers (`leakage.corpus_groups`, `validation.load_pairs`,
`transform_class` per-generation); live/physical ops stay owner-only. `obj_t` is live on the
fw-138 unit, 0 on the fw-147 unit (confirmed; `ScioDevice.read_object_temperature()` added).
**Comparison lead:**
`dsp_boot`/`dsp_dec` have equal reported size/version but differing checksum fields
(−673, −26). This does not establish a byte-sum algorithm, a small changed region,
personalization or a key location. If bodies are obtained, compare their actual
bytes and code before interpreting the differences.

The hardware tasks below need a separately authorised session with the device
opened (the housing is not designed to be reopened). Bounded software coverage
corrections and independently supplied firmware artifacts remain non-teardown routes.
Nothing below may write, erase,
reset or change straps or protection.

### 1. Passive boot-traffic capture

- **Goal:** record the DSP's boot stream as it crosses a bus at power-on. Whatever
  BMODE selects (SPI flash, SPI0 host, UART0 host), the LDR data must travel over
  SPI0/UART0 unless it comes from the ≤3 KB OTP. This route is read-only and needs no
  unlocking.
- **First:** with the board unpowered, find accessible test points on the BF512's
  SPI0/UART0 nets and the CC2540's matching peripheral pins. The BF512 is a BGA, so this
  needs continuity tracing, not photos.
- **Validate** the capture against the known headers: `dsp_boot` 7,284 B, `dsp_dec`
  14,600 B, `dsp_op` 32,628 B, v147, checksum 4151168 (README §5), and parse it as LDR
  (`scio_offline.firmware`).

### 2. CC2540F256 debug-lock status

- Locate DD/DC/RESET_N (continuity from pins 35/34), then use a CC Debugger-class tool's
  status/ID readout only. Verify the status command against TI SWRU191 before use.
- **Never accept a chip-erase prompt.** If the chip is locked, record that and stop.
- If it is unlocked, a read-only flash dump would cover the BLE runtime, any AES/signing
  material and, under the hypothesis above, the DSP images.

### 3. External flash or BF512 JTAG (only if task 1 points there)

- HARDWARE_ACQUISITION.md routes A and B, unchanged.

## Do not repeat

Each is a bounded negative with saved evidence; repeat only with a genuinely new
hypothesis that the earlier run could not have seen.

| Route | Evidence |
|---|---|
| Firmware-header-derived AES/CMAC/HMAC keys and diagnostic deltas | [checksum campaign](analysis_output/checksum_headers_20261008_run/REPORT.md); current-to-historical association remains exploratory |
| Identifier-derived keys, AES (≈220k configurations, corrected framing) | [key_search_confirmed](analysis_output/recovery_20261003/key_search_confirmed.json), [foreign](analysis_output/recovery_20261003/key_search_foreign.json) |
| Identifier keys × TEA/XTEA/ARC4/ChaCha20/TripleDES/Blowfish/Camellia, incl. the MAC, field *pairs*, the full 16-byte Aptina id + upper half, and the serial prefix (2950 keys; top repeatability 0.125, below the 0.150 random-control ceiling) | [identifier_key_gap](analysis_output/identifier_key_gap_20261004/identifier_key_gap.json) |
| Generic compression and word-swap/bit-reverse representations | [compression_only](analysis_output/recovery_20261003/compression_only.json), [representation_codecs](analysis_output/recovery_20261003_followup/representation_codecs.json) |
| Headerless baseline-JPEG Huffman parsing | [jpeg_entropy](analysis_output/recovery_20261003_followup/jpeg_entropy.json) |
| Unknown-polynomial CRC, seeded Murmur/FNV/DJB2 | [unknown_crc](analysis_output/recovery_20261003_followup/unknown_crc.json), [seed](analysis_output/recovery_20261003_followup/unknown_checksum_seed.json) |
| APK/DEX/native/resource/container scans for firmware or tables | [routes v2](analysis_output/recovery_20261003_followup/firmware_routes_summary_v2.json), [containers v2](analysis_output/recovery_20261003_followup/firmware_containers_v2.json) |
| 1.5.19 gradient diagnostic labels (Base64 length checks only) | [validation_trace](analysis_output/recovery_20261003_followup/validation_trace.json) |
| Mock fixtures (duplicates of 2017 source constants) | [mock comparison](analysis_output/recovery_20261003_followup/mock_constant_comparison.json) |
| Server bit-flip/mutation oracles (closed by the signature) | [`ciphertext_oracle/`](analysis_output/ciphertext_oracle/) |
| Firmware-endpoint polling | [server recheck](analysis_output/recovery_20261003_followup/firmware_server_recheck/summary.json) |
| Firmware offer for a genuine fw-138 device (bare `20150812` tag) | [fw-138 findings](analysis_output/foreign_fw138_20261008/FINDINGS.md) |
| Public HarvestMaster software (Mirus 4.6.11, Mirus 5.0.0, SCiO Troubleshooter 1.2.0, all plugin bundles): thin REST clients, no decoder, key or SCiO firmware | [harvestmaster findings](analysis_output/harvestmaster_20261009/FINDINGS.md) |
| Pairing a foreign sample with the owner's white reference (tested combinations rejected) | [fw-138 findings §2](analysis_output/foreign_fw138_20261008/FINDINGS.md) |
| Supervised leakage, fixed-position linear (bits/bytes/u16) | [leakage](analysis_output/leakage_20261003/leakage.json) |
| Gradient as a weaker or derived blob | [gradient](analysis_output/gradient_20261004/gradient.json) |
| Size-only layout fitting (12 receptors, 331 bands) | [size constraints](analysis_output/size_constraints_20261004/size_constraints.json) |
| `intermediate_scan` as a decoding endpoint | [sdk endpoints](analysis_output/sdk_endpoints_20261004/sdk_endpoints.json) |
| Looking for a standalone flash chip in the teardown photos | [teardown markings](../documentation/teardown/README.md#markings-read-from-these-photos-2026-10-04) |
| Firmware offer as a firmware-135/136 device; 2-frame scan with the 1.2.6.476 client (null; spectrum identical) | [old-firmware probe](analysis_output/firmware_old_version_20261004/campaign_summary.json) |
| Same-target bit agreement | README §4 (0.49986 bit distance over 30 captures) |

Documentation: `dev/README.md` was reconciled with this file on 2026-10-04 (fixed
container vs fixed rate, JPEG scope, integrity-check scope, firmware endpoint,
key-architecture framing, acceptance gate).

## Closed for this owner

- The original 2015 phone and its app-data backup (unavailable).
- Lab-portal `sample_raw`/`wr_raw` export (no working credentials).
- USB body readback: headers only; `FILE_DOWNLOAD` is a write.

## Ground rules

- `01_rawdata/` is append-only. `src/` and `dev/` stay decoupled.
- Vendor-server requests need the owner's explicit approval, ≥20 s spacing, and a
  saved plan before sending. No device writes, resets or protection changes.
- Private material (decompiled sources, raw pools, responses) goes in
  `dev/private/` (git-ignored).
- Tests: `python -m pytest tests` and `python dev/scripts/test_without_network.py`.

## References

- [RECOVERY_STATUS.md](RECOVERY_STATUS.md), [NATIVE_ANALYSIS.md](NATIVE_ANALYSIS.md),
  [DEVICE_FUNCTION_REFERENCE.md](DEVICE_FUNCTION_REFERENCE.md)
- [`../documentation/HARDWARE.md`](../documentation/HARDWARE.md) (hardware reference, photos),
  [`../documentation/HARDWARE_ACQUISITION.md`](../documentation/HARDWARE_ACQUISITION.md)
- SparkFun teardown with board photos:
  <https://learn.sparkfun.com/tutorials/scio-pocket-molecular-scanner-teardown-/all>
