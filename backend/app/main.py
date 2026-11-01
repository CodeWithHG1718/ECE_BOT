from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, insert, select, text as sql_text, update
from sqlalchemy.engine import Engine

from .config import get_settings
from .data import load_dataset, options, read_records
from .db import (conversations, courses, faculty, make_engine, messages, now_kolkata,
                 profiles, projects, resources, schedule_events, sessions, source_chunks)
from .retrieval import dense_search, reciprocal_rank_fusion

SETTINGS = get_settings()
ENGINE: Engine = make_engine()
SESSION_TOKEN_HEADER = APIKeyHeader(name='X-Session-Token', auto_error=False)


class RequestSizeLimitMiddleware:
    """Count streamed request bytes and reject oversized bodies before routing."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    def _content_length_exceeds_limit(self, value: str) -> bool:
        if not value.isascii() or not value.isdigit():
            return False
        if self.max_bytes < 0:
            return True
        normalized = value.lstrip('0') or '0'
        limit = str(self.max_bytes)
        return len(normalized) > len(limit) or (len(normalized) == len(limit) and normalized > limit)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        lengths = [value.decode('latin-1') for key, value in scope.get('headers', []) if key.lower() == b'content-length']
        if any(self._content_length_exceeds_limit(value) for value in lengths):
            await self._too_large(scope, receive, send)
            return

        received_bytes = 0
        buffered = []
        while True:
            message = await receive()
            if message['type'] == 'http.request':
                received_bytes += len(message.get('body', b''))
                if received_bytes > self.max_bytes:
                    await self._too_large(scope, receive, send)
                    return
                buffered.append(message)
                if not message.get('more_body', False):
                    break
            else:
                buffered.append(message)
                if message['type'] == 'http.disconnect':
                    break

        async def replay_receive():
            if buffered:
                return buffered.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _too_large(scope, receive, send):
        response = JSONResponse(status_code=413, content={
            'error': {
                'code': 'request_too_large',
                'message': 'Request body exceeds the configured limit.',
                'details': {},
            },
        })
        await response(scope, receive, send)


def startup():
    load_dataset(ENGINE)


@asynccontextmanager
async def lifespan(_: FastAPI):
    startup()
    yield


app = FastAPI(title='Signal 2.0 API', version='1.0.0', description='Source-backed ECE academic records and anonymous conversation API.', lifespan=lifespan)
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=SETTINGS.max_request_bytes)
app.add_middleware(CORSMiddleware, allow_origins=SETTINGS.cors_origins, allow_credentials=False, allow_methods=['GET','POST','PUT'], allow_headers=['Content-Type','X-Session-Token'])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ProfileUpdate(StrictModel):
    study_year: int = Field(ge=1, le=4)
    section: str = Field(min_length=1, max_length=32)
    academic_cohort: str | None = Field(default=None, max_length=32)
    semester: int | None = Field(default=None, ge=1, le=12)


class MessageInput(StrictModel):
    text: str = Field(min_length=1, max_length=4000)


class ToolArgs(StrictModel):
    pass


class CourseArgs(ToolArgs):
    query: str | None = Field(default=None, max_length=200)
    year: int | None = Field(default=None, ge=1, le=4)
    course_code: str | None = Field(default=None, max_length=32)


class TimetableArgs(ToolArgs):
    study_year: int | None = Field(default=None, ge=1, le=4)
    course_code: str | None = Field(default=None, max_length=32)
    section: str | None = Field(default=None, max_length=32)
    day: str | None = Field(default=None, max_length=12)


class DateArgs(ToolArgs):
    on: date | None = None


class ExamArgs(DateArgs):
    course_code: str | None = Field(default=None, max_length=32)
    exam_type: str | None = Field(default=None, max_length=40)


class SearchArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


class FilterArgs(ToolArgs):
    query: str | None = Field(default=None, max_length=200)
    course_code: str | None = Field(default=None, max_length=32)
    limit: int = Field(default=10, ge=1, le=20)


class SourceCitation(StrictModel):
    title: str
    url: str | None = None
    page: int | None = None
    status: str
    path: str | None = None
    verification_status: str | None = None


class MessageRecord(StrictModel):
    id: str
    role: Literal['user', 'assistant']
    content: str
    presentation: Literal['answer', 'course_list', 'timetable', 'exam_schedule', 'resources', 'faculty', 'projects']
    data: Any = None
    sources: list[SourceCitation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str


class ProfileData(StrictModel):
    session_id: str | None = None
    study_year: int
    section: str
    academic_cohort: str | None = None
    semester: int | None = None


class ProfileEnvelope(StrictModel):
    profile: ProfileData | None


class ConversationSummary(StrictModel):
    conversation_id: str
    title: str
    created_at: str
    updated_at: str


class ConversationList(StrictModel):
    conversations: list[ConversationSummary]


class MessagesEnvelope(StrictModel):
    messages: list[MessageRecord]


class ConversationCreated(StrictModel):
    conversation_id: str


class SessionCreated(StrictModel):
    session_id: str
    session_token: str
    profile: None = None


class MessagePair(StrictModel):
    user_message: MessageRecord
    assistant_message: MessageRecord


class ProfileOptions(StrictModel):
    study_years: list[dict]
    sections_by_year: dict[str, list[str]]
    academic_sessions: list[dict]
    warnings: list[str] = Field(default_factory=list)


class ErrorItem(StrictModel):
    code: str
    message: str
    details: dict[str, Any]


class ErrorEnvelope(StrictModel):
    error: ErrorItem


class HealthDependencies(StrictModel):
    database: str
    chat_model: str
    embeddings: str


class HealthResponse(StrictModel):
    status: Literal['ok', 'degraded']
    dependencies: HealthDependencies


ERROR_RESPONSES = {status: {'model': ErrorEnvelope, 'description': 'Safe API error envelope.'}
                   for status in (400, 401, 404, 413, 422, 500)}


def _error(code: str, message: str, details: dict | None = None, status: int = 400):
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message, 'details': details or {}}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    details = {'fields': [{'field': '.'.join(str(x) for x in e['loc'] if x != 'body'), 'reason': e['type']} for e in exc.errors()]}
    return _error('validation_error', 'Request validation failed.', details, 422)


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException):
    code = {401: 'unauthorized', 404: 'not_found', 413: 'request_too_large', 422: 'validation_error'}.get(exc.status_code, 'request_error')
    message = exc.detail if isinstance(exc.detail, str) else 'Request failed.'
    return _error(code, message, status=exc.status_code)


@app.exception_handler(Exception)
async def safe_error_handler(_: Request, __: Exception):
    return _error('internal_error', 'The request could not be completed.', status=500)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo('Asia/Kolkata'))
    return value.isoformat()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _session_for_path(conn, session_id: str, token: str | None) -> str:
    if not token:
        raise HTTPException(401, 'A valid session token is required.')
    row = conn.execute(select(sessions.c.token_hash).where(sessions.c.id == session_id)).first()
    if row is None or not hmac.compare_digest(row.token_hash, _token_hash(token)):
        raise HTTPException(401, 'A valid session token is required.')
    return session_id


def _session_from_token(conn, token: str | None) -> str:
    if not token:
        raise HTTPException(401, 'A valid session token is required.')
    digest = _token_hash(token)
    row = conn.execute(select(sessions.c.id, sessions.c.token_hash).where(sessions.c.token_hash == digest)).first()
    if row is None or not hmac.compare_digest(row.token_hash, digest):
        raise HTTPException(401, 'A valid session token is required.')
    return row.id


def _conversation(conn, conversation_id: str, session_id: str, lock: bool = False):
    statement = select(conversations).where(conversations.c.id == conversation_id, conversations.c.session_id == session_id)
    if lock:
        statement = statement.with_for_update()
    row = conn.execute(statement).mappings().first()
    if row is None:
        # Same response for unknown and non-owned identifiers.
        raise HTTPException(404, 'Conversation not found.')
    return row


def _next_message_sequence(conn, conversation_id: str) -> int:
    last = conn.execute(select(func.coalesce(func.max(messages.c.sequence), 0)).where(messages.c.conversation_id == conversation_id)).scalar_one()
    return int(last) + 1


def _citations(item: dict | None, title: str = 'Academic source') -> list[dict]:
    if not item:
        return []
    evidence = item.get('evidence') or []
    if isinstance(evidence, dict):
        evidence = [evidence]
    citations = []
    seen = set()
    for ev in evidence:
        if not isinstance(ev, dict):
            continue
        url = ev.get('url') or item.get('url') or item.get('source_url')
        path = ev.get('path')
        page = ev.get('page')
        key = (url, path, page)
        if key in seen:
            continue
        seen.add(key)
        src_title = (path.rsplit('/', 1)[-1] if path else None) or title
        citations.append({'title': src_title, 'url': url, 'page': page, 'status': 'source_backed',
                          **({'path': path} if path else {}),
                          **({'verification_status': item.get('source_status')} if item.get('source_status') else {})})
    return citations


def _warning(item: dict, kind: str) -> list[str]:
    warnings = []
    status = str(item.get('source_status') or item.get('applicability') or '')
    if kind == 'exams' or 'draft' in status:
        warnings.append('The ETE schedule is draft; its program and range assignments do not confirm an individual student’s registration. Course assignments for November 23–24 are unresolved.')
    if kind == 'calendar':
        warnings.append('This calendar applies to programs other than MBA; tentative and conditional dates remain as printed in the source.')
        if item.get('source_note'):
            warnings.append(item['source_note'])
    if kind == 'timetable' or 'ocr_recurring' in status:
        warnings.append('Recurring weekly OCR timetable entry; it does not confirm a dated occurrence or live change.')
    if kind in ('books','book_contents','nptel'):
        warnings.append('Collected study guide data; it is not full textbook content or proof of current availability.')
    if item.get('applicability') and 'unverified' in item['applicability'] and not warnings:
        warnings.append('Applicability is unverified in the source record.')
    return warnings


def _course_list(q: str | None = None, year: int | None = None, code: str | None = None):
    records = read_records('courses')
    ql = q.casefold() if q else None
    out = []
    for course in records:
        if code and course.get('code', '').casefold() != code.casefold():
            continue
        entries = course.get('curriculum_entries', [])
        if year is not None and not any(e.get('year') == year for e in entries):
            continue
        if ql and ql not in (course.get('code','') + ' ' + course.get('title','')).casefold():
            continue
        out.append(course)
    return out


def _course_data(course: dict) -> dict:
    entries = course.get('curriculum_entries', [])
    return {'course_id': course.get('course_id'), 'code': course.get('code'), 'title': course.get('title'),
            'curriculum_entries': [{'year': e.get('year'), 'semester': e.get('semester'), 'term': e.get('term'), 'credits': e.get('credits_raw'), 'applicability': e.get('applicability'), 'evidence': e.get('evidence')} for e in entries],
            'syllabus_source_codes': course.get('syllabus_source_codes', []), 'content_mapping': course.get('content_mapping')}


def _timetable(year: int | None = None, code: str | None = None, section: str | None = None, day: str | None = None):
    out = []
    for row in read_records('timetable'):
        if year is not None and row.get('study_year') != year: continue
        if code and (row.get('course_code') or '').casefold() != code.casefold(): continue
        if section and section not in (row.get('student_sections') or []): continue
        if day and (row.get('day') or '').casefold() != day.casefold(): continue
        out.append(row)
    return sorted(out, key=lambda x: (x.get('day',''),x.get('start_time',''),x.get('course_code','')))


def _events(kind: str):
    name = {'calendar':'calendar','exams':'exams'}[kind]
    return read_records(name)


def _keyword_search(q: str, limit: int = 8) -> list[dict]:
    terms = set(re.findall(r'[a-z0-9]+', q.casefold()))
    if not terms: return []
    if ENGINE.dialect.name == 'postgresql':
        with ENGINE.connect() as conn:
            rows = conn.execute(sql_text("""
                SELECT id, text, metadata, ts_rank_cd(search_document, plainto_tsquery('simple', :query)) AS score
                FROM source_chunks
                WHERE search_document @@ plainto_tsquery('simple', :query)
                ORDER BY score DESC LIMIT :limit
            """), {'query': q, 'limit': limit}).mappings().all()
        return [dict(row, score=round(float(row['score']), 5)) for row in rows]
    scored = []
    docs = []
    with ENGINE.connect() as conn:
        rows = conn.execute(select(source_chunks.c.id, source_chunks.c.text, source_chunks.c.metadata)).all()
    for row in rows:
        item = {'chunk_id': row.id, 'text': row.text, 'metadata': row.metadata}
        text = row.text or ''
        toks = set(re.findall(r'[a-z0-9]+', text.casefold()))
        docs.append((item, text, toks))
    # IDF-weighted token ranking with exact identifier boosts; dense vectors are not mixed in.
    stopwords = {'a','an','and','are','about','for','from','how','is','it','of','on','or','the','to','what','when','where','which','who','with'}
    meaningful = terms - stopwords
    query_codes = set(re.findall(r'\b[A-Z]{2,4}-\d{3}\b', q.upper()))
    n = max(1, len(docs)); df = {t: sum(t in toks for _,_,toks in docs) for t in meaningful}
    for item, text, toks in docs:
        overlap = meaningful & toks
        code_match = any(code.casefold() in text.casefold() for code in query_codes)
        if len(overlap) < 2 and not code_match: continue
        score = sum((1 + __import__('math').log((n + 1) / (df[t] + 0.5))) * (1 + text.casefold().count(t) ** 0.5) for t in overlap)
        if code_match: score *= 2
        scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [dict(x[1], score=round(x[0], 3)) for x in scored[:limit]]


def _hybrid_search(q: str, limit: int = 8) -> tuple[list[dict], str]:
    keyword_rows = _keyword_search(q, max(limit * 2, limit))
    dense_rows, dense_status = dense_search(ENGINE, q, limit * 2, SETTINGS)
    if dense_status != 'ready':
        return keyword_rows[:limit], dense_status
    return reciprocal_rank_fusion(keyword_rows, dense_rows, limit), dense_status


def _assistant(content: str, presentation: str = 'answer', data: Any = None, sources: list | None = None, warnings: list | None = None):
    return {'id': str(uuid.uuid4()), 'role': 'assistant', 'content': content, 'presentation': presentation,
            'data': data, 'sources': sources or [], 'warnings': warnings or [], 'created_at': _iso(now_kolkata())}


def _deterministic_answer(text: str, profile: dict | None, prior_user_texts: list[str]):
    query = text.strip()
    code_match = re.search(r'\b[A-Z]{2,4}-\d{3}\b', query, re.I)
    code = code_match.group(0).upper() if code_match else None
    lower = query.casefold()
    # Resolve simple follow-ups against conversation history, while keeping the request scoped to this conversation.
    if not code:
        for previous in reversed(prior_user_texts):
            m = re.search(r'\b[A-Z]{2,4}-\d{3}\b', previous, re.I)
            if m:
                code = m.group(0).upper(); break
    if any(w in lower for w in ('timetable','class schedule','classes')) or re.search(r'\bece[- ]?[1-4]\b', lower):
        year = None
        ym = re.search(r'\b(?:year\s*)?([1-4])(?:st|nd|rd|th)?[- ]?(?:year|ece)?\b', lower)
        if ym: year = int(ym.group(1))
        if year is None and 'ece-3' in lower: year = 3
        if year is None and profile: year = profile.get('study_year')
        section = (profile or {}).get('section')
        rows = _timetable(year=year, code=code, section=section)
        if rows:
            titles = {c['code']: c['title'] for c in read_records('courses')}
            data = [{'course_code': r.get('course_code'), 'course_title': titles.get(r.get('course_code')), 'day': r.get('day'),
                'start_time': r.get('start_time'), 'end_time': r.get('end_time'), 'timezone': 'Asia/Kolkata',
                'session_type': r.get('session_type'), 'course_batch': r.get('course_batch'), 'student_sections': r.get('student_sections') or [],
                'room': r.get('room'), 'faculty': r.get('faculty'), 'applicability': r.get('applicability')} for r in rows[:80]]
            src = [s for r in rows[:80] for s in _citations(r, 'Timetable')]
            warning = list(dict.fromkeys(w for r in rows for w in _warning(r, 'timetable')))
            return _assistant(f'Found {len(rows)} matching recurring timetable record(s). These are not dated class occurrences.', 'timetable', data, src, warning)
        return _assistant('No timetable entry matching those filters was found in the collected source records. Missing room, section, or faculty information is not inferred.')
    if 'calendar' in lower or re.search(r'\b(?:september|sep)\s+\d{1,2}\b', lower):
        day_match = re.search(r'\b(?:september|sep)\s+(\d{1,2})\b', lower)
        wanted = f'2026-09-{int(day_match.group(1)):02d}' if day_match else None
        records = [r for r in _events('calendar') if not wanted or wanted in (r.get('dates') or [])]
        if records:
            data = [{'title': r.get('title'), 'dates': r.get('dates'), 'date_ranges': r.get('date_ranges'), 'date_text': r.get('date_text'), 'event_type': r.get('event_type'), 'day': r.get('day_text'), 'programme_scope': r.get('programme_scope'), 'source_status': r.get('source_status'), 'source_note': r.get('source_note')} for r in records]
            src = [s for r in records for s in _citations(r, 'Academic calendar')]
            warning = list(dict.fromkeys(w for r in records for w in _warning(r, 'calendar')))
            return _assistant(f'Found {len(records)} academic calendar record(s).', 'answer', data, src, warning)
        return _assistant('No matching academic calendar entry was found in the imported calendar source.')
    if 'exam' in lower or re.search(r'\b(?:mte|ete|mid[- ]term|end[- ]term)\b', lower):
        mte_only = bool(re.search(r'\bmte\b|mid[- ]term', lower)) and not bool(re.search(r'\bete\b|end[- ]term', lower))
        if code and not mte_only:
            rows = [r for r in _events('exams') if (r.get('course_code') or '').casefold() == code.casefold()]
        else:
            rows = _events('exams') if 'ete' in lower or 'end-term' in lower or 'end term' in lower else []
        if rows:
            data = [{'course_code': r.get('course_code'), 'exam_date': r.get('exam_date'), 'day': r.get('day'),
                'start_time': r.get('start_time'), 'end_time': r.get('end_time'), 'timezone': 'Asia/Kolkata', 'slot': r.get('slot'),
                'room': r.get('room'), 'exam_type': r.get('exam_type'), 'source_status': r.get('source_status'),
                'applicability': r.get('applicability')} for r in rows[:30]]
            src = [s for r in rows[:30] for s in _citations(r, 'Draft ETE schedule')]
            warning = list(dict.fromkeys(w for r in rows for w in _warning(r, 'exams')))
            return _assistant(f'Found {len(rows)} matching draft exam schedule record(s).', 'exam_schedule', data, src, warning)
        label = 'MTE' if 'mte' in lower else 'exam'
        return _assistant(f'No {label} schedule record matching the request is present in the imported official source data. I will not infer dates or assignments.')
    if code:
        found = _course_list(code=code)
        if found:
            item = found[0]; data = _course_data(item)
            sources = []
            for entry in item.get('curriculum_entries', []): sources.extend(_citations(entry, 'Curriculum'))
            syllabus = next((s for s in read_records('syllabus') if s.get('source_code') in item.get('syllabus_source_codes', [])), None)
            if syllabus and ('syllabus' in lower or 'topic' in lower or 'about' in lower):
                data['syllabus'] = [{'ordinal': sec.get('ordinal'), 'text': sec.get('text')} for sec in syllabus.get('sections', [])]
                sources.extend(_citations({'evidence': [ev for sec in syllabus.get('sections', []) for ev in sec.get('evidence', [])]}, 'Syllabus'))
            return _assistant(f"{item.get('code')}: {item.get('title')}. Curriculum and syllabus records may have different applicability; see the source evidence.", 'course_list', data, sources,
                ['Curriculum and syllabus source files do not establish applicability to every current cohort.'])
    results, dense_status = _hybrid_search(query, 5)
    if results:
        snippets = [{'text': r.get('text'), 'metadata': r.get('metadata'), 'score': r.get('score')} for r in results]
        citations = []
        for r in results:
            meta = r.get('metadata') or {}
            for ev in meta.get('evidence', []):
                citations.extend(_citations({'evidence': ev if isinstance(ev, list) else [ev]}, 'Retrieved source'))
        warning = [] if dense_status == 'ready' else [f'Keyword retrieval only; dense search unavailable ({dense_status}).']
        return _assistant('I found related source passages. These records do not confirm facts beyond their source text.', 'resources', snippets, citations, warning)
    return _assistant('I could not find a matching source-backed record. General guidance is unavailable until the chat model is configured.')


_MODEL_TOOLS = [
    {'type':'function','name':'get_profile','description':'Read the current anonymous session profile.', 'parameters':{'type':'object','properties':{},'additionalProperties':False}},
    {'type':'function','name':'list_courses','description':'List collected ECE curriculum courses by query or study year.', 'parameters':{'type':'object','properties':{'query':{'type':['string','null']},'year':{'type':['integer','null']},'course_code':{'type':['string','null']}},'additionalProperties':False}},
    {'type':'function','name':'course_details','description':'Retrieve the exact course, curriculum and source syllabus records.', 'parameters':{'type':'object','properties':{'course_code':{'type':'string'}},'required':['course_code'],'additionalProperties':False}},
    {'type':'function','name':'get_timetable','description':'Filter recurring source timetable records.', 'parameters':{'type':'object','properties':{'study_year':{'type':['integer','null']},'course_code':{'type':['string','null']},'section':{'type':['string','null']},'day':{'type':['string','null']}},'additionalProperties':False}},
    {'type':'function','name':'get_calendar','description':'Look up academic calendar entries by ISO date.', 'parameters':{'type':'object','properties':{'on':{'type':['string','null'],'format':'date'}},'additionalProperties':False}},
    {'type':'function','name':'get_exams','description':'Look up source exam records by course, exam type or date.', 'parameters':{'type':'object','properties':{'course_code':{'type':['string','null']},'exam_type':{'type':['string','null']},'on':{'type':['string','null'],'format':'date'}},'additionalProperties':False}},
    {'type':'function','name':'search_sources','description':'Search source-backed text passages using keyword ranking.', 'parameters':{'type':'object','properties':{'query':{'type':'string'},'limit':{'type':'integer'}},'required':['query'],'additionalProperties':False}},
    {'type':'function','name':'find_resources','description':'Search the collected book and NPTEL study guides.', 'parameters':{'type':'object','properties':{'query':{'type':['string','null']},'course_code':{'type':['string','null']},'limit':{'type':'integer'}},'additionalProperties':False}},
    {'type':'function','name':'find_faculty','description':'Search collected official faculty profile records.', 'parameters':{'type':'object','properties':{'query':{'type':['string','null']},'limit':{'type':'integer'}},'additionalProperties':False}},
    {'type':'function','name':'find_projects','description':'Search collected department project records.', 'parameters':{'type':'object','properties':{'query':{'type':['string','null']},'limit':{'type':'integer'}},'additionalProperties':False}},
]


def _tool_data(name: str, raw_args: dict, profile: dict | None) -> dict:
    if name == 'get_profile':
        if raw_args: raise ValueError('unexpected arguments')
        return {'profile': profile}
    if name == 'list_courses':
        args = CourseArgs.model_validate(raw_args)
        rows = _course_list(args.query, args.year, args.course_code)[:20]
        return {'courses': [_course_data(x) for x in rows]}
    if name == 'course_details':
        args = CourseArgs.model_validate(raw_args)
        if not args.course_code: raise ValueError('course_code required')
        rows = _course_list(code=args.course_code)
        if not rows: return {'course': None}
        item = rows[0]; out = _course_data(item)
        out['syllabus'] = [{'source_code': s.get('source_code'), 'title': s.get('title'), 'sections': s.get('sections', [])}
                           for s in read_records('syllabus') if s.get('source_code') in item.get('syllabus_source_codes', [])]
        return {'course': out}
    if name == 'get_timetable':
        args = TimetableArgs.model_validate(raw_args)
        return {'timezone':'Asia/Kolkata','recurrence':'weekly','records':_timetable(args.study_year,args.course_code,args.section,args.day)[:80]}
    if name == 'get_calendar':
        args = DateArgs.model_validate(raw_args)
        return {'events':[x for x in _events('calendar') if args.on is None or args.on.isoformat() in (x.get('dates') or [])]}
    if name == 'get_exams':
        args = ExamArgs.model_validate(raw_args); rows = _events('exams')
        if args.course_code: rows = [x for x in rows if (x.get('course_code') or '').casefold() == args.course_code.casefold()]
        if args.exam_type: rows = [x for x in rows if args.exam_type.casefold() in (x.get('exam_type') or '').casefold()]
        if args.on: rows = [x for x in rows if x.get('exam_date') == args.on.isoformat()]
        return {'exams':rows[:30]}
    if name == 'search_sources':
        args = SearchArgs.model_validate(raw_args)
        results, dense_status = _hybrid_search(args.query,args.limit)
        return {'results':results, 'dense_status':dense_status}
    if name == 'find_resources':
        args = FilterArgs.model_validate(raw_args); out = []
        for group in ('books','book_contents','nptel'):
            for item in read_records(group):
                text = json.dumps(item,ensure_ascii=False).casefold()
                if args.query and args.query.casefold() not in text: continue
                if args.course_code and args.course_code.casefold() not in text: continue
                out.append(item)
        return {'resources':out[:args.limit]}
    if name in ('find_faculty','find_projects'):
        args = FilterArgs.model_validate(raw_args)
        rows = read_records('faculty' if name == 'find_faculty' else 'projects')
        if args.query:
            rows = [x for x in rows if args.query.casefold() in json.dumps(x,ensure_ascii=False).casefold()]
        return {'records':rows[:args.limit]}
    raise ValueError('unsupported tool')


def _sources_in_result(value: Any) -> list[dict]:
    result = []
    if isinstance(value, dict):
        ev = value.get('evidence')
        if ev:
            result.extend(_citations({'evidence':ev}, 'Academic source'))
        for key, child in value.items():
            if key != 'evidence': result.extend(_sources_in_result(child))
    elif isinstance(value, list):
        for child in value: result.extend(_sources_in_result(child))
    unique = {}
    for source in result:
        unique[(source.get('url'),source.get('path'),source.get('page'))] = source
    return list(unique.values())


async def _responses_answer(text: str, profile: dict | None, history: list[dict] | None = None) -> dict | None:
    chat_api_key = SETTINGS.resolved_openai_chat_api_key
    if not chat_api_key:
        return None
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=chat_api_key)
    try:
        instructions = ('You are Signal, an ECE study assistant. Use the supplied academic lookup tools for institutional facts. '
            'Never invent institute records, source links, exam dates, timetable assignments, course details, or citations. '
            'If the tools do not support an answer, say so. You may explain general ECE concepts, but prefix those sentences '
            'with “General guidance (not an IIT Roorkee record):”. Distinguish draft exams, recurring OCR timetables, and '
            'unverified applicability. Keep answers concise. Do not ask for names, roll numbers, or other student identifiers.')
        conversation_input = [{'role': row['role'], 'content': row['content']} for row in (history or [])[-12:]]
        conversation_input.append({'role':'user','content':text})
        response = await client.responses.create(model=SETTINGS.openai_chat_model, instructions=instructions, input=conversation_input, tools=_MODEL_TOOLS)
        source_rows: list[dict] = []
        for _ in range(4):
            calls = [item for item in (response.output or []) if getattr(item, 'type', None) == 'function_call']
            if not calls: break
            outputs = []
            for call in calls:
                try:
                    args = json.loads(call.arguments or '{}')
                    result = _tool_data(call.name, args, profile)
                    source_rows.extend(_sources_in_result(result))
                except (ValueError, TypeError, json.JSONDecodeError):
                    result = {'error':'Invalid or unsupported lookup arguments.'}
                outputs.append({'type':'function_call_output','call_id':call.call_id,'output':json.dumps(result,ensure_ascii=False)})
            response = await client.responses.create(model=SETTINGS.openai_chat_model, instructions=instructions,
                previous_response_id=response.id, input=outputs, tools=_MODEL_TOOLS)
        answer = (getattr(response, 'output_text', None) or '').strip()
        if not answer: return None
        unique = {(s.get('url'),s.get('path'),s.get('page')): s for s in source_rows}
        citations = list(unique.values())
        warning = [] if citations else ['No source-backed institutional record was used for this response.']
        return _assistant(answer, 'answer', None, citations, warning)
    except Exception:
        # Provider errors can include request details; never log or return them.
        return None
    finally:
        await client.close()


@app.get('/api/v1/health', response_model=HealthResponse, responses=ERROR_RESPONSES)
def health():
    database = 'ready'
    try:
        with ENGINE.connect() as conn: conn.exec_driver_sql('SELECT 1')
    except Exception:
        database = 'unavailable'
    if SETTINGS.resolved_openai_chat_api_key:
        chat = 'configured'
    else:
        chat = 'not_configured'
    provider = SETTINGS.embedding_provider.casefold()
    if provider == 'azure' and not (SETTINGS.azure_openai_api_key and SETTINGS.azure_openai_endpoint):
        embedding_status = 'azure'
    elif provider in ('openai', 'huggingface', 'ollama', 'azure'):
        embedding_status = provider
    else:
        embedding_status = 'not_configured'
    return {'status': 'ok' if database == 'ready' else 'degraded', 'dependencies': {'database': database, 'chat_model': chat, 'embeddings': embedding_status}}


@app.get('/api/v1/profile-options', response_model=ProfileOptions, responses=ERROR_RESPONSES)
def profile_options():
    return options()


@app.post('/api/v1/sessions', status_code=201, response_model=SessionCreated, responses=ERROR_RESPONSES)
def create_session():
    session_id = str(uuid.uuid4()); token = secrets.token_urlsafe(32); now = now_kolkata()
    with ENGINE.begin() as conn:
        conn.execute(insert(sessions).values(id=session_id, token_hash=_token_hash(token), created_at=now))
    return {'session_id': session_id, 'session_token': token, 'profile': None}


@app.get('/api/v1/sessions/{session_id}/profile', response_model=ProfileEnvelope, responses=ERROR_RESPONSES)
def get_profile(session_id: str, x_session_token: str | None = Security(SESSION_TOKEN_HEADER)):
    with ENGINE.connect() as conn:
        _session_for_path(conn, session_id, x_session_token)
        row = conn.execute(select(profiles).where(profiles.c.session_id == session_id)).mappings().first()
    return {'profile': dict(row) if row else None}


@app.put('/api/v1/sessions/{session_id}/profile', response_model=ProfileEnvelope, responses=ERROR_RESPONSES)
def put_profile(session_id: str, body: ProfileUpdate, x_session_token: str | None = Security(SESSION_TOKEN_HEADER)):
    with ENGINE.begin() as conn:
        _session_for_path(conn, session_id, x_session_token)
        supported = options()['sections_by_year'].get(str(body.study_year), [])
        if body.section not in supported:
            raise HTTPException(422, 'Section is not supported by the collected records.')
        values = body.model_dump()
        exists = conn.execute(select(profiles.c.session_id).where(profiles.c.session_id == session_id)).first()
        if exists: conn.execute(update(profiles).where(profiles.c.session_id == session_id).values(**values))
        else: conn.execute(insert(profiles).values(session_id=session_id, **values))
    return {'profile': {'session_id': session_id, **values}}


@app.get('/api/v1/sessions/{session_id}/conversations', response_model=ConversationList, responses=ERROR_RESPONSES)
def list_conversations(session_id: str, x_session_token: str | None = Security(SESSION_TOKEN_HEADER)):
    with ENGINE.connect() as conn:
        _session_for_path(conn, session_id, x_session_token)
        rows = conn.execute(select(conversations).where(conversations.c.session_id == session_id).order_by(conversations.c.updated_at.desc())).mappings().all()
    return {'conversations': [{'conversation_id': r['id'], 'title': r['title'], 'created_at': _iso(r['created_at']), 'updated_at': _iso(r['updated_at'])} for r in rows]}


@app.post('/api/v1/sessions/{session_id}/conversations', status_code=201, response_model=ConversationCreated, responses=ERROR_RESPONSES)
def create_conversation(session_id: str, x_session_token: str | None = Security(SESSION_TOKEN_HEADER)):
    cid = str(uuid.uuid4()); now = now_kolkata()
    with ENGINE.begin() as conn:
        _session_for_path(conn, session_id, x_session_token)
        conn.execute(insert(conversations).values(id=cid, session_id=session_id, title='New conversation', created_at=now, updated_at=now))
    return {'conversation_id': cid}


@app.get('/api/v1/conversations/{conversation_id}/messages', response_model=MessagesEnvelope, responses=ERROR_RESPONSES)
def get_messages(conversation_id: str, x_session_token: str | None = Security(SESSION_TOKEN_HEADER)):
    with ENGINE.connect() as conn:
        session_id = _session_from_token(conn, x_session_token); _conversation(conn, conversation_id, session_id)
        rows = conn.execute(select(messages).where(messages.c.conversation_id == conversation_id).order_by(messages.c.sequence)).mappings().all()
    return {'messages': [{'id': r['id'], 'role': r['role'], 'content': r['content'], 'presentation': r['presentation'], 'data': r['data'], 'sources': r['sources'], 'warnings': r['warnings'], 'created_at': _iso(r['created_at'])} for r in rows]}


@app.post('/api/v1/conversations/{conversation_id}/messages', response_model=MessagePair, responses=ERROR_RESPONSES)
async def post_message(conversation_id: str, body: MessageInput, x_session_token: str | None = Security(SESSION_TOKEN_HEADER)):
    text = body.text.strip()
    if not text: raise HTTPException(422, 'Message text must not be blank.')
    with ENGINE.connect() as conn:
        owner = _session_from_token(conn, x_session_token); conv = _conversation(conn, conversation_id, owner)
        profile_row = conn.execute(select(profiles).where(profiles.c.session_id == owner)).mappings().first()
        prior_rows = conn.execute(select(messages.c.role, messages.c.content).where(messages.c.conversation_id == conversation_id).order_by(messages.c.sequence)).all()
        previous = [r.content for r in prior_rows if r.role == 'user']
        history = [{'role':r.role,'content':r.content} for r in prior_rows]
        answer = _deterministic_answer(text, dict(profile_row) if profile_row else None, previous)
    if answer['content'].startswith('I could not find a matching source-backed record.') and SETTINGS.resolved_openai_chat_api_key:
        model_answer = await _responses_answer(text, dict(profile_row) if profile_row else None, history)
        if model_answer:
            answer = model_answer
        else:
            answer['warnings'].append('The chat model is configured but unavailable; deterministic lookups remain active.')
    now = now_kolkata(); user = {'id': str(uuid.uuid4()), 'role': 'user', 'content': text, 'presentation': 'answer', 'data': None, 'sources': [], 'warnings': [], 'created_at': _iso(now)}
    with ENGINE.begin() as conn:
        owner = _session_from_token(conn, x_session_token); conv = _conversation(conn, conversation_id, owner, lock=True)
        next_sequence = _next_message_sequence(conn, conversation_id)
        conn.execute(insert(messages).values(id=user['id'], conversation_id=conversation_id, role='user', content=text, presentation='answer', data=None, sources=[], warnings=[], sequence=next_sequence, created_at=now))
        conn.execute(insert(messages).values(id=answer['id'], conversation_id=conversation_id, role='assistant', content=answer['content'], presentation=answer['presentation'], data=answer['data'], sources=answer['sources'], warnings=answer['warnings'], sequence=next_sequence + 1, created_at=now))
        title = text[:80].strip()
        conn.execute(update(conversations).where(conversations.c.id == conversation_id).values(title=title or 'New conversation', updated_at=now))
    return {'user_message': user, 'assistant_message': answer}


@app.get('/api/v1/courses', responses=ERROR_RESPONSES)
def list_courses(q: str | None = None, year: int | None = Query(default=None, ge=1, le=4)):
    result = _course_list(q, year)
    return {'courses': [_course_data(x) for x in result]}


@app.get('/api/v1/courses/{course_code}', responses=ERROR_RESPONSES)
def get_course(course_code: str):
    rows = _course_list(code=course_code)
    if not rows: raise HTTPException(404, 'Course not found.')
    item = rows[0]; data = _course_data(item)
    syllabus = [s for s in read_records('syllabus') if s.get('source_code') in item.get('syllabus_source_codes', [])]
    data['syllabus'] = [{'source_code': x.get('source_code'), 'title': x.get('title'), 'sections': x.get('sections',[])} for x in syllabus]
    return {'course': data}


@app.get('/api/v1/timetable', responses=ERROR_RESPONSES)
def timetable(year: int | None = Query(default=None, ge=1, le=4), course_code: str | None = None, section: str | None = None, day: str | None = None):
    rows = _timetable(year, course_code, section, day)
    rows = [{**row, 'timezone': 'Asia/Kolkata'} for row in rows]
    return {'timezone': 'Asia/Kolkata', 'recurrence': 'weekly', 'records': rows,
            'warnings': ['OCR-derived recurring entries; cohort applicability and live changes are unverified.']}


@app.get('/api/v1/calendar', responses=ERROR_RESPONSES)
def calendar(on: date | None = None):
    rows = [r for r in _events('calendar') if on is None or on.isoformat() in (r.get('dates') or [])]
    return {'events': rows, 'warnings': ['Calendar applies to programs other than MBA. Tentative and conditional dates remain as printed.']}


@app.get('/api/v1/exams', responses=ERROR_RESPONSES)
def exams(course_code: str | None = None, exam_type: str | None = None, on: date | None = None):
    rows = _events('exams')
    if course_code: rows = [r for r in rows if (r.get('course_code') or '').casefold() == course_code.casefold()]
    if exam_type: rows = [r for r in rows if exam_type.casefold() in (r.get('exam_type') or '').casefold()]
    if on: rows = [r for r in rows if r.get('exam_date') == on.isoformat()]
    rows = [{**row, 'timezone': 'Asia/Kolkata'} for row in rows]
    return {'exams': rows, 'timezone': 'Asia/Kolkata', 'warnings': ['Draft schedule; assignments do not confirm an individual student’s registration. Detailed course entries for November 23–24 are unresolved.']}


@app.get('/api/v1/resources', responses=ERROR_RESPONSES)
def get_resources(q: str | None = None, course_code: str | None = None, limit: int = Query(default=50, ge=1, le=200)):
    result = []
    ql = q.casefold() if q else None
    for kind in ('books','book_contents','nptel'):
        for x in read_records(kind):
            text = json.dumps(x, ensure_ascii=False).casefold()
            if ql and ql not in text: continue
            if course_code and course_code.casefold() not in text: continue
            result.append(x)
    return {'resources': result[:limit], 'warnings': ['Book references and contents are selected reading guides, not full textbook content.']}


@app.get('/api/v1/faculty', responses=ERROR_RESPONSES)
def get_faculty(q: str | None = None, limit: int = Query(default=50, ge=1, le=200)):
    rows = read_records('faculty'); ql = q.casefold() if q else None
    if ql: rows = [x for x in rows if ql in json.dumps(x, ensure_ascii=False).casefold()]
    return {'faculty': rows[:limit], 'warnings': ['Directory interests do not confirm current teaching, supervision availability, or open positions.']}


@app.get('/api/v1/projects', responses=ERROR_RESPONSES)
def get_projects(q: str | None = None, limit: int = Query(default=50, ge=1, le=200)):
    rows = read_records('projects'); ql = q.casefold() if q else None
    if ql: rows = [x for x in rows if ql in json.dumps(x, ensure_ascii=False).casefold()]
    return {'projects': rows[:limit], 'warnings': ['Collected records do not establish current activity or availability.']}


@app.get('/api/v1/search', responses=ERROR_RESPONSES)
def search(q: str = Query(min_length=1, max_length=500), limit: int = Query(default=8, ge=1, le=50)):
    results, dense_status = _hybrid_search(q, limit)
    keyword = 'postgresql_full_text' if ENGINE.dialect.name == 'postgresql' else 'token_overlap'
    return {'results': results, 'retrieval': {'keyword': keyword, 'dense': dense_status,
            'embedding_provider': SETTINGS.embedding_provider,
            'embedding_model': SETTINGS.azure_openai_embedding_deployment if SETTINGS.embedding_provider.casefold() == 'azure' else SETTINGS.openai_embedding_model},
            'warnings': [] if dense_status == 'ready' else [f'Dense retrieval unavailable ({dense_status}); keyword results remain available.']}
