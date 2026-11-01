"""Course-scoped links and descriptions from the collected study catalogue."""
import re
from .data import read_records

RESOURCE_REQUEST = r'\b(resources?|sources?|books?|textbooks?|nptel|references?|videos?|reading materials?|study materials?|links?)\b'


def resolve_resources(text, profile, prior, course_matches, personal):
    if not re.search(RESOURCE_REQUEST, text, re.I):
        return None
    courses = course_matches(text, profile)
    topic = re.search(r'\b(?:for|on)\s+(.+)', text, re.I)
    if topic:
        meaningful = set(re.findall(r'[a-z]{3,}', topic[1].casefold())) - {'this','that','subject','subjects','course','courses','all','current','my','study','learn','please','the'}
        if len(meaningful) > 1 and not re.search(r'\b[a-z]{2,4}[- ]?\d{3}\b', text, re.I):
            courses = [c for c in courses if meaningful <= set(re.findall(r'[a-z]+', c['title'].casefold()))]
        if not courses and meaningful:
            return dict(content='No matching source record. Find course resources with live search.', presentation='answer', data=None, evidence=[], warnings=[])
    if not courses:
        for previous in reversed(prior):
            courses = course_matches(previous, profile)
            if courses: break
    if not courses:
        courses = [c for c in read_records('courses') if c['code'] in personal]
    if not courses:
        return dict(content='Which course or topic do you want resources for?', presentation='answer', data=None, evidence=[], warnings=[])
    lines, evidence = [], []
    for course in courses:
        code = course['code']
        nptel = [r for r in read_records('nptel') if code in r.get('curriculum_codes', [])]
        books = [r for r in read_records('book_contents') if code in r.get('curriculum_codes', [])]
        references = [r for r in read_records('books') if code in r.get('curriculum_codes', [])]
        lines.append(f"### {code} · {course['title']}")
        for resource in nptel[:2]:
            lines.append(f"- [**{resource['title']}**]({resource['url']}) — NPTEL; {resource.get('instructor', '')}, {resource.get('institute', '')}.")
            lessons = [l for l in resource.get('lessons', []) if l.get('url')]
            words = set(re.findall(r'[a-z]{4,}', text)) - {'give','study','resources','resource','course','sources','source','links','please','want','books','nptel'}
            lessons.sort(key=lambda l: -len(words & set(re.findall(r'[a-z]+', l.get('title', '').casefold()))))
            if lessons: lines.append('- Start with: ' + ', '.join(f"[{l['title']}]({l['url']})" for l in lessons[:3]) + '.')
            evidence.append(resource)
        for book in books[:2]:
            lines.append(f"- Book: [**{book['title']}**]({book['source_url']}) — {book.get('authors', '')}, {book.get('edition', '')}.")
            evidence.append(book)
        if not books:
            for book in references[:2]:
                lines.append('- Recommended reading: ' + book['bibliographic_text'])
                evidence.append(book)
        if not nptel and not books:
            lines.append('No saved course links are available. Ask me to search NPTEL online for this course.')
    return dict(content='\n\n'.join(lines), presentation='answer', data=None, evidence=evidence, warnings=[])
