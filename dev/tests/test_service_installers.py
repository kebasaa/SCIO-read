import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('service_audit', Path(__file__).resolve().parents[1] / 'scripts/audit_service_installers.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ServiceAuditTests(unittest.TestCase):
    def test_paths(self):
        for name in ('../escape', 'C:\\escape', '\\escape'):
            with self.assertRaises(ValueError): m.contained(m.PRIVATE, name)

    def test_budget_deleted_still_counts(self):
        with self.assertRaises(ValueError): m.budget([{'size': 1, 'deleted': True}] * 5, 1)
        with self.assertRaises(ValueError): m.budget([], 513 * 1024**2)

    def test_cleanup(self):
        with self.assertRaises(ValueError): m.cleanup_eligible(m.PRIVATE, 'existing', {})
        e = dict(created_by_campaign=True, classification='unrelated', sha256='hash', coverage='full', rationale='not SCIO', regeneration='source')
        self.assertEqual(m.cleanup_eligible(m.PRIVATE, 'new', e).name, 'new')
        e['classification'] = 'unresolved'
        with self.assertRaises(ValueError): m.cleanup_eligible(m.PRIVATE, 'new', e)

    def test_mapping(self):
        with tempfile.TemporaryDirectory(dir=m.ROOT / 'dev/private') as name:
            p = Path(name)
            (p / 'u0').write_bytes(b'test')
            (p / '0').write_text('<BurnManifest xmlns="urn:test"><UX><Payload Id="A" FilePath="x.dll" SourcePath="u0" /></UX><Payload Id="B" DownloadUrl="https://example.invalid/b" /></BurnManifest>')
            r = m.manifest(p / '0', p, p)
            self.assertTrue(r['payloads'][0]['present'])
            self.assertEqual(r['payloads'][1]['classification'], 'remotely_referenced')

    def test_bad_xml(self):
        with tempfile.TemporaryDirectory(dir=m.ROOT / 'dev/private') as name:
            p = Path(name)
            (p / '0').write_text('<!DOCTYPE x><BurnManifest/>')
            with self.assertRaises(ValueError): m.manifest(p / '0', p, p)

    def test_zip_limits_and_traversal(self):
        with tempfile.TemporaryDirectory(dir=m.ROOT / 'dev/private') as name:
            p = Path(name) / 'a.zip'
            with zipfile.ZipFile(p, 'w') as z: z.writestr('test.bin', b'1234')
            with self.assertRaises(ValueError): m.inspect_zip(p, 3)
            entries, left = m.inspect_zip(p, 4)
            self.assertEqual(left, 0)
            self.assertEqual(entries[0]['size'], 4)
            with zipfile.ZipFile(p, 'w') as z: z.writestr('../escape', b'x')
            with self.assertRaises(ValueError): m.inspect_zip(p)

if __name__ == '__main__': unittest.main()
