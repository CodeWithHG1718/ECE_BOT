-- Signal v1 PostgreSQL schema. This is the initial system-of-record migration.
-- Requires PostgreSQL 15+ and pgvector. Embeddings are provider/model/dimension scoped.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS anonymous_sessions (
  id varchar(64) PRIMARY KEY,
  token_hash varchar(64) NOT NULL,
  created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
  session_id varchar(64) PRIMARY KEY REFERENCES anonymous_sessions(id) ON DELETE CASCADE,
  study_year integer NOT NULL CHECK (study_year BETWEEN 1 AND 4),
  section varchar(32) NOT NULL,
  academic_cohort varchar(32),
  semester integer CHECK (semester IS NULL OR semester BETWEEN 1 AND 12)
);
CREATE TABLE IF NOT EXISTS conversations (
  id varchar(64) PRIMARY KEY,
  session_id varchar(64) NOT NULL REFERENCES anonymous_sessions(id) ON DELETE CASCADE,
  title varchar(160) NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS conversations_owner_idx ON conversations(session_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
  id varchar(64) PRIMARY KEY,
  conversation_id varchar(64) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role varchar(16) NOT NULL CHECK (role IN ('user','assistant')),
  content text NOT NULL,
  presentation varchar(32) NOT NULL,
  data jsonb,
  sources jsonb NOT NULL DEFAULT '[]'::jsonb,
  warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  sequence integer NOT NULL,
  created_at timestamptz NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS messages_conversation_sequence_uq ON messages(conversation_id, sequence);

CREATE TABLE IF NOT EXISTS course_identities (
  id varchar(96) PRIMARY KEY,
  code varchar(32) NOT NULL UNIQUE,
  title text NOT NULL,
  payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS course_offerings (
  id varchar(128) PRIMARY KEY,
  course_id varchar(96) NOT NULL REFERENCES course_identities(id),
  academic_session varchar(32),
  cohort varchar(32),
  year integer,
  semester integer,
  applicability text
);
CREATE INDEX IF NOT EXISTS course_offerings_filter_idx ON course_offerings(year, semester, academic_session, cohort);
CREATE TABLE IF NOT EXISTS syllabus_topics (
  id varchar(96) PRIMARY KEY,
  course_id varchar(96) REFERENCES course_identities(id),
  source_code varchar(32),
  ordinal integer,
  text text NOT NULL,
  evidence jsonb
);
CREATE INDEX IF NOT EXISTS syllabus_topics_code_idx ON syllabus_topics(source_code, ordinal);
CREATE TABLE IF NOT EXISTS schedule_events (
  id varchar(96) PRIMARY KEY,
  event_type varchar(32) NOT NULL,
  course_code varchar(32),
  academic_session varchar(32),
  payload jsonb NOT NULL,
  evidence jsonb
);
CREATE INDEX IF NOT EXISTS schedule_events_course_idx ON schedule_events(course_code, event_type);
CREATE TABLE IF NOT EXISTS source_documents (
  id varchar(96) PRIMARY KEY,
  path text,
  url text,
  checksum varchar(128),
  academic_session varchar(32),
  applicability text,
  verification_status varchar(48),
  imported_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS source_chunks (
  id varchar(96) PRIMARY KEY,
  document_id varchar(96) REFERENCES source_documents(id),
  text text NOT NULL,
  metadata jsonb NOT NULL,
  keyword_vector text NOT NULL,
  search_document tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text, ''))) STORED
);
CREATE INDEX IF NOT EXISTS source_chunks_search_document_gin ON source_chunks USING GIN(search_document);
CREATE INDEX IF NOT EXISTS source_chunks_metadata_gin ON source_chunks USING GIN(metadata);
CREATE TABLE IF NOT EXISTS source_chunk_documents (
  chunk_id varchar(96) NOT NULL REFERENCES source_chunks(id) ON DELETE CASCADE,
  document_id varchar(96) NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
  PRIMARY KEY(chunk_id, document_id)
);
CREATE TABLE IF NOT EXISTS source_embeddings (
  chunk_id varchar(96) PRIMARY KEY REFERENCES source_chunks(id) ON DELETE CASCADE,
  provider varchar(32) NOT NULL,
  model varchar(96) NOT NULL,
  version varchar(64),
  dimensions integer NOT NULL,
  normalization varchar(32) NOT NULL,
  embedding_json jsonb
);
CREATE TABLE IF NOT EXISTS faculty (
  id varchar(96) PRIMARY KEY,
  name text NOT NULL,
  payload jsonb NOT NULL,
  evidence jsonb
);
CREATE TABLE IF NOT EXISTS projects (
  id varchar(96) PRIMARY KEY,
  title text,
  payload jsonb NOT NULL,
  evidence jsonb
);
CREATE TABLE IF NOT EXISTS resources (
  id varchar(96) PRIMARY KEY,
  resource_type varchar(48) NOT NULL,
  title text,
  payload jsonb NOT NULL,
  evidence jsonb
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
  id varchar(64) PRIMARY KEY,
  started_at timestamptz NOT NULL,
  completed_at timestamptz,
  status varchar(32) NOT NULL,
  source_count integer NOT NULL
);
CREATE TABLE IF NOT EXISTS index_versions (
  id varchar(96) PRIMARY KEY,
  provider varchar(32) NOT NULL,
  model varchar(96) NOT NULL,
  model_version varchar(64),
  dimensions integer NOT NULL,
  normalization varchar(32) NOT NULL,
  complete boolean NOT NULL,
  created_at timestamptz NOT NULL,
  UNIQUE(provider, model, model_version, dimensions, normalization)
);
CREATE TABLE IF NOT EXISTS source_embedding_vectors (
  chunk_id varchar(96) NOT NULL REFERENCES source_chunks(id) ON DELETE CASCADE,
  index_version_id varchar(96) NOT NULL REFERENCES index_versions(id) ON DELETE CASCADE,
  embedding_json jsonb NOT NULL,
  embedding vector,
  PRIMARY KEY(chunk_id, index_version_id)
);
CREATE INDEX IF NOT EXISTS source_embedding_vectors_version_idx ON source_embedding_vectors(index_version_id, chunk_id);
CREATE TABLE IF NOT EXISTS feedback (
  id varchar(64) PRIMARY KEY,
  message_id varchar(64) NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  rating integer NOT NULL CHECK (rating BETWEEN -1 AND 1),
  created_at timestamptz NOT NULL
);
