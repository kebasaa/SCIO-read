"""Acquire one evidence-linked public guide and inspect PDF text/link annotations.
Outputs only beneath dev/private; no installer execution or recursive downloads.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from PyPDF2 import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dev/private/harvestmaster_archive_20261009'
URL = 'https://www.harvestmaster.com/data/support/31360%20H2%20NIR%20Upgrade%20Installation%20Guide.pdf'

def main():
    global OUT
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    if args.attempt < 1 or args.attempt > 2: raise ValueError('bounded attempts')
    OUT = OUT / f'attempt_{args.attempt}'
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {'url': URL, 'timestamp': datetime.now(timezone.utc).isoformat(), 'limit': 32 * 1024**2}
    data = bytearray()
    try:
        if args.offline:
            data.extend((OUT / 'h2_nir_guide.pdf').read_bytes())
        else:
            with urlopen(URL, timeout=30) as response:
                meta.update(status=response.status, final_url=response.url)
                while True:
                    block = response.read(65536)
                    if not block: break
                    data.extend(block)
                    if len(data) > meta['limit']: raise ValueError('guide limit')
        if not data.startswith(b'%PDF-'): raise ValueError('not PDF')
        target = OUT / 'h2_nir_guide.pdf'
        if not args.offline:
            with target.open('xb') as f: f.write(data)
        meta.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
        reader = PdfReader(target)
        pages = []
        links = []
        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ''
            pages.append({'page': i, 'text': text})
            annots = page.get('/Annots', [])
            if hasattr(annots, 'get_object'): annots = annots.get_object()
            for annotation in annots:
                action = annotation.get_object().get('/A')
                if action:
                    action = action.get_object()
                    if action.get('/URI'): links.append({'page': i, 'uri': str(action['/URI'])})
        with (OUT / 'guide_inspection.json').open('x', encoding='utf8') as f:
            json.dump({'pages': pages, 'links': links}, f, indent=2)
        print(json.dumps({'pages': len(pages), 'links': links, 'relevant': [p for p in pages if any(s in p['text'].lower() for s in ('software installation','install the scio','scio service','installer'))]}, indent=2))
    except Exception as exc:
        meta.update(error_type=type(exc).__name__, error=str(exc), received_bytes=len(data))
        print(json.dumps(meta))
    finally:
        with (OUT / ('guide_offline_inspection.json' if args.offline else 'guide_acquisition.json')).open('x', encoding='utf8') as f: json.dump(meta, f, indent=2)

if __name__ == '__main__': main()
