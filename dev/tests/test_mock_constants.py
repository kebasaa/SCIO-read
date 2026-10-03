import sys
from pathlib import Path
import pytest
import binascii
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_lab_fixtures import mock_constants


def test_allowlisted_constants_only():
    source='public static final String SAMPLE = "AAEC\\nAw=="; public static final String SECRET = "ignore";'
    assert mock_constants(source)=={'SAMPLE':bytes(range(4))}
    assert mock_constants('public static final String SAMPLE = getValue();')=={}


def test_invalid_mock_base64_rejected():
    with pytest.raises(binascii.Error):mock_constants('public static final String WR = "!!!!";')
