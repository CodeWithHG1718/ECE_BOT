"""Institutional query resolution over the existing structured academic records."""
import re
from datetime import timedelta
from difflib import get_close_matches
from .data import read_records
from .db import now_kolkata
from .electives import selected_codes, annotate_clashes
from .faculty_context import resolve_faculty

DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']

def normalize(text):
    text = text.casefold()
    for wrong, right in {'timetabel':'timetable','timetble':'timetable','shedule':'schedule','syllbus':'syllabus','profesor':'professor'}.items():
        text = text.replace(wrong, right)
    return re.sub(r'\b([a-z]{2,4})[ -]?(\d{3})\b', r'\1-\2', text)

def year_of(text, profile):
    match = re.search(r'\b([1-4])(?:st|nd|rd|th)?\s*year|\byear\s*([1-4])\b|\bece[- ]?([1-4])\b', text)
    if match: return int(next(v for v in match.groups() if v))
    for i, word in enumerate(('first','second','third','fourth'), 1):
        if word + ' year' in text: return i
    return (profile or {}).get('study_year')

def timetable_context(profile, year=None, complete=False, records=None):
    year = year or (profile or {}).get('study_year')
    if not year: return [], set()
    rows = [r for r in (records if records is not None else read_records('timetable')) if r.get('study_year') == year]
    semester = (profile or {}).get('semester')
    if semester and not complete:
        term = 'Autumn' if semester % 2 else 'Spring'
        rows = [r for r in rows if not r.get('term') or r['term'] == term]
    section = (profile or {}).get('section') if year == (profile or {}).get('study_year') else None
    if section and not complete:
        rows = [r for r in rows if not r.get('student_sections') or section in r['student_sections']]
    # Only explicit section assignments and curriculum core courses are personal context.
    core = {c['code'] for c in read_records('courses') if any(
        e.get('year') == year and e.get('entry_type') == 'course'
        and (not (profile or {}).get('semester') or e.get('semester') == profile['semester'])
        for e in c.get('curriculum_entries', []))}
    codes = {r.get('course_code') for r in rows if r.get('course_code') in core or
             (section and section in r.get('student_sections', []))}
    selected = selected_codes(profile) if year == (profile or {}).get('study_year') else set()
    codes |= selected
    if not complete:
        rows = [r for r in rows if r.get('course_code') in codes]
    return sorted(rows, key=lambda r:(DAYS.index(r['day']) if r.get('day') in DAYS else 7, r.get('start_time') or '',r.get('course_code') or '')), codes

def course_matches(text, profile):
    q = normalize(text)
    courses = read_records('courses')
    codes = set(re.findall(r'\b[a-z]{2,4}-\d{3}\b', q))
    if codes: return [c for c in courses if c['code'].casefold() in codes]
    for kind in ('hss', 'oec'):
        if re.search(r'\b' + kind + r'\b', q) and (profile or {}).get(kind + '_course'):
            return [c for c in courses if c['code'] == profile[kind + '_course']]
    ignore = {'help','learn','course','subject','my','the','about','syllabus','faculty','who','teaches','curriculum','details','show','me','engineering','professor','professors','projects','project','details','show','what','is','are','for','in'}
    words = set(re.findall(r'[a-z]+', q)) - ignore
    matches = []
    for c in courses:
        title = set(re.findall(r'[a-z]+', c.get('title','').casefold())) - {'and','of','the','to','in','engineering'}
        acronym = ''.join(w[0] for w in c.get('title','').casefold().split() if w not in ('and','of','the','to','in'))
        if (title and title <= words) or (words & title and len(words & title) >= min(2,len(words))) or (len(acronym)>1 and acronym in words): matches.append(c)
    if not matches and words:
        for c in courses:
            title = re.findall(r'[a-z]+',c.get('title','').casefold())
            if any(len(w)>5 and get_close_matches(w,title,n=1,cutoff=.88) for w in words): matches.append(c)
    _, personal = timetable_context(profile)
    preferred = [c for c in matches if c['code'] in personal]
    return preferred or matches

