"""Resolve institutional faculty identities and assemble their complete source records."""
import re
from difflib import SequenceMatcher

from .data import read_records


def tokens(value):
    return re.findall(r'[a-z]+', value.casefold())


def person_matches(name, value):
    parts, target = tokens(name), tokens(value)
    return len(parts) > 1 and parts[-1] in target and all(
        p in target or p[0] in target for p in parts[:-1])


def faculty_matches(text):
    words = set(tokens(text)) - {'professor', 'prof', 'dr'}
    records = read_records('faculty')
    exact = [f for f in records if set(tokens(f['name'])) <= words]
    if exact:
        return exact
    partial = [f for f in records if any(len(w) > 2 and w in tokens(f['name']) for w in words)]
    if partial:
        return partial
    # Restrict typo recovery to a near-exact name token, never broad semantic similarity.
    return [f for f in records if any(len(w) >= 6 and SequenceMatcher(None, w, n).ratio() >= .92
                                    for w in words for n in tokens(f['name']))]


def faculty_projects(faculty):
    result = []
    for project in faculty.get('profile_projects', []):
        fields = project.get('fields', {})
        result.append(dict(project, fields={**fields, 'Scheme/Title': fields.get('TOPIC'),
                      'Faculty': faculty['name'], 'Funding Agency': fields.get('FUNDING AGENCY')}))
    result.extend(p for p in read_records('projects') if any(
        person_matches(faculty['name'], str(p.get('fields', {}).get(key, '')))
        for key in ('Faculty', 'Co-PI')))
    unique = {}
    for project in result:
        title = project.get('fields', {}).get('Scheme/Title') or ''
        key = ' '.join(tokens(title))
        if key and key not in unique:
            unique[key] = project
    return list(unique.values())


def teaching_records(faculty):
    titles = {c['code']: c['title'] for c in read_records('courses')}
    result = []
    for row in read_records('timetable'):
        if any(person_matches(faculty['name'], n) for n in (row.get('faculty') or '').split(',')):
            result.append({'course_code': row['course_code'], 'title': titles.get(row['course_code']),
                           'academic_year': row.get('academic_year'), 'term': row.get('term'),
                           'source': 'Uploaded timetable', 'evidence': row.get('evidence')})
    for row in read_records('course_faculty'):
        if row.get('faculty_id') == faculty['faculty_id']:
            result.append({'course_code': row['course_code'], 'title': titles.get(row['course_code']),
                           'source': 'Course-faculty assignments', 'evidence': row.get('evidence')})
    return list({(r['course_code'], r.get('academic_year'), r['source']): r for r in result}.values())


