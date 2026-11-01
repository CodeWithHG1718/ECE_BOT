from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, exists, insert, select, update
from sqlalchemy.engine import Engine

from .db import (courses, faculty, index_versions, ingestion_runs, metadata, now_kolkata,
                 offerings, projects, resources, schedule_events, source_chunks,
                 source_chunk_documents, source_documents, syllabus_topics)

DATA = Path(__file__).resolve().parents[2] / 'datafiles' / 'academic'
FILES = {
    'courses': 'course_catalogue.json', 'syllabus': 'syllabus_courses.json',
    'timetable': 'timetable_records.json', 'calendar': 'academic_calendar_events.json',
    'exams': 'ete_schedule_records.json', 'books': 'book_references.json',
    'book_contents': 'book_contents.json', 'nptel': 'nptel_references.json',
    'faculty': 'faculty_profiles.json', 'projects': 'department_projects.json',
}


def read_records(name: str) -> list[dict[str, Any]]:
    path = DATA / FILES[name]
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(data, dict):
        return data.get('records', [])
    return data if isinstance(data, list) else []


@lru_cache(maxsize=128)
def _checksum(path: str) -> str | None:
    src_path = Path(__file__).resolve().parents[2] / path
    return hashlib.sha256(src_path.read_bytes()).hexdigest() if src_path.is_file() else None


