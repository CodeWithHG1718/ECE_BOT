"""Source-backed optional courses and personalized weekly schedules."""
from .data import read_records


def category(course):
    if course.get('optional_category') in ('hss', 'oec'):
        return course['optional_category']
    if 'open_elective' in course.get('workbook_categories', []):
        return 'oec'
    if course.get('code', '').startswith('HSS-'):
        return 'hss'
    return None


def course_options(year, semester=None):
    timetable = [r for r in read_records('timetable') if r.get('study_year') == year]
    scheduled = {r.get('course_code') for r in timetable}
    curriculum = [e for c in read_records('courses') for e in c.get('curriculum_entries', [])
                  if e.get('year') == year and (semester is None or e.get('semester') == semester)]
    result = {'hss': [], 'oec': []}
    for course in read_records('courses'):
        kind = category(course)
        if kind is None:
            continue
        # An actual course must have a named catalogue entry; slots like OEC-III are not courses.
        has_slot = course['code'] in scheduled
        slot_prefix = 'HSSEC' if kind == 'hss' else 'OEC'
        permitted = any(e.get('code', '').startswith(slot_prefix) for e in curriculum)
        explicit = [e for e in course.get('curriculum_entries', []) if e.get('entry_type') == 'course']
        if explicit and not any(e.get('year') == year and (semester is None or e.get('semester') == semester) for e in explicit):
            continue
        # The timetable is Autumn; do not reuse it as evidence of a Spring offering.
        autumn = semester is None or semester == year * 2 - 1
        if not autumn or not (has_slot or permitted):
            continue
        result[kind].append({'code': course['code'], 'title': course['title'],
                             'schedule_available': has_slot})
    for values in result.values():
        values.sort(key=lambda r: r['code'])
    return result


def selected_codes(profile):
    return {profile.get(key) for key in ('hss_course', 'oec_course') if profile.get(key)} if profile else set()


def annotate_clashes(rows):
    """Keep every source row; annotate real overlaps without duplicating sessions."""
    rows = list({r['record_id']: dict(r) for r in rows}.values())
    for row in rows:
        conflicts = {other['course_code'] for other in rows
                     if other['record_id'] != row['record_id'] and other.get('day') == row.get('day')
                     and other.get('course_code') != row.get('course_code')
                     and row.get('start_time') and row.get('end_time')
                     and other.get('start_time') and other.get('end_time')
                     and row['start_time'] < other['end_time'] and other['start_time'] < row['end_time']}
        row['clashes_with'] = sorted(conflicts)
    return rows