def faculty_result(faculty, query):
    if re.search(r'\b(contact|email|e-mail|phone|telephone|reach|office|room)\b', query):
        contacts = faculty.get('official_contact_fields', [])
        details = []
        email_only = bool(re.search(r'\b(e-?mail)\b', query)) and not re.search(r'\b(contact|phone|office)\b', query)
        phone_only = bool(re.search(r'\b(phone|telephone)\b', query)) and 'contact' not in query
        office_only = bool(re.search(r'\b(office|room)\b', query)) and not re.search(r'\b(contact|email|e-mail|phone|telephone)\b', query)
        for raw in contacts:
            value = raw.replace('[at]', '@').replace('[dot]', '.')
            if '@' in value:
                if not phone_only and not office_only: details.append(f'- Email: [{value}](mailto:{value})')
            elif len(re.sub(r'\D', '', value)) >= 7 and 'room' not in value.casefold():
                if not email_only and not office_only: details.append(f'- Phone: [{value}](tel:{re.sub(r"[^+0-9]", "", value)})')
            elif not email_only and not phone_only:
                details.append(f'- Office: {value}')
        content = f"**{faculty['name']}**\n" + ('\n'.join(details) if details else 'No matching contact detail is recorded.')
        return dict(content=content, presentation='answer', data=None, evidence=[faculty], warnings=[])
    sections = [s for s in faculty.get('sections', []) if s.get('text') or s.get('tables')]
    projects = faculty_projects(faculty)
    teaching = teaching_records(faculty)
    all_details = bool(re.search(r'\b(all|everything|complete|full)\b', query))
    focus = None
    if not all_details:
        if re.search(r'\b(teach|teaches|teaching|courses)\b', query): focus = 'teaching'
        elif 'project' in query: focus = 'projects'
        elif 'publication' in query or 'papers' in query: focus = 'publications'
        elif re.search(r'\b(qualification|qualifications|education|academic background|degree|degrees)\b', query): focus = 'educational'
        elif 'experience' in query or 'professional background' in query: focus = 'professional'
        elif re.search(r'\b(research|interests|areas)\b', query): focus = 'research interests'
    if focus:
        selected = [s for s in sections if focus in s['heading'].casefold()]
    else:
        selected = sections if all_details else [s for s in sections if s['heading'].casefold() in
                    ('research interests', 'educational details', 'professional background', 'teaching engagements')]
    content = f"{faculty['name']} — {faculty.get('designation', 'ECE faculty')}, IIT Roorkee."
    if focus == 'research interests':
        content = faculty.get('research_interests_directory') or content
    if focus == 'teaching':
        codes = ', '.join(r['course_code'] for r in teaching)
        content = f"{faculty['name']}: {codes} in the uploaded timetable." if teaching else f"Teaching engagements listed in {faculty['name']}'s profile."
        if not selected and not teaching: content = f"No teaching assignments are recorded for {faculty['name']}."
    if focus == 'projects':
        return dict(content=f"{len(projects)} recorded projects for {faculty['name']}.", presentation='projects',
                    data=projects, evidence=projects, warnings=[])
    if focus and not selected and not (focus == 'teaching' and teaching):
        content = f"No {focus} details are recorded for {faculty['name']}."
    record = {'faculty_id': faculty['faculty_id'], 'name': faculty['name'],
              'designation': faculty.get('designation'), 'department': 'Electronics and Communication Engineering',
              'profile_url': faculty.get('profile_url'), 'profile_sections': selected,
              'teaching_assignments': teaching if focus in (None, 'teaching') else [],
              'projects': projects if all_details else [],
              'official_contact_fields': faculty.get('official_contact_fields') if all_details else []}
    # Evidence follows the requested sections and joins, rather than a semantic top-k cutoff.
    evidence = [faculty.get('evidence', []), selected, record['teaching_assignments'], record['projects']]
    return dict(content=content, presentation='faculty', data=[record], evidence=evidence, warnings=[])


def resolve_faculty(text, profile, prior):
    query = text.casefold()
    named = faculty_matches(text)
    reference = bool(re.search(r'\b(he|she|his|her|their|they|that professor|this professor|that faculty|contact|email|e-mail|phone|office|room)\b', query))
    if not named and reference:
        for previous in reversed(prior):
            named = faculty_matches(previous)
            if named:
                break
            codes = {re.sub(r'([A-Z])[- ]?(\d)', r'\1-\2', m.upper()) for m in re.findall(r'\b[a-z]{2,4}[- ]?\d{3}\b', previous, re.I)}
            for kind in ('hss', 'oec'):
                if kind in previous.casefold() and (profile or {}).get(kind + '_course'):
                    codes.add(profile[kind + '_course'])
            names = {n.strip() for r in read_records('timetable') if r.get('course_code') in codes
                     for n in (r.get('faculty') or '').split(',') if n.strip()}
            named = [f for f in read_records('faculty') if any(person_matches(f['name'], n) for n in names)]
            if named:
                break
            if names:
                assignments = [{'course_code': r['course_code'], 'faculty': r.get('faculty')}
                               for r in read_records('timetable') if r.get('course_code') in codes and r.get('faculty')]
                assignments = list({(r['course_code'], r['faculty']): r for r in assignments}.values())
                evidence = [r for r in read_records('timetable') if r.get('course_code') in codes]
                return dict(content=', '.join(sorted(names)) + '. Teaching assignments are recorded; no detailed faculty profile is uploaded.',
                            presentation='faculty', data=assignments, evidence=evidence, warnings=[])
    if not named:
        return None
    if len(named) > 1:
        return dict(content='Which professor: ' + ', '.join(f['name'] for f in named) + '?',
                    presentation='answer', data=None, evidence=[], warnings=[])
    return faculty_result(named[0], query)
