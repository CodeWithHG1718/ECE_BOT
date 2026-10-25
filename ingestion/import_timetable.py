"""Normalize recurring timetable rows while preserving OCR and source evidence."""
import hashlib
import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'datafiles/master_timetable_by_year.json'
YEAR_NUMBERS = {'I-Year': 1, 'II-Year': 2, 'III-Year': 3, 'IV-Year': 4}


def extract_records(path=SOURCE):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f'Timetable source not found: {path}')
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    source = json.loads(path.read_text(encoding='utf-8'))
    records = []
    for year_key, rows in source.items():
        if year_key not in YEAR_NUMBERS:
            raise ValueError(f'Unexpected timetable year: {year_key}')
        for position, raw in enumerate(rows, 1):
            sections = raw.get('sections')
            if isinstance(sections, str):
                sections = [value.strip().upper() for value in sections.split(',') if value.strip()]
            elif isinstance(sections, list):
                sections = [str(value).strip().upper() for value in sections if str(value).strip()]
            else:
                sections = []
            batch = raw.get('batch')
            batch = str(batch).strip() if batch not in (None, '') else None
            record_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                f'ece-timetable:{source_hash}:{year_key}:{position}'))
            quote = raw.get('raw_text') or ' | '.join(str(raw.get(k) or '') for k in
                ('day', 'start_time', 'end_time', 'session_type', 'course_code', 'sections', 'room', 'faculty'))
            records.append({
                'record_id': record_id,
                'study_year': YEAR_NUMBERS[year_key],
                'year_label': year_key,
                'academic_year': raw.get('academic_year'),
                'term': raw.get('term'),
                'day': raw.get('day'),
                'start_time': raw.get('start_time'),
                'end_time': raw.get('end_time'),
                'session_type': raw.get('session_type'),
                'session_type_code': raw.get('session_type_code'),
                'course_code': raw.get('course_code'),
                # This source column is a timetable/course-cell label; it is not
                # silently treated as a student's registered section.
                'course_batch': batch,
                'student_sections': sections,
                'room': raw.get('room'),
                'faculty': raw.get('faculty'),
                'raw_text': raw.get('raw_text'),
                'source_page': raw.get('source_page'),
                'applicability': 'ocr_recurring_timetable_unverified',
                'evidence': {
                    'source_version_id': source_hash,
                    'path': path.relative_to(ROOT).as_posix(),
                    'page': raw.get('source_page'),
                    'locator': f'{year_key} row {position}',
                    'quote': quote,
                },
            })
    return records
