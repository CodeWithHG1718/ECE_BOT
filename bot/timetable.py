"""Exact, source-backed lookup for the imported recurring timetable rows."""
import json
import re
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'datafiles/academic/timetable_records.json'
YEAR_KEYS = {'1': 'I-Year', '2': 'II-Year', '3': 'III-Year', '4': 'IV-Year'}
DAY_ORDER = {name: index for index, name in enumerate(
    ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'))}


class Timetable:
    """Read-only timetable queries. No generated answer or fuzzy assignment."""
    def __init__(self, path=SOURCE):
        self.path = Path(path)
        if not self.path.is_file():
            from ingestion.import_timetable import extract_records
            self.rows = [{**row, 'study_year': str(row['study_year'])} for row in extract_records()]
            return
        raw = json.loads(self.path.read_text(encoding='utf-8'))
        self.rows = [{**row, 'study_year': str(row['study_year'])} for row in raw]
        if any(row['study_year'] not in YEAR_KEYS for row in self.rows):
            raise ValueError('Unexpected timetable study year')

    def years(self):
        return sorted({row['study_year'] for row in self.rows})

    def sections(self, year=None):
        rows = self.for_year(year) if year else self.rows
        return sorted({section for row in rows for section in self._sections(row)})

    def batches(self, year=None):
        rows = self.for_year(year) if year else self.rows
        return sorted({str(row.get('course_batch', row.get('batch'))).strip() for row in rows
                       if row.get('course_batch', row.get('batch')) not in (None, '')},
                      key=lambda item: (not item.isdigit(), int(item) if item.isdigit() else item.casefold()))

    def for_year(self, year):
        value = str(year)
        if value not in YEAR_KEYS:
            raise ValueError('Choose timetable year 1, 2, 3 or 4.')
        return [row for row in self.rows if row['study_year'] == value]

    @staticmethod
    def _sections(row):
        raw = row.get('student_sections', row.get('sections'))
        if isinstance(raw, list):
            values = raw
        elif isinstance(raw, str):
            values = raw.split(',')
        else:
            values = []
        return [value.strip().upper() for value in values if value and value.strip()]

    def year_for_section(self, section):
        target = section.strip().upper()
        matches = {row['study_year'] for row in self.rows if target in self._sections(row)}
        return next(iter(matches)) if len(matches) == 1 else None

    def years_for_course(self, code):
        target = re.sub(r'[^A-Z0-9]', '', code.upper())
        return sorted({row['study_year'] for row in self.rows
            if re.sub(r'[^A-Z0-9]', '', str(row.get('course_code', '')).upper()) == target})

    def match_section(self, text):
        values = sorted(self.sections(), key=len, reverse=True)
        upper = text.upper()
        return next((value for value in values
            if re.search(r'(?<![A-Z0-9])' + re.escape(value) + r'(?![A-Z0-9])', upper)), None)

    @staticmethod
    def match_student_batch_number(text):
        """Read conversational ECE-3 / ECE batch 3 as a student group hint."""
        patterns = (
            r'\b(?:ece|ec)\s*[- ]\s*(\d{1,2})(?:st|nd|rd|th)?(?:\s*(?:sub[\s-]*batch|batch))?\b',
            r'\b(?:ece|ec)\s+(?:sub[\s-]*batch|batch)\s*(\d{1,2})\b',
            r'\b(?:my|student)\s+(?:sub[\s-]*batch|batch)\s*(\d{1,2})\b',
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return str(int(match.group(1)))
        return None

    def resolve_student_batch(self, number, year=None):
        """Resolve a sub-batch number only when the source gives one exact section."""
        if number is None:
            return None
        rows = self.for_year(year) if year else self.rows
        pattern = re.compile(r'\d{2}EC0*' + re.escape(str(int(number))) + r'$', re.I)
        matches = sorted({section for row in rows for section in self._sections(row)
                          if pattern.fullmatch(section)})
        return matches[0] if len(matches) == 1 else None

    def match_course(self, text):
        values = sorted({str(row.get('course_code', '')).upper() for row in self.rows if row.get('course_code')},
                        key=len, reverse=True)
        upper = text.upper()
        return next((value for value in values
            if re.search(r'(?<![A-Z0-9])' + re.escape(value).replace(r'\-', '-?') + r'(?![A-Z0-9])', upper)), None)

    @staticmethod
    def match_batch(text):
        match = re.search(r'\b(?:course\s+)?(?:sub[\s-]*batch|batch)\s*(\d+)\b', text, re.I)
        return match.group(1) if match else None

    @staticmethod
    def match_day(text):
        for day in DAY_ORDER:
            if re.search(r'\b' + day[:3] + r'\w*\b', text, re.I):
                return day
        return None

    def matching(self, year, *, section=None, batch=None, course_code=None, day=None):
        target_code = re.sub(r'[^A-Z0-9]', '', course_code.upper()) if course_code else None
        target_section = section.upper() if section else None
        target_batch = str(batch) if batch is not None else None
        target_day = day.casefold() if day else None
        matches = []
        for row in self.for_year(year):
            if target_section and target_section not in self._sections(row):
                continue
            batch_value = row.get('course_batch', row.get('batch'))
            if target_batch is not None and str(batch_value or '').strip() != target_batch:
                continue
            if target_code and re.sub(r'[^A-Z0-9]', '', str(row.get('course_code', '')).upper()) != target_code:
                continue
            if target_day and str(row.get('day', '')).casefold() != target_day:
                continue
            matches.append(row)
        return sorted(matches, key=lambda row: (
            DAY_ORDER.get(row.get('day'), 99), row.get('start_time') or '',
            row.get('end_time') or '', row.get('course_code') or '',
            str(row.get('course_batch', row.get('batch')) or ''), row.get('session_type') or ''))

    def render(self, year, *, section=None, batch=None, course_code=None, day=None, course_title=None):
        rows = self.matching(year, section=section, batch=batch, course_code=course_code, day=day)
        if not rows:
            filters = [f'Year {year}']
            if section: filters.append(f'section {escape(section)}')
            if course_code: filters.append(escape(course_code))
            if batch is not None: filters.append(f'timetable batch {escape(str(batch))}')
            if day: filters.append(escape(day))
            detail = ', '.join(filters)
            text = f'No matching timetable rows were found for {detail}.'
            if section:
                available = self.sections(year)
                if available:
                    text += ' Sections listed for this year: ' + ', '.join(escape(s) for s in available) + '.'
                else:
                    text += ' This year’s extracted rows have no student-section labels, so a personalized match cannot be confirmed.'
            text += ' Rows with missing section labels are not assigned to every student.'
            return text

        label = f'Year {year} timetable'
        if section:
            label += f' · {escape(section)}'
        filters = []
        if course_code: filters.append(escape(course_code))
        if batch is not None: filters.append(f'timetable batch {escape(str(batch))}')
        if day: filters.append(escape(day))
        if filters:
            label += ' · ' + ', '.join(filters)
        lines = [f'<b>{label}</b>', 'Recurring schedule rows from the supplied Autumn 2026–27 timetable extract.']
        for row in rows:
            code = str(row.get('course_code') or 'Course not identified')
            title = course_title(code) if course_title else None
            course_label = f'{escape(code)} · {escape(title)}' if title and title.casefold() != code.casefold() else escape(code)
            parts = [f"{escape(str(row.get('day') or 'Day not stated'))} {escape(str(row.get('start_time') or 'time unknown'))}–{escape(str(row.get('end_time') or 'time unknown'))}"]
            parts.append(escape(str(row.get('session_type') or 'Session type not stated')))
            parts.append(course_label)
            if self._sections(row):
                parts.append('students ' + ', '.join(escape(s) for s in self._sections(row)))
            else:
                parts.append('student section not recorded')
            batch_value = row.get('course_batch', row.get('batch'))
            if batch_value not in (None, ''):
                parts.append('timetable batch ' + escape(str(batch_value)))
            parts.append('room ' + escape(str(row['room'])) if row.get('room') else 'room not recorded')
            parts.append('faculty ' + escape(str(row['faculty'])) if row.get('faculty') else 'faculty not recorded')
            if row.get('source_page'):
                parts.append('source page ' + str(row['source_page']))
            lines.append(' · '.join(parts))
        lines += [
            '',
            'Source note: these are OCR-extracted weekly entries, not dated class occurrences. '
            'A blank section, room, or faculty value remains unknown. “Timetable batch” is '
            'kept separate from student section; do not assume it is an individual sub-batch assignment.',
        ]
        return '\n'.join(lines)
