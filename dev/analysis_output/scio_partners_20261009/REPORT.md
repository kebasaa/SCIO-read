# Alternative SCIO OEM/software distribution routes — 2026-10-09

## Result

Verified alternative SCIO applications and one historical embedded hardware OEM,
but **no second manufacturer with a verified downloadable offline SCIO decoder
service**. Cloud prediction, disconnected scan capture, local spectrum conversion
and export of already-calculated results must remain separate capabilities.
User clarified that packaged offline conversion is the priority.

Research used 39 web search/page operations, independent of the previous
HarvestMaster installer campaigns. No binary downloads, analysis endpoint calls,
account creation, activation, credential use, device operations or correspondence.
Public sources were inspected, not executable software. Search engines returned
many unrelated SCIO products; negative query results are weak coverage evidence.

## Candidate map

| Candidate | Verified connection and computation evidence | Artifact target and priority |
| --- | --- | --- |
| Changhong H2 / Analog Devices | Consumer Physics' January 2017 announcement confirms an embedded SCIO sensor and plans for a developer SDK. It does not establish offline decoding or continued availability. | Highest distinctive hardware lead: legitimate H2 system/OTA images, preinstalled sensing APKs, native libraries, vendor sensor service and bundled firmware. No verified download located in this research. |
| Cargill Reveal | Official Cargill quick-start describes SCIO sensor/cover and cloud-based forage calibrations. Android package com.consumerphysics.cargill.reveal, iOS id1246119692. | Best identified alternate app package, but weaker offline target. Compare hashes/code before another large decompile: existing Analyzer APKs already contain Reveal assets. |
| Eurofins Agro UK / Harpers Feeds | Joint 2019 release explicitly describes SCIO plus Eurofins calibrations and cloud-based service. | Historical app/SDK is a possible implementation comparison; no separate offline executable or app package ID verified here. |
| DietSensor | Vendor instructions identify Consumer Physics SCIO and a CP account. FAQ describes internet transfer for results. | Original-generation companion app could reveal framing/SDK changes, but there is no offline-decoder evidence. Current SCIO functionality not tested. |
| Seedburo, VRO, Marconi / EME Science | Confirmed SCIO products; official product descriptions largely describe cloud-connected mobile workflow. Partner listing includes resellers and integrators together. | Low priority for a unique decoder package without a vendor-specific app/service/download finding. Do not call every listed partner a hardware OEM. |
| CropX / current SCIO | CropX's August 26, 2026 announcement confirms acquisition of SCIO, including integrated sensing technology. | New current ownership/integration documentation lead, not proof of an existing public offline SDK or legacy-device support. No outreach proposed as a required step. |

## Primary evidence