def resolve(text, profile, prior, timetable_records=None):
    q = normalize(text)
    faculty_answer = resolve_faculty(q, profile, prior)
    if faculty_answer is not None:
        return faculty_answer
    if re.search(r'\b(learn|explain|understand|solve|prepare)\b',q) and not re.search(r'\b(timetable|schedule)\b',q):
        return dict(content='No matching source record. General guidance is unavailable until the chat model is configured.', presentation='answer', data=None, evidence=[], warnings=[])
    broad = bool(re.search(r'\b(all years|entire institute|institute-wide|all courses|whole department)\b',q))
    explicit_year = bool(re.search(r'\b(?:[1-4](?:st|nd|rd|th)?|first|second|third|fourth)\s*year|\byear\s*[1-4]|\bece[- ]?[1-4]',q))
    year = year_of(q,profile)
    rows, personal = timetable_context(profile,year,complete=explicit_year or broad,records=timetable_records)
    matches = course_matches(q,profile)
    if not matches and re.search(r'\b(it|its|this course|that course|teaches|this professor|that professor|his|her|their)\b',q):
        for previous in reversed(prior):
            matches = course_matches(previous,profile)
            if matches: break
            if re.search(r'\bete\b',normalize(previous)):
                matches = [c for c in read_records('courses') if c['code'] in personal]; break
    codes = {c['code'] for c in matches}
    def result(content, presentation='answer', data=None, evidence=None, warnings=None):
        return dict(content=content,presentation=presentation,data=data,evidence=evidence or [],warnings=warnings or [])
    for kind in ('hss', 'oec'):
        if re.search(r'\b' + kind + r'\b', q) and not matches and not (profile or {}).get(kind + '_course'):
            return result(f'Your {kind.upper()} selection is None. You can choose a course in your academic profile.')
    teaching = bool(re.search(r'\b(teaches|teaching|faculty|professor|instructor)\b',q))
    projects = 'project' in q
    if teaching or projects:
        names = {n.strip() for r in rows if r.get('faculty') and (r.get('course_code') in codes if codes else r.get('course_code') in personal) for n in r['faculty'].split(',')}
        named = [f for f in read_records('faculty') if all(w in q for w in re.findall(r'[a-z]+',f['name'].casefold()))]
        if not named and re.search(r'\b(it|this professor|his|her|their)\b',q):
            for previous in reversed(prior):
                named = [f for f in read_records('faculty') if all(w in normalize(previous) for w in re.findall(r'[a-z]+',f['name'].casefold()))]
                if named: break
        if not named and codes and re.search(r'\b(this professor|his|her|their)\b', q):
            named = [f for f in read_records('faculty') if f['name'] in names]
        if named: names = {f['name'] for f in named}
        if not codes and not named and not re.search(r'\b(my|ete|teaches)\b',q): return result('Which course or professor? I use the IIT Roorkee ECE records.')
        if projects:
            def person_match(name, value):
                tokens = re.findall(r'[a-z]+',name.casefold()); target=re.findall(r'[a-z]+',value.casefold())
                return len(tokens)>1 and tokens[-1] in target and all(t in target or (len(t)>1 and t[0] in target) for t in tokens[:-1])
            found = [p for p in read_records('projects') if any(person_match(n,str(p.get('fields',{}).get('Faculty',''))) for n in names)]
            return result(f'{len(found)} recorded projects.' if found else 'No projects recorded for those faculty.', 'projects', found, found)
        found = [dict(course_code=r.get('course_code'),faculty=r.get('faculty')) for r in rows if r.get('faculty') and (r.get('course_code') in codes if codes else r.get('course_code') in personal)]
        found = list({(r['course_code'],r['faculty']):r for r in found}.values())
        if named: return result('Faculty details from IIT Roorkee ECE.','faculty',named,named)
        return result('Teaching assignments from your timetable.' if found else 'No teaching assignment recorded for that course.', 'faculty',found,rows)
    exam = bool(re.search(r'\b(exams?|ete|mte|end.term|mid.term)\b',q)) and not re.search(r'\b(classes|syllabus|curriculum)\b',q)
    day = next((d for d in DAYS if d.casefold() in q),None)
    target_date = None
    if re.search(r'\b(today|tomorrow)\b',q):
        target_date = now_kolkata().date() + timedelta(days=1 if 'tomorrow' in q else 0)
        day = DAYS[target_date.weekday()]
    schedule = bool(re.search(r'\b(timetable|schedule|classes|class)\b',q)) or bool(day and re.search(r'\b(my|happening|have|today|tomorrow)\b',q))
    if exam:
        selected = codes or (set() if broad else personal)
        if not selected and not broad: return result('Select your study year and section so I can filter your exam courses.')
        found = [r for r in read_records('exams') if (broad or r.get('course_code') in selected) and ('mte' not in q or 'mid' in r.get('exam_type','').casefold())]
        return result(f'{len(found)} exam entries for your courses.' if found else 'No MTE schedule record found.' if 'mte' in q else 'No matching exam schedule is recorded.', 'exam_schedule' if found else 'answer', found, found, ['Draft exam schedule.'] if found else [])
    if schedule:
        if not year and not broad: return result('Select your study year and section to see your timetable.')
        if broad: rows = read_records('timetable')
        if re.search(r'\bete\b',q) and not codes: return result('ETE denotes the end-term exam in these records. Which course do you mean for classes?')
        if codes: rows = [r for r in rows if r.get('course_code') in codes]
        available = {r.get('course_code') for r in rows}
        missing = selected_codes(profile) - available if not explicit_year and not broad else set()
        if codes: missing &= codes
        if day: rows = [r for r in rows if r.get('day') == day]
        titles = {c['code']:c['title'] for c in read_records('courses')}
        data = [dict(r,course_title=titles.get(r.get('course_code')),date=target_date.isoformat() if target_date else None,
                     section_scope='recorded' if r.get('student_sections') else 'section not specified') for r in rows]
        data = annotate_clashes(data)
        note = ['Recurring timetable; some section or batch assignments are unspecified.'] if any(not r.get('student_sections') for r in rows) else []
        note += [f'{code}: schedule unavailable in the uploaded timetable.' for code in sorted(missing)]
        if any(r['clashes_with'] for r in data): note.append('Overlapping sessions are marked in the Clash column; batch alternatives are preserved.')
        if target_date: note.append('Weekly pattern for this date; calendar exceptions and live cancellations are not established.')
        empty = 'No classes are recorded for that day.' if day else 'No timetable is recorded for the selected academic profile.'
        return result(f'{len(rows)} timetable entries' + (f' for {target_date.isoformat()}' if target_date else f' for {day}' if day else '') + '.' if rows else empty, 'timetable',data,rows,note)
    if re.search(r'\b(my courses|my subjects|core subjects)\b',q):
        found=[c for c in read_records('courses') if c['code'] in personal]
        return result('Courses linked to your timetable and curriculum.' if found else 'Select your study year and section first.','course_list',found,found)
    if matches and not re.search(r'\b(learn|teach|explain|understand|solve)\b',q):
        if len(matches)>1 and not re.search(r'\b(and|courses|subjects)\b',q): return result('Which course: '+', '.join(c['code']+' '+c['title'] for c in matches[:6])+'?')
        if 'syllabus' in q or 'curriculum' in q:
            data=[]
            for c in matches:
                syllabi=[s for s in read_records('syllabus') if s.get('source_code') in c.get('syllabus_source_codes',[])]
                data.append(dict(c,syllabus=[sec for s in syllabi for sec in s.get('sections',[])]))
            return result('Curriculum and syllabus: '+', '.join(c['code'] for c in matches)+'.','course_list',data,data)
        return result('; '.join(c['code']+': '+c['title'] for c in matches)+'.','course_list',matches,matches)
    if re.search(r'\bete\b',q) and re.search(r'\b(syllabus|curriculum)\b',q): return result('Which course syllabus? ETE means end-term examination in the configured records.')
    return None
