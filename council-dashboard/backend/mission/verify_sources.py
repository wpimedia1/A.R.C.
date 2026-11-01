"""Check every published quote in an environment package against the local source PDFs.

    python -m mission.verify_sources [package-id]

Source PDFs live in <repo>/sources/ (referenced by each source's `local_file`). Text is
extracted with pypdf, whitespace and punctuation are normalized, and each quote must appear
verbatim (after normalization) in the document. Writes docs/source-verification.json and exits
non-zero if any quote is not found. Sources without a local file are reported as unchecked.
"""
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from pypdf import PdfReader
from .package import load

REPO = Path(__file__).resolve().parents[3]


def norm(text):
    text = text.replace('–', '-').replace('—', '-').replace('−', '-').replace(' ', ' ')
    return re.sub(r'[^a-z0-9.%~]+', ' ', text.lower()).strip()


def html_text(raw):
    from html.parser import HTMLParser

    class T(HTMLParser):
        def __init__(self):
            super().__init__(); self.parts = []; self.skip = 0
        def handle_starttag(self, tag, attrs):
            if tag in ('script', 'style'): self.skip += 1
        def handle_endtag(self, tag):
            if tag in ('script', 'style'): self.skip = max(0, self.skip - 1)
        def handle_data(self, data):
            if not self.skip: self.parts.append(data)
    t = T(); t.feed(raw.decode('utf-8', errors='replace'))
    return ' '.join(t.parts)


def pages(path):
    reader = PdfReader(str(path))
    return [norm(p.extract_text() or '') for p in reader.pages]


def main(package_id='arcadia-mars-v1'):
    pkg = load(package_id)
    cache, files, results = {}, {}, []
    for name, p in sorted(pkg['parameters'].items()):
        if p['classification'] != 'published':
            continue
        src = pkg['sources'][p['source']]
        row = {'parameter': name, 'source': p['source'], 'locator': p['locator'], 'quote': p['quote']}
        local = src.get('local_file')
        if not local:
            # Archived web copy (tools/archive_sources.py writes sources/web/<source>.<ext>).
            archived = sorted((REPO / 'sources' / 'web').glob(p['source'] + '.*')) if (REPO / 'sources' / 'web').exists() else []
            if not archived:
                row['status'] = 'unchecked: no local copy (web source); run tools/archive_sources.py'
                results.append(row)
                continue
            path = archived[0]
            key = str(path.relative_to(REPO))
            if key not in cache:
                raw = path.read_bytes()
                files[key] = hashlib.sha256(raw).hexdigest()
                cache[key] = pages(path) if path.suffix == '.pdf' else [norm(html_text(raw))]
            q = norm(p['quote'])
            found = [i + 1 for i, text in enumerate(cache[key]) if q in text]
            row.update(file_sha256=files[key], archived_copy=key, found_on_pdf_pages=found,
                       status='verified' if found else 'FAIL: quote not found in archived copy')
            results.append(row)
            continue
        path = REPO / local
        if not path.exists():
            row['status'] = 'FAIL: local file missing ' + local
            results.append(row)
            continue
        if local not in cache:
            raw = path.read_bytes()
            files[local] = hashlib.sha256(raw).hexdigest()
            cache[local] = pages(path)
        q = norm(p['quote'])
        found = [i + 1 for i, text in enumerate(cache[local]) if q in text]
        row['file_sha256'] = files[local]
        row['found_on_pdf_pages'] = found
        row['status'] = 'verified' if found else 'FAIL: quote not found in document text'
        results.append(row)
    failures = [r for r in results if r['status'].startswith('FAIL')]
    report = {'checked_at': time.time(), 'package': pkg['id'], 'package_hash': pkg['hash'], 'method':
              'pypdf text extraction; lowercase; non-alphanumeric runs collapsed to one space; quote must be a substring of one page',
              'verified': sum(r['status'] == 'verified' for r in results), 'failed': len(failures),
              'unchecked': sum(r['status'].startswith('unchecked') for r in results), 'files': files, 'results': results}
    out = REPO / 'docs' / 'source-verification.json'
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    for r in results:
        pages_txt = ','.join(map(str, r.get('found_on_pdf_pages', []))) or '-'
        print(f"{r['status'][:40]:40} {r['parameter']:34} {r['source']:14} pdf p.{pages_txt}")
    print(f"verified {report['verified']}, failed {report['failed']}, unchecked {report['unchecked']} -> {out}")
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
