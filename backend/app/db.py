from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, MetaData, String, Table, Text, UniqueConstraint, create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from .config import get_settings

metadata = MetaData()
sessions = Table('anonymous_sessions', metadata,
    Column('id', String(64), primary_key=True), Column('token_hash', String(64), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False))
profiles = Table('profiles', metadata,
    Column('session_id', String(64), ForeignKey('anonymous_sessions.id', ondelete='CASCADE'), primary_key=True),
    Column('study_year', Integer, nullable=False), Column('section', String(32), nullable=False),
    Column('academic_cohort', String(32)), Column('semester', Integer),
    Column('hss_course', String(32)), Column('oec_course', String(32)))
conversations = Table('conversations', metadata,
    Column('id', String(64), primary_key=True), Column('session_id', String(64), ForeignKey('anonymous_sessions.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('title', String(160), nullable=False), Column('created_at', DateTime(timezone=True), nullable=False), Column('updated_at', DateTime(timezone=True), nullable=False))
messages = Table('messages', metadata,
    Column('id', String(64), primary_key=True), Column('conversation_id', String(64), ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('role', String(16), nullable=False), Column('content', Text, nullable=False), Column('presentation', String(32), nullable=False),
    Column('data', JSON), Column('sources', JSON, nullable=False), Column('warnings', JSON, nullable=False),
    Column('sequence', Integer, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    UniqueConstraint('conversation_id', 'sequence', name='messages_conversation_sequence_uq'))

# Canonical academic tables retain records independently from conversations.
courses = Table('course_identities', metadata,
    Column('id', String(96), primary_key=True), Column('code', String(32), nullable=False, unique=True, index=True), Column('title', Text, nullable=False), Column('payload', JSON, nullable=False))
offerings = Table('course_offerings', metadata,
    Column('id', String(128), primary_key=True), Column('course_id', String(96), ForeignKey('course_identities.id'), nullable=False),
    Column('academic_session', String(32)), Column('cohort', String(32)), Column('year', Integer), Column('semester', Integer), Column('applicability', Text))
syllabus_topics = Table('syllabus_topics', metadata,
    Column('id', String(96), primary_key=True), Column('course_id', String(96), ForeignKey('course_identities.id'), nullable=True),
    Column('source_code', String(32)), Column('ordinal', Integer), Column('text', Text, nullable=False), Column('evidence', JSON))
schedule_events = Table('schedule_events', metadata,
    Column('id', String(96), primary_key=True), Column('event_type', String(32), nullable=False), Column('course_code', String(32), index=True),
    Column('academic_session', String(32)), Column('payload', JSON, nullable=False), Column('evidence', JSON))
source_documents = Table('source_documents', metadata,
    Column('id', String(96), primary_key=True), Column('path', Text), Column('url', Text), Column('checksum', String(128)),
    Column('academic_session', String(32)), Column('applicability', Text), Column('verification_status', String(48)),
    Column('imported_at', DateTime(timezone=True), nullable=False))
source_chunks = Table('source_chunks', metadata,
    Column('id', String(96), primary_key=True), Column('document_id', String(96), ForeignKey('source_documents.id'), nullable=True),
    Column('text', Text, nullable=False), Column('metadata', JSON, nullable=False), Column('keyword_vector', Text, nullable=False))
source_chunk_documents = Table('source_chunk_documents', metadata,
    Column('chunk_id', String(96), ForeignKey('source_chunks.id', ondelete='CASCADE'), primary_key=True),
    Column('document_id', String(96), ForeignKey('source_documents.id', ondelete='CASCADE'), primary_key=True))
source_embeddings = Table('source_embeddings', metadata,
    Column('chunk_id', String(96), ForeignKey('source_chunks.id', ondelete='CASCADE'), primary_key=True),
    Column('provider', String(32), nullable=False), Column('model', String(96), nullable=False), Column('version', String(64)),
    Column('dimensions', Integer, nullable=False), Column('normalization', String(32), nullable=False), Column('embedding_json', JSON))
faculty = Table('faculty', metadata,
    Column('id', String(96), primary_key=True), Column('name', Text, nullable=False), Column('payload', JSON, nullable=False), Column('evidence', JSON))
projects = Table('projects', metadata,
    Column('id', String(96), primary_key=True), Column('title', Text), Column('payload', JSON, nullable=False), Column('evidence', JSON))
resources = Table('resources', metadata,
    Column('id', String(96), primary_key=True), Column('resource_type', String(48), nullable=False), Column('title', Text),
    Column('payload', JSON, nullable=False), Column('evidence', JSON))
ingestion_runs = Table('ingestion_runs', metadata,
    Column('id', String(64), primary_key=True), Column('started_at', DateTime(timezone=True), nullable=False),
    Column('completed_at', DateTime(timezone=True)), Column('status', String(32), nullable=False), Column('source_count', Integer, nullable=False))
index_versions = Table('index_versions', metadata,
    Column('id', String(96), primary_key=True), Column('provider', String(32), nullable=False), Column('model', String(96), nullable=False),
    Column('model_version', String(64)), Column('dimensions', Integer, nullable=False), Column('normalization', String(32), nullable=False),
    Column('complete', Boolean, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False))
source_embedding_vectors = Table('source_embedding_vectors', metadata,
    Column('chunk_id', String(96), ForeignKey('source_chunks.id', ondelete='CASCADE'), primary_key=True),
    Column('index_version_id', String(96), ForeignKey('index_versions.id', ondelete='CASCADE'), primary_key=True),
    Column('embedding_json', JSON, nullable=False))
feedback = Table('feedback', metadata,
    Column('id', String(64), primary_key=True), Column('message_id', String(64), ForeignKey('messages.id', ondelete='CASCADE'), nullable=False),
    Column('rating', Integer, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False))


def make_engine(url: str | None = None) -> Engine:
    default_path = (Path(__file__).resolve().parents[2] / 'backend' / 'signal.db').as_posix()
    url = url or get_settings().database_url or f"sqlite:///{default_path}"
    if os.environ.get('VERCEL') and not url.startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
        raise RuntimeError('Vercel requires a persistent PostgreSQL DATABASE_URL; local SQLite is not supported for deployed sessions.')
    if url.startswith('postgres://'):
        url = 'postgresql+psycopg://' + url.removeprefix('postgres://')
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    kwargs = {'pool_pre_ping': True}
    if url.startswith('sqlite'):
        kwargs['connect_args'] = {'check_same_thread': False}
        if url in ('sqlite://', 'sqlite:///:memory:'):
            kwargs['poolclass'] = StaticPool
    engine = create_engine(url, **kwargs)
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def _sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.close()
    return engine


def now_kolkata() -> datetime:
    return datetime.now(ZoneInfo('Asia/Kolkata'))


def ensure_compat_schema(engine: Engine) -> None:
    """Apply additive local/online compatibility changes before importing records."""
    inspector = inspect(engine)
    if engine.dialect.name == 'postgresql' and 'source_chunks' in inspector.get_table_names():
        with engine.begin() as conn:
            conn.exec_driver_sql("""ALTER TABLE source_chunks ADD COLUMN IF NOT EXISTS search_document
                tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text, ''))) STORED""")
            conn.exec_driver_sql('CREATE INDEX IF NOT EXISTS source_chunks_search_document_gin ON source_chunks USING GIN(search_document)')
    if 'profiles' in inspector.get_table_names():
        profile_columns = {c['name'] for c in inspector.get_columns('profiles')}
        with engine.begin() as conn:
            for name in ('hss_course', 'oec_course'):
                if name not in profile_columns:
                    conn.exec_driver_sql(f'ALTER TABLE profiles ADD COLUMN {name} VARCHAR(32)')
    if 'messages' not in inspector.get_table_names():
        return
    columns = {c['name'] for c in inspector.get_columns('messages')}
    with engine.begin() as conn:
        if 'sequence' not in columns:
            conn.exec_driver_sql('ALTER TABLE messages ADD COLUMN sequence INTEGER NOT NULL DEFAULT 0')
        conn.exec_driver_sql("""
            UPDATE messages AS current_message
            SET sequence = (
              SELECT COUNT(*) FROM messages AS prior_message
              WHERE prior_message.conversation_id = current_message.conversation_id
                AND (prior_message.created_at < current_message.created_at
                  OR (prior_message.created_at = current_message.created_at AND (
                    CASE prior_message.role WHEN 'user' THEN 0 WHEN 'assistant' THEN 1 ELSE 2 END
                      < CASE current_message.role WHEN 'user' THEN 0 WHEN 'assistant' THEN 1 ELSE 2 END
                    OR (CASE prior_message.role WHEN 'user' THEN 0 WHEN 'assistant' THEN 1 ELSE 2 END
                      = CASE current_message.role WHEN 'user' THEN 0 WHEN 'assistant' THEN 1 ELSE 2 END
                      AND prior_message.id <= current_message.id)
                  ))
            )
            )
            WHERE sequence = 0
        """)
        conn.exec_driver_sql('CREATE UNIQUE INDEX IF NOT EXISTS messages_conversation_sequence_uq ON messages(conversation_id, sequence)')


def json_load(value):
    if isinstance(value, str):
        return json.loads(value)
    return value
