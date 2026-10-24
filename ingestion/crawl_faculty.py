"""Fetch the department's roster, every linked faculty profile and research pages."""
import json
from urllib.parse import urljoin, quote, unquote
from lxml import html
from fetch_sources import fetch, ROOT

HOME = 'https://ece.iitr.ac.in/'
DIRECTORY = 'https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/People/Faculty/FACULTY%20MEMBERS.html'

def tree(meta):
    return html.parse(str(ROOT / meta['snapshot']))

def clean_url(url):
    return quote(unquote(url), safe=':/?=&%+#')

if __name__ == '__main__':
    roster = fetch(DIRECTORY)
    doc = tree(roster)
    urls = [a.get('href') for a in doc.xpath('//div[contains(@class,"faculty-card")]//a[@href]')]
    home = tree(fetch(HOME))
    for a in home.xpath('//a[@href]'):
        u = urljoin(HOME, a.get('href'))
        if '/Research/' in u or '/Academics/Courses' in u:
            urls.append(u)
    results = []
    for url in dict.fromkeys(clean_url(u) for u in urls):
        try:
            meta = fetch(url)
            results.append(meta)
            print('OK', url, flush=True)
        except Exception as exc:
            results.append({'url':url,'error':str(exc)})
            print('ERROR',url,str(exc),flush=True)
    (ROOT/'datafiles/academic/crawl_report.json').write_text(json.dumps(results, indent=2),encoding='utf-8')
