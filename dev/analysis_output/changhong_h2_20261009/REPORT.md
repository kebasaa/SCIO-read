# Changhong H2 firmware/system-software discovery — 2026-10-09

## Result and scope

No verified H2 firmware/system image, sensing APK, native sensor service or SDK
package obtained. This closes this bounded discovery pass, not the historical
artifact route. No new decode key or offline transform was recovered.

40 web search/page operations; two shell attempts at the same exact press-kit
URL, both transport failures, zero downloaded bytes. Bounds were two new
evidence-linked packages, 512 MiB each, 1 GiB cumulative; no successful package
acquisitions. No installers, activation, accounts, endpoint enumeration, device
commands, flashing, vendor-code execution or correspondence. All new files are
under dev. Existing production code, captures and private vendor material were
only read. No files were removed.

## Supported evidence

| Finding | Source and boundary |
| --- | --- |
| H2 embeds Consumer Physics SCIO and a developer SDK was planned | [Manufacturer-supplied launch release, January 4, 2017](https://www.prnewswire.com/news-releases/changhong-h2-worlds-first-molecular-identification-and-sensing-smartphone-with-a-miniaturized-integrated-material-sensor-unveiled-at-ces-300385325.html). Announced availability is not verified retail shipment, nor an available SDK binary. |
| ADI supplied the H2 sensing module | [ADI demonstration page, February 10, 2017](https://www.analog.com/cn/education/education-library/videos/5318273224001.html). Indexed page text inspected; video not watched. No module part number, firmware container or electrical interface recovered. |
| ADI/CP describe a sensor-to-cloud platform | [ADI February 2016 release](https://investor.analog.com/static-files/67a1d588-0690-464c-baea-598c8b8b247d). Two-page PDF text inspected. Describes general collaboration and developer kit, not an H2-specific offline SDK. Does not separate acquisition, spectral conversion and prediction locations. |
| Changhong confirms the H2/SCIO integration | [Changhong-hosted January 2017 coverage](https://group.changhong.com/xwzx_255/mtbd/201701/t20170109_65869.html). Marketing coverage, not a firmware distribution manifest. Do not reuse its imprecise physical explanation as decoder evidence. |

## Artifact leads and acquisition outcomes

The launch release links exactly `http://www.consumerphysics.com/H2PressKit.zip`.
This is a press kit, **not** a firmware offer. It could provide screenshots,
app labels or hardware identifiers, so acquisition was justified as identification
work. `dev/scripts/acquire_h2_presskit.py` makes an exclusive, bounded download
and ZIP member inventory without execution/extraction. Its immutable private
ledger is `dev/private/changhong_h2_20261009/acquisition.json`.

The first attempt raised URLError and received zero bytes. A separate diagnostic
attempt identified ConnectionRefusedError / WinError 10061. DNS resolved the
hostname, but that does not demonstrate working HTTP service. The exception does
not identify whether refusal arose at the origin, a proxy or the local transport;
therefore **do not claim the vendor deleted the file**. HTTP and HTTPS web-tool
opens returned internal errors, not usable HTTP status evidence. No incomplete
download file was created.

Other exact launch links, `phone.consumerphysics.com` and the historical
Changhong mobile product-search page, could not be read by the web tool. An exact
public Wayback CDX query for the press-kit path also returned an internal error.
Archive coverage is unresolved: no snapshot list was obtained and no historical
payload absence established. No guessed archive timestamps were used.

[ZOL H2 catalogue](https://detail.zol.com.cn/cell_phone/index1163696.shtml)
identifies H2 / mobile 4G / 64 GB, but no chipset/board identifier. Following its
actual download tab failed. A generic download navigation item is not evidence
of an available ROM. Catalogue specs differ from launch material, so they are
not adequate for identifying a candidate firmware image. The Chinese alias
"天眼" appears in secondary launch coverage; no different verified model code
was established.

Needrom-, 4PDA-, GitHub-, English- and Chinese-focused searches yielded no
evidence-linked H2 phone binary. Strong false matches included Allwinner H2/H2+
TV boxes, XGIMI H2 projectors, Changhong TV service firmware and a Changhong
address in an unrelated FCC report. None was downloaded. Search silence is
bounded negative evidence, not an exhaustive repository or Chinese-web audit.

Existing private Java/XML/Dart/C# source trees were text-searched for Changhong,
HONPhone and Chinese names: no matches. This is not a binary/resource-string
audit and does not exclude generic CP code reused by the H2. The supplied APK
inventory has no separately identified H2 system/sensing package.

## Next artifact and analysis decision

Do not expand into unrelated H2 firmware or invent OTA URL templates. The most
useful new evidence is one of:

1. A verifiable H2 system/OTA image, with model/build identifiers and provenance.
2. Its preinstalled sensing APK together with native libraries, vendor service,
   calibration assets and any module firmware; APK alone may be only a cloud UI.
3. A public historical phone-page/press-kit snapshot exposing a real app or
   firmware link, or an authorized owner's existing software dump.

For an acquired image: statically inventory system/vendor APKs and native code,
trace sensor acquisition through framing, spectral conversion and cloud calls,
and identify embedded firmware/update assets. Preserve distinctions between
phone CPU code and sensor-module code. Only path-connected constants/derivations
should enter key tests; do not sweep arbitrary binary windows. Consumer-device
compatibility remains unproven until raw layout, calibration and independent
paired spectra are validated. Prediction's cloud dependency would not itself
prove that raw-to-spectrum conversion is also remote.

Useful alternate next software artifact remains the identified Cargill Reveal
package, with hash/code comparison to existing Analyzer extracts before a new
decompile. This campaign did not acquire it or claim an offline decoder there.

## Verification

Three mocked acquisition tests passed: static ZIP inventory without extraction,
immutable acquisition ledger, transport failure and streaming size-limit failure.
Tests made no network requests and kept temporary files under dev/tmp.
`git diff --check` passed (only an existing Windows line-ending advisory).
The campaign report, ledgers, script and test were scanned for personal absolute
paths and common credential markers; no matches. Production tests were not rerun:
no production implementation changed. Pre-existing dirty changes were preserved.
