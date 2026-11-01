# Signal 2.0 backend

FastAPI service for the versioned `/api/v1` contract. OpenAPI is published at `/openapi.json` and Swagger UI at `/docs`.

## Local start

From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item backend\.env.example .env
uvicorn backend.app.main:app --reload
```

The default local database is `backend/signal.db` (SQLite). Set `DATABASE_URL` to a PostgreSQL SQLAlchemy URL (`postgresql+psycopg://...`) for PostgreSQL. On a fresh PostgreSQL database, apply `backend/migrations/0001_initial.sql` and then `backend/migrations/0002_hybrid_index_and_message_order.sql` before starting the service. On a database made with the earlier backend schema, apply only `0002`; it adds message ordering and versioned vector storage without deleting old data. Keep credentials in the ignored root `.env` or deployment secrets. OpenAI chat and embedding credentials are separate; missing credentials leave deterministic endpoints available.

Legacy messages with identical timestamps are backfilled with user before assistant, then ID order. Timestamps cannot recover original order among same-role messages.

## Data and coverage

At startup, source-backed JSON under `datafiles/academic/` is imported into relational course, offering, syllabus, schedule, source, resource, faculty and project tables. Session tokens are generated with 256 bits of entropy; only SHA-256 hashes are stored. Conversation ownership is checked on every request. Logs do not contain request bodies or credentials.

`GET /api/v1/courses`, `/timetable`, `/calendar`, `/exams`, `/resources`, `/faculty`, `/projects`, and `/search` provide deterministic source lookups. `POST /api/v1/conversations/{id}/messages` recognizes exact course codes, timetable, calendar, exam and source-search requests. Dates/times cite the original source evidence, with draft/OCR/coverage caveats included. The current imported records do not establish every cohort's applicability. Profile options only include years with at least one source-recorded section; those section values are OCR-transcribed and marked applicability-unverified.

## Hybrid retrieval index

Retrieval imports local and web source manifests first, then links every persisted chunk to every `source_version_id` in `source_chunk_documents`. Chunks with an unmapped source version are skipped. The importer does not create placeholder source documents.

Set exactly one `EMBEDDING_PROVIDER` (`openai` or `azure`) and its corresponding credentials/model values, then build a complete index:

```powershell
python -m backend.app.index --batch-size 64
```

OpenAI embeddings use `OPENAI_EMBEDDING_API_KEY` and `OPENAI_EMBEDDING_MODEL`. Azure requires `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`, and `AZURE_OPENAI_API_VERSION`. `OPENAI_CHAT_API_KEY` configures the Responses API. Dedicated keys take precedence; legacy `OPENAI_API_KEY` fills either key only when its dedicated setting is empty. The command embeds the imported source chunks in batches, L2-normalizes the vectors, and publishes a complete manifest only after every chunk is stored. A provider or model change creates a distinct manifest and vector set; it never reuses or falls back to another provider's vectors. A failed build rolls back and remains unavailable to retrieval.

PostgreSQL search combines `tsvector` full-text results and pgvector cosine results with reciprocal-rank fusion. pgvector HNSW indexes are built per manifest and dimension. SQLite offers the same manifest checks and cosine path for local development, using JSON vectors; it uses token-overlap keyword ranking. If credentials, a matching complete index, or the query embedding is unavailable, `/search` and model tools return keyword results with an explicit retrieval status. The model is never asked to use incompatible or incomplete vectors.

## Limitations

The Responses API client is enabled only when `OPENAI_CHAT_API_KEY` or its legacy fallback is configured; it uses validated read-only academic tools and attaches citations collected from backend source records. Dense retrieval requires `OPENAI_EMBEDDING_API_KEY` (or the legacy fallback) for the OpenAI provider, or matching Azure credentials, plus running the index build command. PostgreSQL supports pgvector HNSW and full-text search; SQLite supports local JSON-vector similarity and token-overlap keyword ranking. No admin, uploads, deployment, or student login is included. Live PostgreSQL/pgvector and provider requests were not exercised by the local test suite.

Set narrow comma-separated `API_CORS_ORIGINS` for the web origin. Request bodies are limited by `MAX_REQUEST_BYTES` (32 KiB default); middleware counts streamed body bytes, including when `Content-Length` is absent or too small. All validation errors use the documented `{ "error": { "code", "message", "details" } }` envelope. `X-Session-Token` is required for all protected routes and must never be included in URLs or analytics.
