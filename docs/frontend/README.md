# Signal 2.0 Frontend Task

This brief defines the frontend work for Signal 2.0. The frontend and backend can be developed in parallel against the API contract below and in [`../backend/README.md`](../backend/README.md).

## Product goal

Build a responsive academic assistant website where an IIT Roorkee ECE student selects a study year and a source-supported section, then asks free-form questions about courses, timetables, exams, syllabus topics, resources, faculty, and projects. The website is a new Signal 2.0 surface; the existing Python local/Telegram bot remains a working reference and must not be broken.

The repository’s old `frontend/` folder is a discarded prototype and is ignored by Git. Create the new app under **`apps/web/`**. Do not build on or unignore the old prototype.

## Ownership and parallel-work boundary

Frontend ownership is `apps/web/**` and this README. The backend owns `backend/**`, its database, API implementation, and the API contract in [`../backend/README.md`](../backend/README.md). The frontend consumes that contract; it does not edit backend code, academic source files, ingestion scripts, the existing bot, or the root environment template without coordinating first.

The backend README is the contract source of truth. Keep the frontend types and API client aligned with its versioned `/api/v1` routes and structured response envelope. If the backend proposes a breaking change, agree on the contract change before either side implements it. UI work can use clearly marked local fixtures until the API is available; fixtures must never be presented as collected IIT Roorkee records.

## Proposed stack and setup

- Next.js with TypeScript.
- Tailwind CSS and shadcn/ui, with a small, consistent design system.
- Accessible forms, keyboard navigation, visible focus, and responsive layouts.
- One typed API client under `apps/web/lib/`; keep the backend base URL configurable.

Suggested public configuration: `NEXT_PUBLIC_SIGNAL_API_BASE_URL`. This value may contain a service URL only. **Never put OpenAI, Azure, Telegram, or database credentials in browser-visible variables.** The frontend must not call OpenAI directly.

The current repository has no Signal 2.0 frontend scaffold yet. Add a clear local run command in `apps/web/README.md` or here once the scaffold exists; do not document commands that have not been implemented.

## Screens and behavior

### 1. Landing and onboarding

- Landing page presents Signal as an AI study assistant designed for IIT Roorkee ECE. Do not claim it is an official institute service.
- “Launch Signal” begins onboarding.
- Fetch year and section choices from `GET /api/v1/profile-options`; never hardcode section names such as `ECE-1` through `ECE-10`.
- Collect study year and section first. Keep cohort and semester optional until the API has reviewed values for them.
- Submit the profile through `PUT /api/v1/sessions/{session_id}/profile`. If the selected section cannot be matched to a source-supported profile, show a concise clarification instead of silently selecting another section.
- Provide “Change academic profile” from the chat screen.

### 2. Chat workspace

- Branded, responsive chat layout with a conversation list, New Chat, current profile, multiline input, and useful empty state.
- Support free-form messages and follow-up context. Quick prompts (timetable, courses, syllabus, resources, exam schedule, faculty/projects) are shortcuts, not the only interaction method.
- Render the backend response envelope by `presentation` (`answer`, `course_list`, `timetable`, `exam_schedule`, `resources`, `faculty`, or `projects`). Keep factual `data`, generated `content`, `sources`, and `warnings` visually distinguishable.
- Link source citations using only URLs returned by the backend. Display draft, OCR-derived, tentative, or missing-coverage warnings where provided; do not hide them in a tooltip.
- Provide loading, empty, timeout, API unavailable, and model-not-configured states. Never replace an error with a fake assistant answer.
- Include copy, retry/regenerate, and feedback controls only when they have real behavior. Streaming may be added after the non-streaming `/api/v1` flow works.

### 3. Visual direction

Use a restrained academic technology identity: deep navy/charcoal, electric blue/cyan accents, readable typography, signal or waveform details used sparingly, and strong information hierarchy. Avoid generic stock imagery, fake dashboards, decorative gradients, excess cards, glow effects, and repeated three-column feature sections. Build coherent empty, loading, and error states, not only a polished first screen.

## Shared API contract (v1)

Use the routes and response shapes in [`../backend/README.md`](../backend/README.md). The frontend’s minimum integration path is:

1. `GET /api/v1/health`
2. `GET /api/v1/profile-options`
3. `POST /api/v1/sessions`
4. `PUT /api/v1/sessions/{session_id}/profile`
5. `POST /api/v1/sessions/{session_id}/conversations`
6. `GET /api/v1/sessions/{session_id}/conversations`
7. `GET /api/v1/conversations/{conversation_id}/messages`
8. `POST /api/v1/conversations/{conversation_id}/messages`

Store the `session_id` and opaque `session_token` returned by session creation in session-scoped browser storage. Send the token as `X-Session-Token` on every session/profile/conversation request; never put it in a URL, analytics, or client logs. A chat send returns `{ "user_message": { ... }, "assistant_message": { ... } }`; message history returns `{ "messages": [...] }`. An assistant message has `content`, `presentation`, optional structured `data`, `sources[]`, `warnings[]`, and `created_at`. Do not infer exam rooms, dates, course applicability, or source status in the frontend. The API owns those facts.

## Delivery sequence

1. Scaffold `apps/web/` and a compact design system.
2. Implement landing, onboarding, and profile switching against profile options.
3. Implement chat, conversation list, and response rendering against typed fixtures matching the backend contract.
4. Connect the real API and remove any fixture-only path from the normal run.
5. Finish responsive behavior, accessibility, loading/error/empty states, and browser checks.

## Acceptance checklist

- A student can select a valid year/section returned by the API and see the active profile.
- A student can create a conversation, send free-form text, receive the response envelope, and reopen prior conversations for the same session.
- Timetable, exam, and resource citations/warnings are rendered from API fields without frontend-generated facts.
- Unavailable data and an unconfigured model appear as honest, usable states.
- Layout works at desktop and mobile widths with keyboard access and visible focus.
- No secrets, fake academic records, or privileged database calls exist in browser code.

## Non-goals for the first frontend slice

Do not build an administrator dashboard, student login/SSO, payment flow, public deployment, live notices feed, or a second retrieval pipeline in the frontend. Those require separate data, security, or deployment decisions.