def _iter_evidence(value: Any):
    if isinstance(value, dict):
        if value.get('source_version_id') or value.get('path') or value.get('url'):
            yield value
        for child in value.values():
            yield from _iter_evidence(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_evidence(child)


def _source_from_evidence(evidence: dict[str, Any], record: dict[str, Any], imported: datetime) -> dict[str, Any] | None:
    path = evidence.get('path') or record.get('source_path')
    url = evidence.get('url') or record.get('url') or record.get('source_url')
    source_id = evidence.get('source_version_id') or evidence.get('sha256')
    if not source_id and (path or url):
        source_id = hashlib.sha256(str(path or url).encode()).hexdigest()
    if not source_id or not (path or url):
        return None
    checksum = evidence.get('sha256') or evidence.get('checksum') or (_checksum(path) if path else None)
    return {'id': str(source_id), 'path': path, 'url': url, 'checksum': checksum,
            'academic_session': record.get('academic_session') or record.get('academic_year'),
            'applicability': record.get('applicability'),
            'verification_status': record.get('source_status') or record.get('review_status') or record.get('applicability') or 'source_manifest',
            'imported_at': imported}


def _manifest_sources(imported: datetime) -> list[dict[str, Any]]:
    result = []
    for filename in ('local_source_manifest.json', 'web_source_manifest.json'):
        path = DATA / filename
        if not path.exists():
            continue
        records = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(records, list):
            continue
        for record in records:
            checksum = record.get('sha256')
            source_id = checksum or record.get('source_id')
            source_path = record.get('snapshot') or record.get('path')
            url = record.get('final_url') or record.get('url')
            if not source_id or not (source_path or url):
                continue
            base = {'path': source_path, 'url': url, 'checksum': checksum,
                           'academic_session': None, 'applicability': None,
                           'verification_status': 'source_manifest', 'imported_at': imported}
            result.append({'id': str(source_id), **base})
            alias = record.get('source_id')
            if alias and str(alias) != str(source_id):
                result.append({'id': str(alias), **base})
    return result


def _insert_missing(conn, table, rows, key='id'):
    if not rows:
        return
    keys = (key,) if isinstance(key, str) else tuple(key)
    existing = {tuple(row) for row in conn.execute(select(*(table.c[k] for k in keys))).all()}
    conn.execute(insert(table), [r for r in rows if tuple(r.get(k) for k in keys) not in existing])


def load_dataset(engine: Engine) -> None:
    metadata.create_all(engine)
    from .db import ensure_compat_schema
    ensure_compat_schema(engine)
    with engine.begin() as conn:
        started = now_kolkata()
        course_records = read_records('courses')
        course_rows = [{'id': x.get('course_id') or x['code'], 'code': x['code'], 'title': x.get('title') or x['code'], 'payload': x} for x in course_records if x.get('code')]
        _insert_missing(conn, courses, course_rows)
        course_ids = {r['code']: r['id'] for r in course_rows}
        offering_rows = []
        for item in course_records:
            for entry in item.get('curriculum_entries', []):
                entry_id = entry.get('entry_id')
                if entry_id:
                    offering_rows.append({'id': entry_id, 'course_id': course_ids.get(item['code'], item.get('course_id', item['code'])),
                        'academic_session': entry.get('academic_session'), 'cohort': None, 'year': entry.get('year'),
                        'semester': entry.get('semester'), 'applicability': entry.get('applicability')})
        _insert_missing(conn, offerings, offering_rows)
        topic_rows = []
        syllabus_course_ids = {}
        for course in course_records:
            for source_code in course.get('syllabus_source_codes', []):
                syllabus_course_ids[source_code] = course_ids.get(course['code'])
        for syllabus in read_records('syllabus'):
            for section in syllabus.get('sections', []):
                topic_rows.append({'id': hashlib.sha256(f"{syllabus.get('syllabus_id')}:{section.get('ordinal')}".encode()).hexdigest(),
                    'course_id': syllabus_course_ids.get(syllabus.get('source_code')), 'source_code': syllabus.get('source_code'), 'ordinal': section.get('ordinal'),
                    'text': section.get('text') or '', 'evidence': section.get('evidence', [])})
        _insert_missing(conn, syllabus_topics, topic_rows)
        academic_rows = []
        for kind in ('timetable', 'calendar', 'exams'):
            for item in read_records(kind):
                rid = item.get('record_id') or hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
                academic_rows.append({'id': rid, 'event_type': kind, 'course_code': item.get('course_code'),
                    'academic_session': item.get('academic_session') or item.get('academic_year'), 'payload': item,
                    'evidence': item.get('evidence')})
        _insert_missing(conn, schedule_events, academic_rows)
        faculty_rows = [{'id': x.get('faculty_id') or hashlib.sha256(json.dumps(x, sort_keys=True).encode()).hexdigest(),
                         'name': x.get('name') or 'Unknown', 'payload': x, 'evidence': x.get('sections', [])} for x in read_records('faculty')]
        _insert_missing(conn, faculty, faculty_rows)
        project_rows = [{'id': x.get('project_id') or hashlib.sha256(json.dumps(x, sort_keys=True).encode()).hexdigest(),
                         'title': (x.get('fields') or {}).get('Scheme/Title'), 'payload': x, 'evidence': x.get('evidence')} for x in read_records('projects')]
        _insert_missing(conn, projects, project_rows)
        resource_rows = []
        for kind in ('books', 'book_contents', 'nptel'):
            for item in read_records(kind):
                rid = item.get('resource_id') or item.get('book_id') or hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
                resource_rows.append({'id': str(rid), 'resource_type': item.get('resource_type') or kind,
                    'title': item.get('title') or item.get('title_candidate'), 'payload': item, 'evidence': item.get('evidence')})
        _insert_missing(conn, resources, resource_rows)
        source_rows_by_id = {row['id']: row for row in _manifest_sources(started)}
        academic_sources = course_records + read_records('syllabus') + sum((read_records(k) for k in ('timetable','calendar','exams','books','book_contents','nptel','faculty','projects')), [])
        for record in academic_sources:
            for evidence in _iter_evidence(record):
                source = _source_from_evidence(evidence, record, started)
                if source is None:
                    continue
                prior = source_rows_by_id.get(source['id'], {})
                merged = {**prior, **source}
                for key, value in source.items():
                    if value is None and key in prior:
                        merged[key] = prior[key]
                source_rows_by_id[source['id']] = merged
        fake_none_id = hashlib.sha256(b'None').hexdigest()
        conn.execute(delete(source_documents).where(
            source_documents.c.id == fake_none_id,
            source_documents.c.path.is_(None), source_documents.c.url.is_(None), source_documents.c.checksum.is_(None),
            ~exists(select(source_chunks.c.id).where(source_chunks.c.document_id == source_documents.c.id)),
            ~exists(select(source_chunk_documents.c.chunk_id).where(source_chunk_documents.c.document_id == source_documents.c.id))))
        _insert_missing(conn, source_documents, list(source_rows_by_id.values()))
        for source in source_rows_by_id.values():
            conn.execute(update(source_documents).where(source_documents.c.id == source['id']).values(**source))
        chunks_path = DATA / 'embedding_chunks.jsonl'
        chunk_rows = []
        chunk_links = []
        if chunks_path.exists():
            for line in chunks_path.read_text(encoding='utf-8').splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                metadata_value = item.get('metadata') or {}
                raw_source_ids = [str(x) for x in metadata_value.get('source_version_ids', [])]
                source_ids = list(dict.fromkeys(source_id for source_id in raw_source_ids if source_id in source_rows_by_id))
                # Only persist chunks with complete, provenance-backed source links.
                if not source_ids or set(source_ids) != set(raw_source_ids):
                    continue
                chunk_rows.append({'id': item['chunk_id'], 'document_id': source_ids[0],
                               'text': item.get('text', ''), 'metadata': item.get('metadata') or {},
                               'keyword_vector': item.get('text', '').casefold()})
                chunk_links.extend({'chunk_id': item['chunk_id'], 'document_id': source_id} for source_id in source_ids)
            _insert_missing(conn, source_chunks, chunk_rows)
            _insert_missing(conn, source_chunk_documents, chunk_links, key=('chunk_id', 'document_id'))
        run_id = hashlib.sha256(f"seed:{started.isoformat()}".encode()).hexdigest()
        conn.execute(insert(ingestion_runs).values(id=run_id, started_at=started, completed_at=now_kolkata(), status='completed', source_count=len(source_rows_by_id)))
        provider = 'azure' if get_provider() == 'azure' else get_provider()
        model = get_model(provider)
        if provider in ('azure', 'openai'):
            dimensions = 1536
            version_id = hashlib.sha256(f'{provider}:{model}:{dimensions}:l2'.encode()).hexdigest()
            if conn.execute(select(index_versions.c.id).where(index_versions.c.id == version_id)).first() is None:
                conn.execute(insert(index_versions).values(id=version_id, provider=provider, model=model,
                    model_version=None, dimensions=dimensions, normalization='l2', complete=False, created_at=started))


def get_provider() -> str:
    from .config import get_settings
    return get_settings().embedding_provider.casefold()


def get_model(provider: str) -> str:
    from .config import get_settings
    s = get_settings()
    if provider == 'azure':
        return s.azure_openai_embedding_deployment or 'text-embedding-3-small'
    if provider == 'openai':
        return s.openai_embedding_model
    if provider in ('huggingface', 'bge-m3'):
        return 'BAAI/bge-m3'
    return 'unconfigured'


def options() -> dict[str, Any]:
    courses = read_records('courses')
    years = sorted({entry.get('year') for course in courses for entry in course.get('curriculum_entries', []) if isinstance(entry.get('year'), int)})
    timetable = read_records('timetable')
    sections: dict[str, set[str]] = {}
    for row in timetable:
        year = row.get('study_year')
        if not isinstance(year, int) or not row.get('student_sections'):
            continue
        for section in row['student_sections']:
            if isinstance(section, str) and section.strip():
                sections.setdefault(str(year), set()).add(section.strip())
    supported = {str(y): sorted(sections[str(y)]) for y in years if str(y) in sections and sections[str(y)]}
    supported_years = sorted(int(y) for y in supported)
    return {'study_years': [{'value': y, 'label': ['First','Second','Third','Fourth'][y-1] + ' Year' if 1 <= y <= 4 else f'Year {y}'} for y in supported_years],
            'sections_by_year': supported,
            'academic_sessions': [{'value': '2026-27', 'label': 'Autumn 2026–27'}] if read_records('calendar') else [],
            'warnings': ['Section options come from recurring OCR timetable records; cohort applicability is unverified.'] if supported else []}
