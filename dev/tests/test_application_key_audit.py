import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
audit = importlib.import_module("audit_application_key")


def test_incomplete_tree_is_not_evidence_of_absence(tmp_path):
    with pytest.raises(ValueError, match="incomplete source package"):
        audit.inspect_source(tmp_path, "fixture")


@pytest.mark.parametrize("device_ref", [False, True])
def test_device_application_id_reference_invalidates_negative_check(tmp_path, device_ref):
    # Minimal synthetic source text tests the audit, not Android behavior.
    files = {
        "sdk/sciosdk/ScioLoginActivity.java": 'extras.getString(INTENT_APPLICATION_ID); response_type=token&client_id=',
        "sdk/sciosdk/ScioInternalCloud.java": 'Config.REQUEST_CLIENT_ID, this.preferences.getAppId()',
        "sdk/config/ScioCloudPreferences.java": 'putString("AppID", str); putString("AccessToken", str);',
        "scioconnection/services/SCiOBLeService.java": 'boolean performSpectrum(Handler h) { return performCommand((byte) 2, h); }',
        "sdk/sciosdk/ScioInternalDevice.java": 'getDataAsBase64();' + (' getAppId();' if device_ref else ''),
    }
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    result = audit.inspect_source(tmp_path, "fixture")
    assert result["all_checks_pass"] is (not device_ref)
