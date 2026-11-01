"""Task routing and compact institutional context for generated answers."""
import re

from .data import read_records
from .db import now_kolkata


def needs_generation(text):
    # These requests ask for new work or a transformation, rather than a stored record.
    text = re.sub(r'\bstudy\s+(resources?|materials?|links?)\b', r'\1', text, flags=re.I)
    if re.search(r'\b(resources?|books?|links?)\b', text, re.I):
        text = re.sub(r'\bto study\b', '', text, flags=re.I)
    if re.search(r'\bwhat courses? (?:does|do).*\bteach\b', text, re.I):
        text = re.sub(r'\bteach\b', '', text, flags=re.I)
    return bool(re.search(
        r'\b(study|learn|teach|explain|understand|solve|prepare|plan|planner|planning|'
        r'write|draft|rewrite|rephrase|summari[sz]e|summary|simplify|compare|design|create|make|'
        r'generate|quiz|practice|practise|revise|revision|recommend|prioriti[sz]e|priorities|outline|organize|structure|calculate|'
        r'derive|prove|debug|code|implement|translate|convert|turn|shorter|longer|instead|'
        r'checklist|flashcards?|examples?|why|how)\b', text, re.I))


def reference(text):
    return bool(re.search(r'\b(it|its|this|that|those|them|same|above|instead|shorter|longer|continue|again|her|him|his|their)\b', text, re.I))


def relevant_courses(text, profile, history, match_courses):
    courses = match_courses(text, profile)
    if courses or not reference(text):
        return courses
    for row in reversed(history[-12:]):
        if row['role'] != 'user': continue
        courses = match_courses(row['content'], profile)
        if courses: return courses
        if not reference(row['content']): break
    return []


def model_context(text, profile, history, match_courses):
    context = {'local_time': now_kolkata().isoformat(), 'timezone': 'Asia/Kolkata'}
    if reference(text):
        previous = next((row for row in reversed(history) if row['role'] == 'assistant'), {})
        fields = {
            'timetable': ('day','start_time','end_time','course_code','course_title','room','faculty','session_type'),
            'exam_schedule': ('course_code','exam_date','start_time','end_time','room','exam_type'),
        }.get(previous.get('presentation'))
        if fields and isinstance(previous.get('data'), list):
            context['previous_result'] = [{key: row.get(key) for key in fields} for row in previous['data'] if isinstance(row, dict)]
    courses = relevant_courses(text, profile, history, match_courses)
    if not courses and re.search(r'\bmy (?:courses|subjects)\b', text, re.I):
        from .academic_context import timetable_context
        _, codes = timetable_context(profile)
        courses = [c for c in read_records('courses') if c['code'] in codes]
    if courses:
        context['courses'] = []
        for course in courses[:6]:
            syllabus = [section['text'] for source in read_records('syllabus')
                        if source.get('source_code') in course.get('syllabus_source_codes', [])
                        for section in source.get('sections', []) if section.get('text')]
            links = [{'title': r['title'], 'url': r['url']} for r in read_records('nptel')
                     if course['code'] in r.get('curriculum_codes', [])][:2]
            links += [{'title': r['title'], 'url': r['source_url']} for r in read_records('book_contents')
                      if course['code'] in r.get('curriculum_codes', [])][:2]
            context['courses'].append({'code': course['code'], 'title': course['title'],
                                       'syllabus_topics': syllabus, 'study_links': links,
                                       'curriculum': [{k: e.get(k) for k in ('year','semester','credits_raw')}
                                                      for e in course.get('curriculum_entries', []) if e.get('entry_type') == 'course']})
    if profile and re.search(r'\b(timetable|classes|academic schedule)\b', text, re.I):
        from .academic_context import timetable_context
        rows, _ = timetable_context(profile)
        context['weekly_timetable'] = [{k: r.get(k) for k in ('course_code','day','start_time','end_time','session_type')}
                                       for r in rows]
    if courses and re.search(r'\b(exam|ete|mte)\b', text, re.I):
        context['exam_records'] = [{k: r.get(k) for k in ('course_code','exam_type','exam_date','start_time','end_time')}
                                   for r in read_records('exams') if r.get('course_code') in {c['code'] for c in courses}]
    # Drafting an email should receive the relevant name/contact, not a biography dump.
    if re.search(r'\b(email|contact|professor|faculty|her|him|research|background|biography)\b', text, re.I):
        from .faculty_context import faculty_matches, person_matches
        faculty = faculty_matches(text)
        if not faculty and reference(text):
            for previous in reversed(history[-8:]):
                if previous['role'] == 'user':
                    faculty = faculty_matches(previous['content'])
                    if faculty: break
        if not faculty and courses:
            codes = {c['code'] for c in courses}
            names = [r.get('faculty', '') for r in read_records('timetable') if r.get('course_code') in codes]
            faculty = [f for f in read_records('faculty') if any(person_matches(f['name'], n) for n in names)]
        context['faculty'] = []
        for f in faculty[:3]:
            item = {'name': f['name'], 'designation': f.get('designation')}
            if re.search(r'\b(email|contact|office|phone)\b', text, re.I):
                item['contact'] = f.get('official_contact_fields', [])
            else:
                item['sections'] = [{'heading': s['heading'], 'text': s['text']} for s in f.get('sections', [])
                                    if s.get('text') and s['heading'] in ('Research Interests','Educational Details','Professional Background')]
            context['faculty'].append(item)
    return context
