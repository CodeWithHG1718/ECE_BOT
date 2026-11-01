"""Provider-hosted web search, restricted to institutional/course sites."""
import re
from urllib.parse import urlsplit

DOMAINS = ['iitr.ac.in', 'nptel.ac.in']
WEB_TOOL = {'type': 'web_search', 'filters': {'allowed_domains': DOMAINS}, 'search_context_size': 'low'}


def requested(text):
    return bool(re.search(r'\b(browse|online|latest|live|web|website)\b', text, re.I) or (
        re.search(r'\b(search|look up|find)\b', text, re.I)
        and re.search(r'\b(nptel|iitr|iit roorkee)\b', text, re.I)))


def linked_answer(response):
    answer = re.sub(r'cite[^]+', '', response.output_text or '').strip()
    links = {}
    for item in response.output or []:
        for part in getattr(item, 'content', []) or []:
            for annotation in getattr(part, 'annotations', []) or []:
                if getattr(annotation, 'type', '') != 'url_citation': continue
                url = annotation.url
                parsed = urlsplit(url)
                host = parsed.hostname or ''
                if parsed.scheme in ('http', 'https') and any(host == d or host.endswith('.'+d) for d in DOMAINS):
                    links[url] = getattr(annotation, 'title', None) or host
    missing = [f'[{title.replace("[", "").replace("]", "")}]({url})' for url, title in links.items() if url not in answer]
    return answer + ('\n\n' + ' · '.join(missing) if missing else '')
