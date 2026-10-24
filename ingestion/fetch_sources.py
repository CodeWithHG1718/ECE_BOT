"""Cache public official academic pages; no credentials or API spending."""
import argparse
import hashlib
import json
import time
import urllib.request
from urllib.parse import urlsplit
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'datafiles' / 'academic' / 'sources'
CACHE.mkdir(parents=True, exist_ok=True)

def fetch(url, refresh=False):
    host = (urlsplit(url).hostname or '').lower()
    allowed_domains = ('iitr.ac.in', 'nptel.ac.in', 'wiley.com', 'pearson.com', 'springer.com', 'springeropen.com', 'cambridge.org')
    if not any(host == domain or host.endswith('.'+domain) for domain in allowed_domains):
        raise ValueError('Only official academic and publisher sources are enabled: ' + url)
    key = hashlib.sha256(url.encode()).hexdigest()[:20]
    record = CACHE / (key + '.json')
    if record.exists() and not refresh:
        return json.loads(record.read_text(encoding='utf-8'))
    request = urllib.request.Request(url, headers={'User-Agent': 'AcademicCatalogueResearch/1.0'})
    with urllib.request.urlopen(request, timeout=40) as response:
        raw = response.read()
        mime = response.headers.get_content_type()
        final_url = response.url
    sha = hashlib.sha256(raw).hexdigest()
    extension = '.pdf' if mime == 'application/pdf' or raw.startswith(b'%PDF') else '.html'
    snapshot = CACHE / (sha + extension)
    if not snapshot.exists():
        snapshot.write_bytes(raw)
    result = {'source_id': key, 'url': url, 'final_url': final_url, 'sha256': sha,
              'snapshot': snapshot.relative_to(ROOT).as_posix(), 'content_type': mime,
              'retrieved_at': datetime.now(timezone.utc).isoformat(), 'published_at': None}
    record.write_text(json.dumps(result, indent=2), encoding='utf-8')
    time.sleep(0.4)
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('urls', nargs='+')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    for url in args.urls:
        try:
            print(json.dumps(fetch(url, args.refresh)), flush=True)
        except Exception as exc:
            print(json.dumps({'url': url, 'error': str(exc)}), flush=True)
