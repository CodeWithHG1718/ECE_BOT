from __future__ import annotations

import hashlib
import uuid
from datetime import date

from sqlalchemy import insert, select
from fastapi import HTTPException

from backend.app import main
from backend.app.db import conversations, make_engine, messages, sessions


def reset_database():
    main.ENGINE = make_engine('sqlite:///:memory:')
    main.startup()


def new_session():
    return main.create_session()


def test_openapi_and_health_are_published_without_secret_values():
    reset_database()
    schema = main.app.openapi()
    assert '/api/v1/sessions/{session_id}/profile' in schema['paths']
    error_schema = schema['paths']['/api/v1/sessions/{session_id}/profile']['get']['responses']['401']['content']['application/json']['schema']
    assert error_schema['$ref'].endswith('/ErrorEnvelope')
    schemes = schema['components']['securitySchemes']
    token_scheme = next(name for name, value in schemes.items() if value == {
        'type': 'apiKey', 'in': 'header', 'name': 'X-Session-Token'})
    protected_operations = [
        ('/api/v1/sessions/{session_id}/profile', 'get'),
        ('/api/v1/sessions/{session_id}/profile', 'put'),
        ('/api/v1/sessions/{session_id}/conversations', 'get'),
        ('/api/v1/sessions/{session_id}/conversations', 'post'),
        ('/api/v1/conversations/{conversation_id}/messages', 'get'),
        ('/api/v1/conversations/{conversation_id}/messages', 'post'),
    ]
    for path, method in protected_operations:
        operation = schema['paths'][path][method]
        assert {token_scheme} <= {name for requirement in operation['security'] for name in requirement}
    health = main.health()
    assert health['status'] == 'ok'
    assert 'api_key' not in str(health).casefold()


def test_anonymous_session_token_is_opaque_hashed_and_profile_is_validated():
    reset_database()
    created = new_session(); token = created['session_token']
    assert len(token) >= 43
    with main.ENGINE.connect() as conn:
        stored = conn.execute(select(sessions.c.token_hash).where(sessions.c.id == created['session_id'])).scalar_one()
    assert stored != token
    options = main.profile_options()
    assert {str(y['value']) for y in options['study_years']} == set(options['sections_by_year'])
    year = next(y['value'] for y in options['study_years'] if str(y['value']) in options['sections_by_year'])
    section = options['sections_by_year'][str(year)][0]
    assert options['warnings']
    updated = main.put_profile(created['session_id'], main.ProfileUpdate(study_year=year, section=section), token)
    assert updated['profile']['academic_cohort'] is None
    assert updated['profile']['semester'] is None
    assert main.get_profile(created['session_id'], token)['profile']['section'] == section
    try:
        main.put_profile(created['session_id'], main.ProfileUpdate(study_year=year, section='not-a-real-section'), None)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError('invalid session was not rejected before profile validation')
    try:
        main.put_profile(created['session_id'], main.ProfileUpdate(study_year=year, section='not-a-real-section'), token)
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError('unsupported section accepted')
    try:
        main.get_profile(created['session_id'], None)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError('missing token accepted')


def test_conversation_messages_are_isolated_and_unknown_owner_match():
    reset_database()
    a = new_session(); b = new_session()
    ca = main.create_conversation(a['session_id'], a['session_token'])['conversation_id']
    row = main._deterministic_answer('ECC-201 syllabus topics', None, [])
    assert row['presentation'] == 'course_list'
    assert row['sources']
    created = main.now_kolkata()
    user_id = str(uuid.uuid4())
    with main.ENGINE.begin() as conn:
        conn.execute(insert(messages).values(id=user_id, conversation_id=ca, role='user', content='ECC-201 syllabus topics', presentation='answer', data=None, sources=[], warnings=[], sequence=1, created_at=created))
        conn.execute(insert(messages).values(id=row['id'], conversation_id=ca, role='assistant', content=row['content'], presentation=row['presentation'], data=row['data'], sources=row['sources'], warnings=row['warnings'], sequence=2, created_at=created))
    stored_messages = main.get_messages(ca, a['session_token'])['messages']
    assert [m['role'] for m in stored_messages] == ['user', 'assistant']
    errors = []
    for cid, token in ((ca, b['session_token']), ('missing', b['session_token'])):
        try:
            main.get_messages(cid, token)
        except HTTPException as exc:
            errors.append((exc.status_code, exc.detail))
    assert errors[0] == errors[1] == (404, 'Conversation not found.')


