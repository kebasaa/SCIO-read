# Local embedded dependency/resource audit — 2026-10-09

## Outcome

No SCIO service installer, supported scan-decoding transformation, SCIO firmware
body or evidence-backed scan key was recovered from this enumerated local audit.
This is a bounded result, not proof that all vendor packages lack them.

The previously compressed dependencies are now accessible. Of 160 distinct
recovered payload hashes, 93 were absent from the earlier broad inventory.
Therefore earlier searches of extracted filenames did not cover these bytes.

## Coverage and reproduction

Starting revision: `680d139ac8663276e97c11554b8033449f508965` with pre-existing
working-tree changes; new research scripts are not part of that revision.
All vendor material remains in the ignored private research workspace.

- 170 payload records, 160 distinct hashes: 151 managed-PE records and 19 other
  records, including symbols/configuration/XML. Counts are not distinct DLL counts.
- Costura framing established from `serviceapp/Costura/AssemblyLoader.cs:60` in
  the preceding campaign's decompile: raw DeflateStream, then Assembly.Load.
  Only the stream transformation was reproduced; Assembly.Load was not invoked.
- 33,425,872 bytes expanded/copied by the Costura/older-resource step; zero
  malformed streams. Troubleshooter bundle separately dumped statically with
  `ilspycmd --disable-updatecheck -d`.
- 26 distinct HM/JS vendor assembly hashes decompiled, including localized
  resource assemblies. Main SCIO call sites and generic licensing, serialization,
  schema resources and firmware references inspected. Third-party libraries were
  hashed/triaged, not exhaustively decompiled or instruction-audited.
- 13,488 resx entries across prior installer decompiles and new dependency
  decompiles; 25 binary entries, 12 distinct binary hashes, zero nested ZIPs.
- Non-resx vendor assets: 216 XAML files, two PNGs, two JPGs. See `coverage.json`
  for every path, length and hash. No additional extracted executable/archive
  resource among these files. XAML/graphics are inventoried, not runtime-loaded.
- 135 source-resource hashes and all 170 recovered payload hashes reverified.
  Resx sources checked unchanged during inspection. No production/source edits
  made by this campaign; pre-existing dirty source capture left untouched.

Run the scripts with bytecode disabled and temporary directories beneath dev:

1. Dump the existing troubleshooting executable with ILSpy's static bundle mode.
2. `dev/scripts/audit_embedded_harvestmaster.py` (exclusive creation; use a fresh
   campaign workspace for a repeat, never overwrite historical results).
3. Statically decompile unique HM/JS managed payloads with ILSpy project mode,
   naming directories by assembly filename plus SHA-256 prefix.
4. `dev/scripts/inspect_harvestmaster_resx.py --output resource_manifest_v2.json`.
5. `dev/scripts/summarize_harvestmaster_resources.py`.

The first resource manifest is preserved; v2 includes the completed vendor batch.
Manifests retain hash provenance and repository-relative paths, not string values.

## Supported findings and source anchors

Anchors below are relative to the private campaign's `vendor/` directory.

### SCIO boundary

`hm.devices_49a52165/HM.Devices.Scio/ScioApiClient.cs:54` selects localhost
8080/v1. Scan sends plot metadata/GPS/GrainGage ID and receives constituent
predictions; normalization changes constituent names, not spectral amplitudes.
`HM.Devices_e0ac1e31/HM.Devices.Scio/ScioApiClient.cs:27` independently retains
the same endpoint and calls it the offline service API in documentation.
These clients do not implement the service or expose a raw-to-spectrum function.
The word offline in documentation does not establish where every computation
inside the absent service or OEM sensor occurs, or consumer-device compatibility.

`hm.vcg_9399afe3/HM.Devices.VCG.Scio/ScioModule.cs:289` calls the service scan;
`:704` stores results; `:467` applies an additive constituent-specific offset
except during the stated calibration states. This is downstream prediction
adjustment, not a recovered reflectance calculation. `:522` checks service/sensor
connection then calls connect; no installer provisioning in this function.

`HM.Devices_e0ac1e31/HM.Devices.Scio/ScioApiClient.cs:72` documents that
`export_scans` creates a ZIP and deletes scan-history files afterwards. It must
not be treated as a harmless read-only diagnostic. No request was issued.

`hm.vcg_9399afe3/HM.Devices.VCG.Calibration/Step4ReferenceCap.cs` performs cap
self-test through the service and handles external-light/temperature failures.
Its restart path invokes the GrainGage moisture-sensor reset, not a consumer
SCIO USB/BLE command. No reset or hardware operation was performed.

### Assets and generic helpers

The six occurrences of `ggDefaultScriptHashes` decode as two distinct JSON
catalogs, each containing 147 records with FileName, GrainGageType, Hash, Version.
Names include CollectionSetup.py, Calibration.py, Plot.py and Tare.py. They are
hash/version catalogs, not script bodies, firmware or spectral calibration tables.
Only generated resource-property accessors were found for this resource name;
its complete runtime use has not been established.

Remaining binary resource names describe backgrounds/logos/GrainGage icons.
Serialized drawing objects are preserved opaque without BinaryFormatter or
vendor deserialization. Their type/name and absence of an executable/archive
signature are bounded classification evidence, not a proof against steganography.

`js.common_35a6793a/JS.Common.Licensing/ActivationValidator.cs:7` connects
CryptoSharp to registration/unlock validation, not scan bytes. Do not turn its
isolated constants into claimed SCIO keys or use them to bypass activation.

`js.common_35a6793a/JS.Common.Licensing/SoftwareVersionResponse.cs:24` parses
MessageXML/updates/versions; `:35` chooses ZIP/EXE update adapters from each
location field. `LicenseProvider.cs:258` gets this response through the generic
licensing provider. This is a real dependency/download path, but the location
comes from a response, not an embedded SCIO package URL. Credentials found in
vendor code are private, omitted from reports, and were not used.

`js.common.core_afa6d67d/JS.Common/SerializationHelpers.cs:38` compresses XML
serialization before Base64; `:63` decompresses before XML deserialization.
This generic object-serialization chain is not tied to opaque SCIO scan bodies.
`js.common_35a6793a/JS.Common.Data.Schema/SchemaUpdate.cs:134` reads SQL schema
resources by versioned name; not executable package acquisition.

## Verification and limitations

Seven new extraction/resource safety tests plus two retained archive tests:
**9 passed** with socket connections blocked. Coverage includes exact raw-deflate
recovery, limits, truncation/trailing bytes, Base64/XML safety and ZIP traversal.
Production suite unchanged: **116 passed**. A preliminary blanket socket-blocked
production run failed because Windows asyncio creates internal connected sockets;
that run is not a production regression result. The ordinary rerun passed.

No network/discovery requests, downloads, installer execution, licensing calls,
service startup, device commands or cleanup. Private inputs/evidence retained.
No claimed intermediate vectors, 331-band reflectance or absolute domain values.

The remaining acquisition gap is still the actual service distribution or an
authorized installed-service/cache artifact. This audit supplies no new concrete
public download URL. Third-party instruction analysis and opaque serialized
graphics remain outside exhaustive coverage, but there is no demonstrated SCIO
transform reference justifying treating them as decoder candidates yet.
