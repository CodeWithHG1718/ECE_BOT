from pathlib import Path
import json
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tmp' / 'pdfs' / 'inspection'
OUT.mkdir(parents=True, exist_ok=True)
for path in sorted((ROOT / 'data').glob('*.pdf')):
    pages = []
    with pdfplumber.open(path) as pdf:
        for n, page in enumerate(pdf.pages, 1):
            pages.append({'page': n, 'text': page.extract_text() or '',
                          'tables': page.extract_tables()})
    (OUT / (path.stem + '.json')).write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding='utf-8')
    print(path.name, len(pages), 'pages;', sum(len(p['tables']) for p in pages), 'tables')
    if 'str_24' in path.name:
        print(json.dumps(pages[3]['tables'], ensure_ascii=False)[:9000])
