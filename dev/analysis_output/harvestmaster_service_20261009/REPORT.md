# HarvestMaster installer/service follow-up — 2026-10-09

## Result

No SCIO service installer, concrete service download URL, firmware body or
spectral transformation recovered in this bounded inspection. This is not proof
that none is publicly available or that the separate service decodes consumer
scans offline. Frozen spectra and source captures were not used or changed.

## Installer coverage and containment graph

`coverage.json` records all **88 Mirus 4 and 200 Mirus 5 payloads**, including
extensionless Burn `0` manifests. Every payload is present in existing extracts;
all available declared size/hash comparisons pass. Payload SHA-256 and original
package hashes are retained. `coverage_v2.json` additionally records code revision,
driver hash and limits; prior output is preserved.

| Source | Edge and target | Evidence / classification |
|---|---|---|
| Mirus 4 Burn | embedded MSI + .NET48, VC2008/2010, SQL CE, FTDI packages | Manifest `0`, attached `a0`–`a7`; embedded |
| Mirus 5 Burn | embedded MSI + desktop runtime 8.0.20 | Manifest `0`, attached `a0`–`a1`; embedded |
| Mirus 4 UI | bundled `.mpb` files → PluginManagerCore | `installer4/InstallerUI.ViewModels/BundledPluginsInstaller.cs:27`; local provisioning |
| Mirus 5 UI | bundled `.mpb5` files → dependency order → Install | `installer5/BundledPluginsInstaller.cs:54,158`; local provisioning |
| PluginManager 5 | InstallSingle → plugin.zip → copy files | `plugins5/HM.PluginManager/MirusPluginPackage.cs:572,664,737`; no download in this path |
| Mirus MSI | launch Mirus; EULA; directory/permission actions | Private `msi_tables.json`, seven CustomAction rows each; no ServiceInstall/ServiceControl tables |
| HM.Service helpers | GrainGage / VCG / CAN service commands | `service134/HM.Samples/ModuleInterface.cs:13`; `serviceapp/HM.ServiceApp.Helpers/DeviceModuleFactory.cs:8`; unrelated to the sought SCIO API implementation in inspected top-level code |
| Troubleshooter scan | ScioApiClient → localhost:8080/v1/scan | `troubleshooter/...MainViewModel.cs:476`; `troubleshooter_devices/HM.Devices.Scio/ScioApiClient.cs:24`; thin client |
| Troubleshooter DSP checks | SerialCanPort → GrainGage DSP firmware and connectivity | `...MainViewModel.cs:359,501`; not SCIO firmware extraction |
| H3 SCIO Soybean.xml | crop selector, constituent offsets, moisture-voltage points | Existing H3 plugin Curves file; not 331-band spectral calibration |

Source anchors are relative to private campaign `decomp/`; vendor sources remain
git-ignored. Dependencies are not all exhaustively decompiled. Native WiX custom
action implementations and every generic library instruction were not audited;
table targets and call sites bound the conclusions. No URL override or service
download was found in installer-specific code. Update callbacks inspected in
Detector are empty; plugin dependencies are checked locally, not fetched by the
traced installation path. No installer code was executed.

## Troubleshooter supplied by the user

The supplied external copy hashes to
`54b182c4bb669ee7a97715287b5ecb21cb73f493ceca3b7b6cdbcae87818c598`,
identical to the previously downloaded 1.2.0 utility. Fresh ILSpy decompilation
of its entry assembly and bundled HM.Devices confirms the same path. Its
firmware-series query is for the **GrainGage DSP**, not the consumer BF512.
The connectivity query uses index 8208 (0x2010), response specifier 67 and
data byte 0 equal to 2. These are OEM GrainGage facts, not commands to send to
the consumer SCIO. No device commands were sent.

## Acquisition and cleanup ledgers

New packages downloaded: **0**; cumulative download bytes: **0**. No concrete
new evidence-linked package qualified. No guessed filename or token requests.
16 discovery operations (9 search queries, 7 page/index opens), including failed
opens, were attempted; the maximum is 60, not a quota. Official articles 17179,
17160 and 14648, the HM800 archive 17012 and indexed H2/H3 manual references
supplied no service-installer link. Unrelated SCIO health/automation products
were rejected without downloading. The Wayback CDX index was inaccessible via
the available web tool; no bypass attempted. Public archive coverage remains
incomplete. Failed guide fetches do not exclude links inside that guide.

Primary references: [service installation advice](https://www.harvestmaster.com/support/article/17179),
[prerequisites](https://harvestmaster.com/support/article/17160),
[utility/plugins](https://www.harvestmaster.com/support/article/14648),
[HM800 archive](https://harvestmaster.com/support/article/17012).

Files removed: **0**; reclaimed space: **0**. Existing materials untouched.
All new decompilations and MSI Binary streams retained privately as evidence.
No installation, registration, activation, network SCIO API, or correspondence.

## Remaining acquisition gap and next decision

Need the executable implementing SCIO Service, its referenced transform libraries
and non-sensitive calibration/model assets. A real service build may reveal
local decoding, a remote/delegated path or sensor-side processing; .NET8 advice
does not establish the transform's language. OEM compatibility must be checked
against consumer raw framing and calibration before trying recovered constants.

Draft request (not sent):

> I am researching preservation of legacy SCIO measurements. Can you supply a
> legitimately shareable SCIO Services installer for static inspection, including
> its version and checksum? I will not activate or register an H3 unit. If the
> package cannot be shared, is an offline raw-to-spectrum SDK available?

For an authorized H3 owner, request only service executable/dependencies and
shareable calibration assets with permission. Exclude credentials, licence
secrets, customer/GPS databases and unrelated logs. Any execution or outreach
requires a separate decision.

## Interpretation corrections

Earlier claims that all HarvestMaster code never touches SCIO data, that the
decoder must live in this service, that .NET8 proves a managed decoder, and that
the service is absent from every public download were overbroad. The supported
observation is a thin client in the inspected call paths, with a separate
service still missing. No offline spectral decode is claimed.

## Verification and reproducibility

Run `python -B dev/scripts/audit_service_installers.py --output
dev/analysis_output/<new-run>/coverage.json` (exclusive creation). Run
`python -B dev/scripts/read_service_msi.py` only in a fresh campaign workspace;
Binary saves are exclusive and intentionally refuse overwrite. This reads MSI
database tables/streams without executing installation sequences. ILSpy was
invoked with `--disable-updatecheck`; no vendor program was run.

Six new audit tests passed, also rerun with Python socket connections blocked.
Full socket-blocked research suite: 278 passed (three existing Blowfish
deprecation warnings); its collection preceded the sixth new test, which was
verified in the targeted rerun.
Unchanged production tests: 116 passed. New private artifacts occupy 31,294,691
bytes (1,009 files), below 4 GiB. Shareable campaign outputs were scanned for
personal absolute paths and credential assignments; no such matches. A generic
drive-escape test is intentionally present, not a personal path.

Input original-package hashes were taken before inspection and rechecked through
the second coverage run. No production implementation was edited. The capture
and handover were already dirty at entry; the capture change is user-owned and
was not reverted. There was no comprehensive before-session hash baseline of
every production file, so do not claim that stronger verification was performed.

Scope limits: the cleanup and budget helpers are tested gates, not a deployed
automatic downloader/remover. No qualified package required either operation.
ZIP handling is preflight-only; existing extracts were reused, not re-extracted
under a new universally verified archive pipeline. Private MSI tables/binaries
and code are available for further static work. Archive discovery was bounded
but incomplete; do not repeat broad thin-client downloads without a new lead.
