# Renewed installer acquisition search — 2026-10-09

## Outcome

Actual SCIO service installer still not acquired. Twenty additional public
search/page operations completed, separately accounted from the earlier 60.
No download-qualified package URL, guessed filename requests, activation calls,
credential use, outreach, service execution or cleanup.

This attempt covered service/installer/setup queries, official HarvestMaster and
Consumer Physics/SCiO domains, GitHub-indexed service references, the HarvestMaster
knowledge-base link inventory, prerequisites, SCIO Q&A and utility documentation.
Search-result absence is not proof of absence; several restrictive queries
returned mostly unrelated products/geographic matches. They are weak negatives,
not valid exclusions of unindexed distributions.

## Findings

1. [H3 SCIO Q&A](https://harvestmaster.com/support/article/17161), dated 2 February
   2026, says model updates are supplied in new software builds. This supports
   targeting a **model-bearing customer service distribution**, rather than
   assuming the sought artifact is a generic driver. It does not establish that
   the executable itself is unique per device, contains a consumer decoder, or
   that its model/calibration tables are compatible with consumer scans.
2. [Installation error 1060](https://harvestmaster.com/support/article/17160)
   requires Windows 11 x64/.NET8 SDK in that advice, but exposes no service
   download. The non-www linked page succeeded after the www URL failed. Its
   error screenshot failed in the web tool and remains **uninspected**; no
   filename/host conclusion was drawn from it.
3. [Plugin/utility page](https://www.harvestmaster.com/support/article/14648)
   links the troubleshooting guide through Filecamp share
   `C0fdDn9VMaz96Ksx`. The web tool reported cache miss. This is a known exact
   public-share reference, not a guessed token; failure does not establish
   authentication requirements or absence of useful content. No token enumeration
   or protected endpoint request occurred.
4. Indexed consumer developer downloads describe mobile SDKs, not the Windows
   HarvestMaster service. SCIO Automation, biofeedback/Clasp products, Spotify's
   Scio and geographic service providers were rejected as unrelated without
   downloading their packages.
5. Additional local trace:
   `dev/private/harvestmaster/h3_decomp/HM.Devices.Plugin.H3/H3PluginCreator.cs:68`
   checks model information and displays licence-expiration warnings. Notification
   action arrays are empty; no activation/downloader action is attached there.
   Existing `cmd.py` files in MSI extracts are Python standard-library command
   interpreter modules, not SCIO installer commands. No vendor code executed.

## Precisely remaining acquisition gaps

- Inspect the error screenshot from the known article, which may reveal a real
  executable/service identifier. Current failure is a tool limitation.
- Retrieve the exact public troubleshooting-guide share through an ordinary
  browser if available; inspect any documented deployment filenames or host paths.
  Do not infer a service installer from the utility's name.
- Inspect the complete linked H3 installation documentation, rather than only
  indexed snippets. Follow actual deployment links if present; no guessed URLs.
- A legitimately supplied installed-service directory or installer/cache would
  bypass the discovery gap without bypassing activation. No owner access or
  correspondence was assumed or requested in this run.

These are specific uncompleted leads, **not** a claim that outreach or physical
teardown is mandatory. Public service distribution separate from sensor-specific
activation remains possible but unproven. Further acquisition requires a new
bounded decision; neither search silence nor missing service activation authorizes
access-control bypass or use of embedded vendor credentials.

## Records and safeguards

REQUEST_LEDGER.json records all twenty operations, including failures. Vendor
artifacts unchanged; all new output under dev; no production code changes.
Historical reports preserved. No binary package obtained, so no new signature,
hash or executable-inspection claim. Documentation-only follow-up; tests from the
local resource campaign remain 9 research and 116 production passes, not rerun
or relabelled as tests of public-site completeness.
