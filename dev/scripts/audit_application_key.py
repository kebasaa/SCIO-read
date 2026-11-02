"""Record bounded static evidence for APPLICATION_KEY's role in local Java SDKs.

No network/device access. This is a source audit, not execution of the Android SDK
or whole-program proof about uninspected firmware. Source roots end in android/.
"""
import argparse
import re
from pathlib import Path

import _bootstrap  # noqa: F401
from scio_offline import research as r

PATTERN = re.compile(r"\b(?:appId|applicationId|APPLICATION_KEY|INTENT_APPLICATION_ID|"
                     r"REQUEST_CLIENT_ID|getAppId|storeAppId)\b|client_id")


def inspect_source(root, label):
    files = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
             for p in sorted(root.rglob("*.java"))}
    required = {
        "login": "sdk/sciosdk/ScioLoginActivity.java",
        "cloud": "sdk/sciosdk/ScioInternalCloud.java",
        "prefs": "sdk/config/ScioCloudPreferences.java",
        "transport": "scioconnection/services/SCiOBLeService.java",
        "device": "sdk/sciosdk/ScioInternalDevice.java",
    }
    missing = sorted(set(required.values()) - set(files))
    if missing:
        raise ValueError(f"{label}: incomplete source package; missing {missing}")
    source = {k: files[v] for k, v in required.items()}
    refs = [{"file": path, "lines": [i for i, line in enumerate(text.splitlines(), 1)
                                     if PATTERN.search(line)]}
            for path, text in files.items() if PATTERN.search(text)]
    checks = {
        "intent_reads_application_id": "extras.getString(INTENT_APPLICATION_ID)" in source["login"],
        "login_client_id_parameter": "response_type=token&client_id=" in (source["login"] + source["cloud"]),
        "phone_preferences_store_app_id": 'putString("AppID", str)' in source["prefs"],
        "phone_preferences_store_token_separately": 'putString("AccessToken", str)' in source["prefs"],
        "app_id_used_for_logout": "Config.REQUEST_CLIENT_ID, this.preferences.getAppId()" in source["cloud"],
        "spectrum_command_is_opcode_2": bool(re.search(
            r"boolean performSpectrum\([^)]*\)\s*\{\s*return performCommand\(\(byte\) 2,",
            source["transport"])),
        "reading_uses_base64_response": "getDataAsBase64()" in source["device"],
        "no_named_app_id_reference_in_transport_or_device": not any(
            ref["file"].startswith("scioconnection/") or ref["file"] == required["device"]
            for ref in refs),
    }
    return {"label": label, "java_files_searched": len(files), "checks": checks,
            "all_checks_pass": all(checks.values()), "application_id_references": refs,
            "source_hashes": {path: r.sha((root / path).read_bytes()) for path in required.values()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True, help="label=path to android source package")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = []
    for value in args.source:
        label, path = value.split("=", 1)
        results.append(inspect_source(Path(path), label))
    report = {"schema": "scio-application-key-audit/1", "checked_on": "2026-10-29",
              "comment": "https://github.com/kebasaa/SCIO-read/issues/1#issuecomment-6482085109",
              "sources": results,
              "limits": ["Exact MyScioApp sample/latest SDK artifact from the comment was not supplied.",
                         "Named-reference search plus manual path tracing is not exhaustive data-flow analysis.",
                         "No server response to an all-zero client ID was tested.",
                         "No device key-setting command or key material was recovered."]}
    r.write_new(args.output, report)
    for result in results:
        print(result["label"], result["java_files_searched"], result["checks"])
    if not all(result["all_checks_pass"] for result in results):
        raise SystemExit("Source audit checks failed; inspect evidence before drawing conclusions")


if __name__ == "__main__":
    main()
