# Public archive follow-up — 2026-10-09

## New supported findings

The ordinary Wayback browser interface works even though the web fetcher failed.
The HarvestMaster `/data/` index displays 337 captured URLs. Filtering by SCIO
finds only two troubleshooting PDFs; `exe` finds five driver/update utilities;
`msi` finds one Windows Mobile Device Center repair package. No service installer
is identified by these filters. This is bounded index evidence, not proof of
absence: an opaque filename, external host or uncaptured link remains possible.

The support-article prefix index displays 205 URLs. Article 17160 has four captures
between February 15 and June 17, 2026. The earliest capture was actually opened:
it points to .NET8 and reinstalling the service, not a service package. A wrapped
SDK link contains correspondence metadata; that wrapper is neither followed nor
included in shareable artifacts. Both www and bare-host calendars for article
17179 reported no archived capture; the www miss alone was not used to infer
absence because the prefix index exposes bare-host captures.

## H2 NIR guide: acquisition and installation path

Retrieved the exact [official guide](https://www.harvestmaster.com/data/support/31360%20H2%20NIR%20Upgrade%20Installation%20Guide.pdf),
19,075,308 bytes, SHA-256
`dedcb8f14cf36f77292f03fd95e86945fd00835c66ff1bde26f640cbf0200d59`.
Original PDF, acquisition metadata, full 32-page text and annotation inspection,
and page 16/30 renders remain under the private campaign directory.
The first sandbox attempt failed before receiving bytes; an approved network
retry succeeded. An initial indirect-annotation parsing error was repaired and
inspection rerun offline without re-downloading. No URI annotations were found.

Sections 1.7 (page 16) and 2.7 (page 30), visually checked, distinguish Mirus/H3
plugin installation from installing SCIO Service. They describe sensor-specific
activation links and direct customers through Support → My Product → SCIO
License Renewal. This does not prove device-specific installer binaries, keys,
local decoding, or the relationship between activation and package delivery.

The current public support modal resolves that route to
[SCIO Software Request](https://www.harvestmaster.com/products/software-request).
It asks for contact information, sensor and GrainGage serials, licence start
date and combine description. No form was filled or submitted, and no generic
package download is exposed in the inspected page. Outreach is unavailable to
the user and is not an authorized next action.

## SCIO vendor archive

The scionir.com URL index displays 2,128 URLs; local filters `exe`, `msi`, `zip`
and `service` returned no matching URL rows. These are filename/URL searches,
not inspection of every page body.

Additional indices: consumerphysics.com (2,449 URLs) has no EXE/MSI matches;
its three ZIP matches are named press kits, not established service-package
candidates, and were not downloaded. dev.scionir.com (1,767 URLs) has no
ZIP/EXE/MSI matches. junipersys.com/data/ (862 URLs) has no SCIO matches;
service matches are two support-plan PDFs. Filecamp (77 URLs) has no SCIO/EXE
matches; opaque public-share identifiers were not enumerated or guessed.
The software-request exact URL has no archive capture in the inspected calendar.
Its products-prefix index displays 42 URLs and also returns no software-request
match. The eight prefix indices total 7,867 listed URLs (summing displayed
counts only, not a deduplicated or fully inspected corpus).

These indices do not cover unknown CDN/storage hosts, every case/path alias or
content inside every page. They do not prove that a generic unactivated installer
does not exist. No positive package filename/download lead emerged.

## Decision and remaining unknowns

The newly established path is separate service installation plus sensor-specific
activation-link delivery. A publicly downloadable generic installer could still
be independent of activation. That is the acquisition target, not bypassing
licensing or access checks. No invented identities, private-token guesses or
restricted endpoint calls were used. The user cannot ask HarvestMaster; the
earlier draft correspondence remains historical and is not a recommended action.

The bounded discovery budget is exhausted under conservative accounting: 16
earlier operations plus 44 here, including local index filters, failures and
recovery navigation. `REQUEST_LEDGER.json` records them. This is not a count of
browser-internal HTTP traffic. Stop broad public search in this campaign.
Reopen for a concrete new distribution hostname, package filename, public link
or legitimately supplied service/cache artifact—not another guessed filename
sweep. Local dependency/resource analysis remains a distinct software-only route.

## Safeguards

No installer execution, activation, device commands, account impersonation,
token guessing or correspondence. Existing captures/production untouched.
The guide is retained as positive evidence, not cleaned up as irrelevant.
New executable/service packages: zero. Guide bytes count conservatively against
the cumulative download allowance; browser asset requests are not counted as
independent agent discovery operations. Navigation/query counts are recorded
separately from unobservable browser-internal HTTP requests.

## Verification

Eight targeted guide/ledger/installer-safety tests passed; rerun with Python
socket connections disabled. The guide hash and both activation-link passages
are checked offline. Full 32-page extraction and URI annotation inspection are
private; page16 and page30 were visually inspected. The PDF skill guided this
text-plus-render verification, using already installed PyPDF2/PyMuPDF without
installing dependencies. Computer-use skill guided ordinary public browser
navigation, allowing the archive route that the fetcher could not access.
Shareable campaign files scanned for credentials/personal absolute paths and
correspondence wrappers; no matches. Production tests/code/captures were not
changed in this follow-up; no new production test run is claimed.
