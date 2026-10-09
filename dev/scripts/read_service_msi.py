"""Read MSI tables with Windows Installer APIs in MSIDBOPEN_READONLY mode.
No action/sequence is executed. Exported Binary streams are data only.
"""
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
from audit_service_installers import ROOT, PRIVATE, digest

def main():
    api = c.WinDLL('msi')
    api.MsiOpenDatabaseW.argtypes = [w.LPCWSTR, w.LPCWSTR, c.POINTER(w.UINT)]
    api.MsiDatabaseOpenViewW.argtypes = [w.UINT, w.LPCWSTR, c.POINTER(w.UINT)]
    api.MsiRecordGetStringW.argtypes = [w.UINT, w.UINT, w.LPWSTR, c.POINTER(w.DWORD)]
    api.MsiRecordReadStream.argtypes = [w.UINT, w.UINT, c.c_void_p, c.POINTER(w.DWORD)]
    def check(code):
        if code: raise OSError(code, 'MSI read failed')
    def string(record, index):
        size = w.DWORD(0)
        rc = api.MsiRecordGetStringW(record, index, None, c.byref(size))
        if rc not in (0, 234): check(rc)
        size.value += 1
        buf = c.create_unicode_buffer(size.value)
        check(api.MsiRecordGetStringW(record, index, buf, c.byref(size)))
        return buf.value
    result = {}
    PRIVATE.mkdir(parents=True, exist_ok=True)
    for version in ('4', '5'):
        path = ROOT / f'dev/private/harvestmaster/x_mirus{version}_container/a0'
        db = w.UINT()
        check(api.MsiOpenDatabaseW(str(path), None, c.byref(db)))
        tables = {}
        try:
            for table in ('CustomAction', 'Binary', 'ServiceInstall', 'ServiceControl', 'Feature', 'Condition', 'InstallExecuteSequence', 'InstallUISequence'):
                view = w.UINT()
                rc = api.MsiDatabaseOpenViewW(db, f'SELECT * FROM `{table}`', c.byref(view))
                if rc:
                    tables[table] = {'absent_or_error': rc}
                    continue
                rows = []
                try:
                    check(api.MsiViewExecute(view, 0))
                    while True:
                        record = w.UINT()
                        rc = api.MsiViewFetch(view, c.byref(record))
                        if rc == 259: break
                        check(rc)
                        try:
                            if table == 'Binary':
                                name = string(record, 1)
                                if any(x in name for x in ('/', '\\', '..')): raise ValueError('unsafe binary name')
                                out = PRIVATE / f'msi{version}_{name}.bin'
                                with out.open('xb') as f:
                                    total = 0
                                    while True:
                                        buf = c.create_string_buffer(65536)
                                        size = w.DWORD(65536)
                                        check(api.MsiRecordReadStream(record, 2, buf, c.byref(size)))
                                        if not size.value: break
                                        total += size.value
                                        if total > 512 * 1024**2: raise ValueError('stream limit')
                                        f.write(buf.raw[:size.value])
                                rows.append({'name': name, 'size': total, 'sha256': digest(out)})
                            else:
                                rows.append([string(record, i) for i in range(1, api.MsiRecordGetFieldCount(record) + 1)])
                        finally: api.MsiCloseHandle(record)
                finally: api.MsiCloseHandle(view)
                tables[table] = rows
        finally: api.MsiCloseHandle(db)
        result[version] = tables
    with (PRIVATE / 'msi_tables.json').open('x', encoding='utf8') as f:
        json.dump(result, f, indent=2)
    print(json.dumps({v: {'CustomAction': t['CustomAction'], 'Binary': t['Binary'], 'ServiceInstall': t['ServiceInstall']} for v, t in result.items()}, indent=2))

if __name__ == '__main__': main()