def test_deterministic_academic_lookups_keep_source_caveats():
    reset_database()
    timetable = main._deterministic_answer('Show ECE-3 timetable', None, [])
    assert timetable['presentation'] == 'timetable'
    assert timetable['data']
    assert any('recurring' in w.casefold() for w in timetable['warnings'])
    calendar = main.calendar(on=__import__('datetime').date(2026, 9, 23))
    assert any('Timetable rescheduled' in item['title'] for item in calendar['events'])
    calendar_answer = main._deterministic_answer('What is on September 23?', None, [])
    assert any('2026-09-23' in row['dates'] for row in calendar_answer['data'])
    exams = main.exams(course_code='ECC-201')
    assert exams['exams'][0]['source_status'] == 'draft_unreviewed'
    ete = main._deterministic_answer('When is ETE for ECC-201?', None, [])
    assert ete['presentation'] == 'exam_schedule'
    assert any('draft' in w.casefold() for w in ete['warnings'])
    no_mte = main._deterministic_answer('When is MTE for ECC-201?', None, [])
    assert no_mte['presentation'] == 'answer'
    assert 'No MTE schedule record' in no_mte['content']
    # Multi-turn shorthand reuses an exact code only from this conversation.
    follow_up = main._deterministic_answer('show its syllabus', None, ['Tell me about ECC-201'])
    assert 'ECC-201' in follow_up['content']


def test_missing_model_does_not_replace_deterministic_mode(monkeypatch):
    from backend.app.config import Settings

    reset_database()
    monkeypatch.setattr(main, 'SETTINGS', Settings(_env_file=None, openai_chat_api_key=None, openai_api_key=None))
    health = main.health()
    assert health['dependencies']['chat_model'] == 'not_configured'
    answer = main._deterministic_answer('zzyzx qqqq nonexistentrecord', None, [])
    assert 'General guidance is unavailable' in answer['content']


def test_openai_chat_and_embedding_keys_are_isolated_with_legacy_fallback(monkeypatch):
    from types import SimpleNamespace

    import openai

    from backend.app.config import Settings
    from backend.app.retrieval import _identity, embed_texts

    settings = Settings(_env_file=None, openai_embedding_api_key='embedding-dummy',
                        openai_api_key='legacy-dummy')
    assert _identity(settings) == ('openai', 'text-embedding-3-small', 'embedding-dummy')
    assert settings.resolved_openai_chat_api_key == 'legacy-dummy'

    legacy = Settings(_env_file=None, openai_api_key='legacy-dummy')
    assert legacy.resolved_openai_embedding_api_key == 'legacy-dummy'
    assert legacy.resolved_openai_chat_api_key == 'legacy-dummy'

    chat_only = Settings(_env_file=None, openai_chat_api_key='chat-dummy',
                         openai_embedding_api_key=None, openai_api_key=None)
    assert _identity(chat_only)[2] is None
    assert chat_only.resolved_openai_chat_api_key == 'chat-dummy'

    selected = Settings(_env_file=None, openai_embedding_api_key='embedding-dummy',
                        openai_chat_api_key='chat-dummy', openai_api_key='legacy-dummy')
    assert selected.resolved_openai_embedding_api_key == 'embedding-dummy'
    assert selected.resolved_openai_chat_api_key == 'chat-dummy'

    embedding_keys = []

    class FakeEmbeddings:
        def create(self, **_kwargs):
            return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[3.0, 4.0])], model='mock-version')

    class FakeOpenAI:
        def __init__(self, api_key):
            embedding_keys.append(api_key)
            self.embeddings = FakeEmbeddings()

        def close(self):
            pass

    monkeypatch.setattr(openai, 'OpenAI', FakeOpenAI)
    vectors, version = embed_texts(['sample'], selected)
    assert embedding_keys == ['embedding-dummy']
    assert vectors == [[3.0, 4.0]] and version == 'mock-version'

    chat_keys = []

    class FakeResponses:
        async def create(self, **_kwargs):
            return SimpleNamespace(id='mock-response', output=[], output_text='Mock answer')

    class FakeAsyncOpenAI:
        def __init__(self, api_key):
            chat_keys.append(api_key)
            self.responses = FakeResponses()

        async def close(self):
            pass

    monkeypatch.setattr(openai, 'AsyncOpenAI', FakeAsyncOpenAI)
    monkeypatch.setattr(main, 'SETTINGS', selected)
    monkeypatch.setattr(main, 'ENGINE', make_engine('sqlite:///:memory:'))
    response = main._responses_answer('Explain a concept', None)
    try:
        response.send(None)
    except StopIteration as completed:
        answer = completed.value
    else:
        raise AssertionError('Mock Responses call unexpectedly needed an event loop.')
    assert answer['content'] == 'Mock answer'
    assert chat_keys == ['chat-dummy']
    assert main.health()['dependencies']['chat_model'] == 'configured'

    embedding_only = Settings(_env_file=None, openai_embedding_api_key='embedding-dummy',
                              openai_chat_api_key=None, openai_api_key=None)
    monkeypatch.setattr(main, 'SETTINGS', embedding_only)
    assert main.health()['dependencies']['chat_model'] == 'not_configured'


