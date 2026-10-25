"""Read the supplied ECE course-structure workbook without third-party packages.

The workbook is retained as a source artifact. Its rows are imported with sheet
and cell evidence, and are explicitly marked as user-supplied/unverified because
the file does not state an effective cohort or publication date.
"""
from __future__ import annotations

import hashlib
import posixpath
import re
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / 'datafiles/ECE_Course_Structure.xlsx'
NS = {
    'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'rel': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}
ROMAN_YEARS = {'I': 1, 'II': 2, 'III': 3, 'IV': 4}
SHEET_CATEGORIES = {
    'Year I-IV Courses': 'curriculum_course',
    'Program Electives': 'program_elective',
    'Talent Enhancement': 'talent_enhancement_elective',
    'Minor Specializations': 'minor_specialization',
    'Departmental Honours': 'departmental_honours',
    'Open Electives': 'open_elective',
}


def _column_name(reference: str) -> str:
    match = re.match(r'[A-Z]+', reference)
    if not match:
        raise ValueError(f'Invalid spreadsheet cell reference: {reference}')
    return match.group(0)


def _read_workbook(path: Path):
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        relationships = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        rel_targets = {node.attrib['Id']: node.attrib['Target'] for node in relationships}
        shared_strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            shared_strings = [
                ''.join(node.text or '' for node in item.findall('.//main:t', NS))
                for item in root.findall('main:si', NS)
            ]

        sheets = []
        for sheet in workbook.findall('main:sheets/main:sheet', NS):
            rel_id = sheet.attrib[f"{{{NS['rel']}}}id"]
            target = rel_targets[rel_id].lstrip('/')
            worksheet_path = target if target.startswith('xl/') else posixpath.normpath(posixpath.join('xl', target))
            root = ET.fromstring(archive.read(worksheet_path))
            rows = []
            for row in root.findall('.//main:sheetData/main:row', NS):
                cells = {}
                for cell in row.findall('main:c', NS):
                    value = cell.find('main:v', NS)
                    inline = cell.find('main:is', NS)
                    text = (value.text if value is not None else
                            ''.join(node.text or '' for node in inline.findall('.//main:t', NS))
                            if inline is not None else '')
                    if cell.attrib.get('t') == 's' and text:
                        text = shared_strings[int(text)]
                    reference = cell.attrib['r']
                    cells[_column_name(reference)] = {
                        'value': str(text).strip(), 'reference': reference,
                    }
                rows.append({'number': int(row.attrib['r']), 'cells': cells})
            sheets.append((sheet.attrib['name'], rows))
    return sheets


def _value(row, headers, label):
    column = headers.get(label)
    return row['cells'].get(column, {}).get('value', '') if column else ''


def _record_id(source_hash, sheet, row_number):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
        f'ece-course-workbook:{source_hash}:{sheet}:{row_number}'))


def extract_records(path: Path = WORKBOOK):
    """Extract course rows from the six course-bearing workbook sheets."""
    if not path.is_file():
        raise FileNotFoundError(f'Course workbook not found: {path}')
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    records = []
    for sheet_name, rows in _read_workbook(path):
        category = SHEET_CATEGORIES.get(sheet_name)
        if not category or not rows:
            continue
        header_cells = rows[0]['cells']
        headers = {cell['value']: column for column, cell in header_cells.items()}
        if 'Subject Code' not in headers or 'Course Title' not in headers:
            raise ValueError(f'Required course columns are missing from {sheet_name}')

        for row in rows[1:]:
            code = _value(row, headers, 'Subject Code')
            title = _value(row, headers, 'Course Title')
            if not code or not title:
                continue

            year_raw = _value(row, headers, 'Year').upper()
            year = ROMAN_YEARS.get(year_raw)
            term = _value(row, headers, 'Semester').strip().title()
            semester = None
            if category == 'curriculum_course' and year:
                if term == 'Autumn':
                    semester = year * 2 - 1
                elif term == 'Spring':
                    semester = year * 2
            group = _value(row, headers, 'Group')
            credits = _value(row, headers, 'Credits')
            contacts = {part: _value(row, headers, part) for part in ('L', 'T', 'P')}
            evidence_ref = row['cells'][headers['Subject Code']]['reference']
            evidence = {
                'source_version_id': source_hash,
                'path': path.relative_to(ROOT).as_posix(),
                'sheet': sheet_name,
                'row': row['number'],
                'locator': f"{sheet_name}!{evidence_ref}",
                'quote': f'{code} | {title}',
            }
            record = {
                'record_id': _record_id(source_hash, sheet_name, row['number']),
                'code': code,
                'title': title,
                'category': category,
                'year': year,
                'year_raw': year_raw or None,
                'semester': semester,
                'term': term or None,
                'group': group or None,
                'subject_area': _value(row, headers, 'Subject Area') or None,
                'credits_raw': credits or None,
                'contact_hours_raw': {k: v or None for k, v in contacts.items()},
                'l_t_p_raw': _value(row, headers, 'L-T-P') or None,
                'notes': _value(row, headers, 'Notes') or None,
                'assessment_raw': {
                    key: value or None for key, value in {
                        label: _value(row, headers, label) for label in
                        ('CWS (%)', 'PRS (%)', 'MTE (%)', 'ETE (%)', 'PRE (%)')
                    }.items()
                },
                'applicability': 'user_supplied_workbook_unverified',
                'evidence': evidence,
            }
            records.append(record)
    return records


def curriculum_entry(record):
    """Convert a workbook year/semester row to the shared course-list shape."""
    if record['category'] != 'curriculum_course' or not record['semester']:
        return None
    normalized = re.sub(r'[^A-Z0-9]+', '-', record['code'].upper()).strip('-')
    return {
        'entry_id': 'workbook-' + record['record_id'],
        'course_id': 'curriculum-' + normalized,
        'code': record['code'],
        'title': record['title'],
        'entry_type': 'course',
        'year': record['year'],
        'semester': record['semester'],
        'term': record['term'],
        'group': record['group'],
        'subject_area': record['subject_area'],
        'credits_raw': record['credits_raw'] or 'not stated',
        'contact_hours_raw': record['contact_hours_raw'],
        'examination_hours_raw': {},
        'assessment_raw': record['assessment_raw'],
        'raw_cells': [],
        'evidence': record['evidence'],
        'review_status': 'extracted',
        'applicability': record['applicability'],
    }


def course_text(record):
    text = f"Course {record['code']}: {record['title']}. Category: {record['category'].replace('_', ' ')}."
    if record['year']:
        text += f" Study year {record['year']}."
    if record['semester']:
        text += f" Semester {record['semester']} ({record['term']})."
    if record['group']:
        text += f" Group: {record['group']}."
    if record['subject_area']:
        text += f" Subject area: {record['subject_area']}."
    if record['credits_raw']:
        text += f" Credits as printed: {record['credits_raw']}."
    if any(record['contact_hours_raw'].values()):
        text += ' Contact hours as printed: ' + ', '.join(
            f'{key}: {value}' for key, value in record['contact_hours_raw'].items() if value
        ) + '.'
    if record['l_t_p_raw']:
        text += f" L-T-P as printed: {record['l_t_p_raw']}."
    if record['notes']:
        text += f" Source note: {record['notes']}"
    text += ' This is user-supplied course information; effective cohort and current availability are unverified.'
    return text
