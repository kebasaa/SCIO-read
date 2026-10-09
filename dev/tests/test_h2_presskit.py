"""Acquisition control tests using mocks only; vendor code is never executed."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

spec = importlib.util.spec_from_file_location(
    "h2_acquire", Path(__file__).resolve().parents[1] / "scripts/acquire_h2_presskit.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Response(io.BytesIO):
    status = 200
    url = module.URL
    headers = {"Content-Type": "application/zip"}


class AcquisitionTests(unittest.TestCase):
    def run_fixture(self, response=None, error=None, limit=module.LIMIT):
        root = module.ROOT / "tmp"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            dest = Path(folder)
            with patch.object(module, "DEST", dest), patch.object(module, "LIMIT", limit), \
                    patch.object(module.urllib.request, "urlopen", return_value=response,
                                 side_effect=error), patch("builtins.print"):
                module.main()
                record = json.loads((dest / "acquisition.json").read_text())
                with self.assertRaises(RuntimeError):
                    module.main()
                return record

    def test_static_inventory_does_not_extract(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("../do_not_extract.exe", b"fixture-only")
        record = self.run_fixture(Response(buf.getvalue()))
        self.assertTrue(record["zip_valid"])
        self.assertEqual(record["members"][0]["name"], "../do_not_extract.exe")
        self.assertEqual(record["outcome"], "preserved; not executed or extracted")

    def test_transport_failure_records_no_bytes(self):
        record = self.run_fixture(error=urllib.error.URLError("mock failure"))
        self.assertEqual(record["received_bytes"], 0)
        self.assertEqual(record["exception_type"], "URLError")

    def test_size_limit(self):
        record = self.run_fixture(Response(b"too big"), limit=3)
        self.assertEqual(record["exception_type"], "ValueError")
        self.assertNotIn("sha256", record)


if __name__ == "__main__":
    unittest.main()
