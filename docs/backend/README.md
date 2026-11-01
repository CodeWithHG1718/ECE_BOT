# Signal 2.0 Backend Task

This brief defines backend work for Signal 2.0. The frontend can develop in parallel using this stable `/api/v1` contract and [`../frontend/README.md`](../frontend/README.md).

## Existing system and migration approach

The repository already has a working Python academic-data pipeline and local/Telegram chatbot. Reuse its structured records, source evidence, deterministic course/timetable/calendar logic, chunking, and retrieval rather than building a disconnected knowledge base. Relevant existing areas include `ingestion/`, `datafiles/academic/`, and `bot/`.

The current demo selects Azure `text-embedding-3-small` from the local ignored `.env`; BGE-M3 has a separate local index. Azure vectors have 1,536 dimensions. The new product direction names OpenAI `gpt-6-luna` and `text-embedding-3-small`, with Azure optional. Do not assume vectors from different provider/model identities can be mixed: retain model/version/dimension/normalization manifests and rebuild a complete index for the selected provider unless compatibility is demonstrated. A new GPT chat key has not yet been supplied; keep chat configuration server-side and allow deterministic lookups to work without it.

Build a new **`backend/`** FastAPI service. Keep the existing `bot/` local and Telegram surfaces working while the API is introduced. The old `frontend/` prototype is ignored; the new website will live under `apps/web/`.

## Ownership and parallel-work boundary

Backend ownership is `backend/**`, backend migrations, backend tests, and the API contract in this README. The frontend owns `apps/web/**` and consumes the versioned contract. Do not edit frontend implementation files. Avoid changing `bot/**` or shared ingestion behavior unless required for a reusable service seam; preserve the local bot and coordinate any shared contract/data-schema change before landing it.

Publish an OpenAPI schema from the FastAPI app as soon as the routes exist. Keep its request/response shapes aligned with this document. Changes to `/api/v1` must be backward-compatible; discuss a breaking change with the frontend owner first.

## Target architecture

- FastAPI owns session/profile loading, conversation history, retrieval, tool execution, model calls, validation, and source citations.
- PostgreSQL is the system of record; use pgvector for embeddings and PostgreSQL full-text search or a measured BM25-capable search component for keyword retrieval.
- Reuse existing ingestion code to import source-backed JSON and approved extracted data. Preserve source URL/path, checksum, page or workbook locator, academic session, applicability, verification status, and import timestamp.
- Keep academic facts structured and deterministic. Use GPT tool calling for intent interpretation and multi-step questions, not to invent course, timetable, exam, or source records.
- Treat the model as optional at runtime until the API key is configured. Missing model credentials must produce a clear capability status; deterministic profile, course, timetable, and sourced lookup endpoints must continue to work.

## Backend-owned API contract (v1)

All routes are under `/api/v1`. JSON uses ISO dates and 24-hour local times; timetable/exam times include `Asia/Kolkata` explicitly. Return validation errors as `{ "error": { "code": "...", "message": "...", "details": {} } }` without stack traces or secret values.

### Health and profile

`GET /api/v1/health`

Returns service readiness without exposing configuration values:

```json
{
  "status": "ok",
  "dependencies": { "database": "ready", "chat_model": "not_configured", "embeddings": "azure" }
}
```

`GET /api/v1/profile-options`

Returns only year/section values supported by validated source records:

```json
{
  "study_years": [{ "value": 1, "label": "First Year" }],
  "sections_by_year": { "1": ["25EC1"] },
  "academic_sessions": [{ "value": "2026-27", "label": "Autumn 2026–27" }]
}
```

`POST /api/v1/sessions` creates a lightweight anonymous session and returns `{ "session_id": "...", "session_token": "...", "profile": null }`. `session_id` is a random public identifier; generate `session_token` as an unguessable credential with at least 256 bits of entropy. Store only a hash of the token server-side where practical.

`GET /api/v1/sessions/{session_id}/profile` and `PUT /api/v1/sessions/{session_id}/profile` read/update the profile. Require `X-Session-Token` and verify it belongs to the path’s `session_id`. The update body is `{ "study_year": 2, "section": "...", "academic_cohort": null, "semester": null }`. Validate the section against the year’s supported options. Do not infer a cohort or semester from year alone.

### Conversation and chat

- `GET /api/v1/sessions/{session_id}/conversations` lists that session’s conversations as `{ "conversations": [{ "conversation_id": "...", "title": "...", "created_at": "...", "updated_at": "..." }] }`. Require and validate `X-Session-Token`.
- `POST /api/v1/sessions/{session_id}/conversations` creates one and returns `{ "conversation_id": "..." }`. Require and validate `X-Session-Token`.
- `GET /api/v1/conversations/{conversation_id}/messages` returns `{ "messages": [...] }` only when `X-Session-Token` identifies the session that owns the conversation.
- `POST /api/v1/conversations/{conversation_id}/messages` accepts `{ "text": "..." }` and returns `{ "user_message": { ... }, "assistant_message": { ... } }`. It also requires the owning `X-Session-Token` header.

