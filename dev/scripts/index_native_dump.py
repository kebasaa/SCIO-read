"""Create a sanitized function/reference index of a private Blutter dump."""
import argparse
from pathlib import Path
import _bootstrap
from scio_offline.native_index import index_dump
from scio_offline.research import write_new, DEV

p = argparse.ArgumentParser()
p.add_argument("--dump", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
if not a.dump.resolve().is_relative_to(DEV / "private"):
    p.error("dump must be under dev/private")
report = index_dump(a.dump)
write_new(a.output, report)
hits = [f for f in report['functions'] if f['pool_refs']]
print(f"{len(report['files'])} files; {len(report['functions'])} function entries; {len(hits)} labeled functions")
for fn in hits:
    print(fn['address'], fn['file'], [report['labels'][x] for x in fn['pool_refs']])