- [Consumer Physics announcement of Changhong H2](https://www.prnewswire.com/news-releases/changhong-h2-worlds-first-molecular-identification-and-sensing-smartphone-with-a-miniaturized-integrated-material-sensor-unveiled-at-ces-300385325.html).
  This is a manufacturer-supplied press release, not confirmation that a ROM or
  SDK download remains available. Different integrated sensor hardware may have
  different framing, firmware or calibration from the owner's consumer device.
- [Cargill quick-start](https://www.cargill.com/doc/1432095639329/reveal-user-guide.pdf),
  five pages; text inspected. No PDF rendering/layout conclusions made.
  [Google Play listing](https://play.google.com/store/apps/details?id=com.consumerphysics.cargill.reveal)
  identifies SCIO Solutions LTD as publisher and a subscription requirement.
  Listing existence/update metadata does not verify backend operation.
- [Reveal iOS history](https://apps.apple.com/au/app/cargill-reveal-utilizing-scio/id1246119692):
  version 1.1.1 (2018) says deferred results follow restored connectivity;
  1.1.5/1.1.7 (2019) mention offline results/scanning. Those later phrases do not
  prove a local decoder. Version 1.5.8 (2025) adds SCIO 2 support, making separate
  generation checks necessary. No app was installed or scan submitted.
- [Eurofins joint release](https://cdnmedia.eurofins.com/european-west/media/1927096/ef-cp-press-release_31012019.pdf),
  January 30, 2019: SCIO hardware and Eurofins model calibrations, cloud service.
  Two-page text inspected; no inference from visual layout.
- [DietSensor SCIO setup](https://www.dietsensor.com/using-scio-scanner/)
  and [FAQ](https://www.dietsensor.com/faq/). Historical instructions remain
  published but are not proof of today's subscription/device availability.
- [SCIO partner list](https://scionir.com/partners/),
  [VRO SCIO Mini](https://vroagtech.com.br/produto/scio-mini/),
  [Marconi SCIO Cup](https://www.marconi.com.br/produto/1311/scio-cup-%E2%80%93-nir-analisador-de-materia-seca),
  [Seedburo product collection](https://seedburo.com/collections/new-products).
- [SCIO integrated combine page](https://scionir.com/sensors-network/hardware-integrations/)
  describes local storage followed by cloud sync; does not identify another
  downloadable OEM decoder. [Dairy page](https://scionir.com/solutions/dairy/)
  explicitly defers disconnected results until reconnection. Likewise the
  [Cup quick-reference](https://sciolatam.com/wp-content/uploads/2020/07/SCiO-Cup-Forages-Quick-Reference-Guide-V1.3.pdf)
  defines offline mode as capturing fingerprints for later cloud analysis.
- [Integration layer](https://www.consumerphysics.com/integration-layer/)
  advertises fetch/realtime/mobile interfaces, not an exposed local spectrum SDK.
- [CropX acquisition announcement](https://cropx.com/2026/08/26/cropx-acquires-scio/).
  Ongoing enterprise SCIO activity does not contradict discontinuation of the
  original consumer offering; do not infer that its older backend is restored.

## Local overlap check

Read-only check of `dev/analysis_output/recovery_20261003/apps.json` confirms
`assets/images/reveal/cargill_logo.png` inside the recorded members of both
Analyzer 1.5.6 and 1.5.19 XAPK inventories. Existing 1.5.6 Flutter analyses also
contain reveal branding/loader strings. This supports shared application assets,
**not** binary identity or an already completed audit of the Cargill scan path.
The supplied APK directory has no separately named Reveal, DietSensor or Changhong
package among its nine listed archives. Nothing was modified in source archives.

## Recommended follow-up, artifact first

1. Locate a legitimately public Changhong H2 firmware/OTA package or sensing SDK
   through exact model/support references. Be careful not to confuse this phone
   with HarvestMaster H2 hardware or another Changhong model. Preserve origin,
   signatures/hashes, and statically extract only under dev/private. Stop at
   authentication/access restrictions; do not buy hardware merely on this lead.
2. Trace its sensing app to any native/system service and DSP firmware asset.
   This is promising because embedded integration may expose a different software
   boundary, not because it proves decoding moved into Android. Follow actual
   raw acquisition/calibration/transform callers before harvesting constants.
3. If Reveal packages become legitimately available, compare SDK/native library
   hashes and scan-path implementations against existing Analyzer first. Target
   code/data deltas, not another full sweep of shared assets. Historical and
   newer SCIO 2 records remain separate. Offline-labelled UI is insufficient.
4. Pursue other partner download pages only where a concrete OEM application,
   desktop runtime, embedded controller or firmware distribution is named.
   Mere reseller membership or a web/cloud API is not enough to prioritize it.
5. For any claimed local conversion, require a new scan to yield an intermediate
   or spectrum with network disabled. Cached predictions and delayed cloud jobs
   do not pass. Consumer compatibility still requires the frozen metadata-aware
   paired-record validation gates; no arbitrary byte interpolation/rescaling.

Bosch X-Spect appeared in speculative comparisons, but no primary SCIO integration
confirmation was established in this research. ScioSense, SCIO Automation,
biofeedback SCIO/Clasp, Spotify/Thales software and geographic SCIO service pages
are not verified Consumer Physics decoder leads. No packages downloaded from them.

No decoder or key recovered; this report supplies acquisition leads, not a
working alternative analysis endpoint or confirmed second offline installer.