Verify session-token ownership server-side on every protected request. Return the same not-found response for unknown and non-owned conversation IDs. The frontend keeps the opaque session token in session-scoped browser storage and sends it only in the `X-Session-Token` header; never put it in a URL, analytics event, or log.

Assistant message shape:

```json
{
  "id": "message-id",
  "role": "assistant",
  "content": "The sourced explanation or concise lookup result.",
  "presentation": "answer",
  "data": null,
  "sources": [{ "title": "Source title", "url": "https://...", "page": 12, "status": "source_backed" }],
  "warnings": [],
  "created_at": "2026-11-01T12:00:00+05:30"
}
```

`presentation` is one of `answer`, `course_list`, `timetable`, `exam_schedule`, `resources`, `faculty`, or `projects`. `data` contains validated structured records for the selected presentation; `content` contains generated or deterministic explanatory text. Never place unsupported facts in `data` to make the UI look complete. Streaming is a later compatible enhancement; the initial contract is JSON.

## Data and academic guarantees

Current collected data includes 120 course identities; 232 source syllabus topics; 221 OCR timetable records; 808 draft ETE schedule/venue records across 639 course codes; 61 Autumn 2026–27 calendar records; 194 syllabus book references; 100 collected book chapter references; 693 NPTEL lecture records; 38 faculty profiles; and 229 department project records. These counts do not establish cohort applicability or current availability.

Specific caveats the API must preserve:

- The ETE schedule is draft and its printed program/range assignments do not confirm an individual student’s registration. The detailed entries cover Nov 13–21; the broad calendar ETE period ends Nov 24, and course assignments for Nov 23–24 remain unresolved.
- The academic calendar applies to programs other than MBA and contains tentative/conditional dates. Return source notes for convocation and lunar-calendar caveats.
- Recurring timetable entries are not dated occurrences or proof of live changes/holidays. Do not replace missing section/room/faculty values with guesses.
- Book data is a selected table of contents and reading-list guide, not full textbook content.
- Keep enrollment rosters and student identifiers out of chunks, embeddings, logs, and public source snapshots. The original ETE PDF is Git-ignored; the repository uses a checksummed roster-free schedule snapshot.
- Missing or unverified official information must be stated as missing; never hallucinate exam dates, faculty assignments, notices, or source URLs.

## Retrieval and model work

1. Import source-backed JSON into normalized relational tables. Separate course identity from an offering in an academic session/cohort.
2. Store source documents, chunks, ingestion runs, index versions, verification status, and provenance. Use pgvector and a keyword index without combining incompatible embeddings.
3. Add tools for profile, courses, course details/syllabus, timetable, calendar/exams, resources, faculty, projects, and hybrid search. Validate tool arguments and result schemas.
4. Use the Responses API with configurable `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL=gpt-6-luna`, and `OPENAI_EMBEDDING_MODEL=text-embedding-3-small`. Keep credentials on the server. Azure endpoint/deployment settings remain optional and separate.
5. Relevance-check retrieved sources before generation. The model may explain general ECE concepts, but label general guidance separately from institutional records. Validate source IDs and attach citations from backend records only.
6. Preserve a deterministic mode when the model is unavailable. Never return fake generated answers or silently switch embedding providers.

## Database and privacy

Start with migrations for anonymous sessions, profiles, conversations/messages, course identities/offerings, syllabus topics, schedule/calendar events, source documents/chunks/embeddings, faculty/projects/resources, ingestion/index versions, and feedback. Add foreign keys and uniqueness constraints; keep row-level ownership checks for session conversations. Do not require student names, roll numbers, or institute login for the initial demo. Add admin auth and file-upload workflows only in a separately scoped phase.

Configuration belongs in a local ignored `.env` or deployment secret store, not source control. Document variables in `backend/.env.example` without values. Set narrow CORS origins, request size/time limits, safe error mapping, privacy-aware logs, and health checks. Never log prompts containing personal data or provider request headers.

## Delivery order and acceptance

1. Scaffold FastAPI, settings, health check, OpenAPI, and database migrations.
2. Import existing validated records and provide profile options plus exact course/timetable/calendar lookups.
3. Implement anonymous session/profile and conversation APIs with per-session isolation.
4. Implement hybrid retrieval, source citations, and the structured response envelope.
5. Add Responses API/tool calling behind configuration; keep deterministic endpoints operational without the model key.
6. Run API, migration, privacy, retrieval, and multi-turn tests. Exercise the examples from the master prompt: ECE-3 timetable, ECC-201 follow-ups, MTE/ETE, September 23 calendar entry, missing exam details, sources, and unavailable model behavior.
7. Publish OpenAPI and a local start guide for the frontend. Deployment/admin services are later phases; do not claim them complete until actually implemented and verified.

Completion means the frontend can use the v1 contract with real source-backed records, sessions remain isolated, key academic answers are deterministic/cited, and missing or draft data is transparent. It does not mean every source category has complete coverage or the production deployment is live.