def test_model_tool_arguments_are_schema_validated_and_allowlisted():
    reset_database()
    result = main._tool_data('course_details', {'course_code':'ECC-201'}, None)
    assert result['course']['code'] == 'ECC-201'
    try:
        main._tool_data('get_timetable', {'study_year':99}, None)
    except Exception:
        pass
    else:
        raise AssertionError('out-of-range tool argument accepted')
    try:
        main._tool_data('search_sources', {'query':'course','sql':'DROP TABLE courses'}, None)
    except Exception:
        pass
    else:
        raise AssertionError('extra tool argument accepted')


def test_every_chunk_source_version_has_manifest_document_links():
    from backend.app.data import DATA
    from backend.app.db import source_chunk_documents, source_chunks, source_documents
    import json

    reset_database()
    chunks = [json.loads(line) for line in (DATA / 'embedding_chunks.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    with main.ENGINE.connect() as conn:
        document_ids = {row[0] for row in conn.execute(select(source_documents.c.id)).all()}
        links = {(row.chunk_id, row.document_id) for row in conn.execute(select(source_chunk_documents)).all()}
        imported_chunks = {row.id for row in conn.execute(select(source_chunks.c.id)).all()}
    assert hashlib.sha256(b'None').hexdigest() not in document_ids
    for manifest_name in ('local_source_manifest.json', 'web_source_manifest.json'):
        manifest = json.loads((DATA / manifest_name).read_text(encoding='utf-8'))
        expected = {str(row[key]) for row in manifest for key in ('sha256','source_id') if row.get(key)}
        assert expected <= document_ids
    assert len(imported_chunks) == len(chunks)
    for chunk in chunks:
        source_ids = set(chunk['metadata'].get('source_version_ids') or [])
        assert source_ids <= document_ids
        assert {(chunk['chunk_id'], source_id) for source_id in source_ids} <= links


def test_version_scoped_index_build_query_and_provider_isolation():
    from backend.app.config import Settings
    from backend.app.db import index_versions, source_embedding_vectors, source_chunks
    from backend.app.retrieval import build_index, dense_search, reciprocal_rank_fusion

    engine = make_engine('sqlite:///:memory:')
    settings = Settings(embedding_provider='openai', openai_api_key='mock-key', openai_embedding_model='text-embedding-3-small')
    def mock_embed(texts, _settings):
        return [[3.0, 4.0] for _ in texts], 'text-embedding-3-small-mock-v1'
    manifest = build_index(engine, batch_size=128, settings=settings, embedder=mock_embed)
    assert manifest['complete'] and manifest['dimensions'] == 2 and manifest['normalization'] == 'l2'
    with engine.connect() as conn:
        chunk_count = conn.execute(select(source_chunks.c.id)).all()
        vectors = conn.execute(select(source_embedding_vectors.c.chunk_id).where(source_embedding_vectors.c.index_version_id == manifest['index_version_id'])).all()
        stored = conn.execute(select(index_versions.c.provider, index_versions.c.model, index_versions.c.model_version, index_versions.c.dimensions, index_versions.c.complete).where(index_versions.c.id == manifest['index_version_id'])).one()
    assert len(vectors) == len(chunk_count)
    assert tuple(stored) == ('openai', 'text-embedding-3-small', 'text-embedding-3-small-mock-v1', 2, True)
    dense, status = dense_search(engine, 'course search', 3, settings, embedder=mock_embed)
    assert status == 'ready' and dense
    wrong_version = lambda texts, _settings: ([[1.0, 0.0] for _ in texts], 'text-embedding-3-small-other-version')
    assert dense_search(engine, 'course search', 3, settings, embedder=wrong_version) == ([], 'manifest_mismatch')
    azure = Settings(embedding_provider='azure', azure_openai_api_key='mock', azure_openai_endpoint='https://example.invalid', azure_openai_embedding_deployment='ece-embeddings', azure_openai_api_version='v1')
    never_called = lambda *_: (_ for _ in ()).throw(AssertionError('must not query a different provider index'))
    dense2, status2 = dense_search(engine, 'course search', 3, azure, embedder=never_called)
    assert dense2 == [] and status2 == 'index_incomplete'
    assert reciprocal_rank_fusion([{'chunk_id':'a','score':1}], [{'chunk_id':'b','score':0.9}], 2)[0]['score'] > 0
    no_key = Settings(embedding_provider='openai', openai_api_key=None, openai_embedding_model='text-embedding-3-small')
    assert dense_search(engine, 'query', 1, no_key)[1] == 'credentials_missing'


def test_old_message_table_gets_deterministic_sequence_backfill():
    from backend.app.db import ensure_compat_schema

    engine = make_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE messages (id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, created_at TEXT)')
        conn.exec_driver_sql("INSERT INTO messages(id, conversation_id, role, created_at) VALUES ('000-assistant','c','assistant','2026-01-01'),('zzz-user','c','user','2026-01-01')")
    ensure_compat_schema(engine)
    with engine.connect() as conn:
        rows = conn.exec_driver_sql('SELECT id, role, sequence FROM messages ORDER BY sequence').all()
    assert rows == [('zzz-user', 'user', 1), ('000-assistant', 'assistant', 2)]


def test_request_size_limit_counts_streamed_bytes_and_preserves_normal_body():
    import json

    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from backend.app.main import RequestSizeLimitMiddleware

    async def exercise(events, headers=(), consume_body=True, cors=False):
        endpoint_calls = []

        async def endpoint(scope, receive, send):
            endpoint_calls.append(True)
            request = Request(scope, receive=receive)
            if consume_body:
                body = await request.body()
            else:
                await receive()
                body = b''
            response = JSONResponse({'body': body.decode()})
            await response(scope, receive, send)

        middleware = RequestSizeLimitMiddleware(endpoint, max_bytes=5)
        if cors:
            from starlette.middleware.cors import CORSMiddleware

            middleware = CORSMiddleware(middleware, allow_origins=['https://ui.example'],
                                         allow_methods=['POST'], allow_headers=['Content-Type'])
            headers = (*headers, (b'origin', b'https://ui.example'))
        pending = list(events)
        sent = []

        async def receive():
            return pending.pop(0) if pending else {'type': 'http.disconnect'}

        async def send(message):
            sent.append(message)

        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'method': 'POST', 'path': '/',
                 'query_string': b'', 'headers': list(headers), 'server': ('test', 80),
                 'client': ('test', 1), 'scheme': 'http', 'http_version': '1.1'}
        await middleware(scope, receive, send)
        response_start = next(message for message in sent if message['type'] == 'http.response.start')
        status = response_start['status']
        response_body = b''.join(message.get('body', b'') for message in sent if message['type'] == 'http.response.body')
        return status, json.loads(response_body), bool(endpoint_calls), response_start['headers']

    def run_immediate(coroutine):
        try:
            coroutine.send(None)
        except StopIteration as completed:
            return completed.value
        raise AssertionError('Direct ASGI test unexpectedly yielded to an event loop.')

    too_large_events = [
        {'type': 'http.request', 'body': b'123', 'more_body': True},
        {'type': 'http.request', 'body': b'456', 'more_body': False},
    ]
    status, body, endpoint_called, _ = run_immediate(exercise(too_large_events))
    assert status == 413
    assert body == {'error': {'code': 'request_too_large', 'message': 'Request body exceeds the configured limit.', 'details': {}}}
    assert not endpoint_called

    status, body, endpoint_called, _ = run_immediate(exercise(too_large_events, consume_body=False))
    assert status == 413
    assert body['error']['code'] == 'request_too_large'
    assert not endpoint_called

    status, body, endpoint_called, _ = run_immediate(exercise(too_large_events, [(b'content-length', b'2')]))
    assert status == 413
    assert body['error']['code'] == 'request_too_large'
    assert not endpoint_called

    normal_events = [
        {'type': 'http.request', 'body': b'12', 'more_body': True},
        {'type': 'http.request', 'body': b'345', 'more_body': False},
    ]
    status, body, endpoint_called, _ = run_immediate(exercise(normal_events))
    assert status == 200
    assert body == {'body': '12345'}
    assert endpoint_called

    status, body, endpoint_called, headers = run_immediate(exercise(too_large_events, cors=True))
    assert status == 413 and not endpoint_called
    assert (b'access-control-allow-origin', b'https://ui.example') in headers
