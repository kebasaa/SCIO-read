import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "check_public_safety.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("check_public_safety", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("text", [
    '"mobile_GPS": {"latitude": 46.95, "longitude": 7.45}',          # record / processed JSON
    '{\\"latitude\\":46.95,\\"longitude\\":7.45}',                  # escaped JSON in a log
    "Address[latitude=46.95,longitude=7.45]",                       # Android geocoder line
    "'latitude': -33.9",
])
def test_real_coordinates_are_findings(tool, text):
    assert tool.gps_findings(text)


@pytest.mark.parametrize("text", [
    '"latitude": 47.3769, "longitude": 8.5417',                      # documented redaction placeholder
    '{\\"longitude\\":8.5417,\\"latitude\\":47.3769}',
    '"latitude": null, "longitude": null',                            # empty fields
    '"latitude": 0, "longitude": 0.0',
    '"lat": 5, "accuracy_m": 25.0',
])
def test_placeholder_and_empty_values_pass(tool, text):
    assert tool.gps_findings(text) == []


def test_line_numbers_point_at_the_coordinate(tool):
    assert tool.gps_findings('{\n "a": 1,\n "latitude": 46.1\n}') == [3]
