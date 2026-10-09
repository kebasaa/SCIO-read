"""Bounded static acquisition of the exact press-kit link in the H2 announcement.

No firmware URL guessing, authentication, execution or extraction. Run from repo.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "private" / "changhong_h2_20261009"
URL = "http://www.consumerphysics.com/H2PressKit.zip"
SOURCE = "https://www.prnewswire.com/news-releases/changhong-h2-worlds-first-molecular-identification-and-sensing-smartphone-with-a-miniaturized-integrated-material-sensor-unveiled-at-ces-300385325.html"
LIMIT = 512 * 1024 * 1024


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    target = DEST / "H2PressKit.download"
    ledger = DEST / "acquisition.json"
    if target.exists() or ledger.exists():
        raise RuntimeError("Immutable acquisition already exists; inspect it instead")
    record = {"url": URL, "source": SOURCE,
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "limit_bytes": LIMIT, "received_bytes": 0}
    try:
        with urllib.request.urlopen(URL, timeout=20) as response:
            record.update(status=response.status, final_url=response.url,
                          content_type=response.headers.get("Content-Type"))
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > LIMIT:
                raise ValueError("Declared size exceeds acquisition bound")
            digest = hashlib.sha256()
            with target.open("xb") as out:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    record["received_bytes"] += len(chunk)
                    if record["received_bytes"] > LIMIT:
                        raise ValueError("Streaming size exceeds acquisition bound")
                    digest.update(chunk)
                    out.write(chunk)
            record["sha256"] = digest.hexdigest()
            record["zip_valid"] = zipfile.is_zipfile(target)
            if record["zip_valid"]:
                with zipfile.ZipFile(target) as archive:
                    record["members"] = [dict(name=x.filename, size=x.file_size,
                                               compressed=x.compress_size)
                                         for x in archive.infolist()]
            record["outcome"] = "preserved; not executed or extracted"
    except urllib.error.HTTPError as exc:
        record.update(outcome="http_error", status=exc.code)
    except Exception as exc:
        # Exception text can contain local paths; keep only the class in metadata.
        record.update(outcome="failure", exception_type=type(exc).__name__)
    finally:
        record["finished_utc"] = datetime.now(timezone.utc).isoformat()
        with ledger.open("x", encoding="utf-8") as out:
            json.dump(record, out, indent=2, ensure_ascii=False)
        print(json.dumps(record, ensure_ascii=True))


if __name__ == "__main__":
    main()
