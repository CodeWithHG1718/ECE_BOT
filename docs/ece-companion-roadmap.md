# ECE Companion: agreed product direction

The user's full brief is preserved in `ece-companion-vision.txt`. This is a Telegram department assistant with seven sections, one shared knowledge catalogue, contextual actions and natural-language shortcuts. The local chat remains the test interface until the pipeline is ready; Telegram deployment is deferred.

## Implemented in this iteration

- Seven-section main menu, persistent Telegram reply keyboard and contextual inline actions, defined by application-owned registries in `bot/navigation.py`.
- Shared conversation state for both transports: academic year, study year, selected course and recent topic.
- Complete semester-grouped course lists with codes; syllabus topic selection; direct resource queries; faculty discovery; departmental project discovery using the existing indexed records.
- DSP shortcut and course-to-related-faculty follow-up. Research matches do not imply teaching assignments or supervision openings.
- Deterministic timetable lookup for the 221 supplied recurring OCR rows, including year/day/course/section filters. Missing sections, rooms and faculty remain explicitly unknown. Notes, PYQs, notices, events, facilities and policies remain navigation destinations without connected data.
- Grounded IIT Roorkee prompt templates with separate requested academic year, source dates and course identity. No claim that a 2026 query proves a source is applicable in 2026.
- Commands: `/start`, `/menu`, `/help`, `/courses`, `/course`, `/faculty`, `/projects`, `/resources`, `/search`, `/timetable`, `/notices`, `/clear`. `/search` currently routes supported course, resource, faculty and project requests; universal ranked search across all seven sections is not complete.

## Connected: local answer model

Installed: Ollama `qwen3:4b-instruct` (4.02B, Q4_K_M, approximately 2.5 GB download; https://ollama.com/library/qwen3:4b-instruct). The project-local Ollama 0.24.0 runtime uses the RTX 4060 through CUDA; the original installed runtime was detecting only CPU.

BGE-M3 remains the retriever; authoritative codes/credits/semesters and faculty/project records use structured rendering. The local LLM supplies conversational explanations, general study advice, short plans and resource summaries, with bounded context and output, local caching and per-user follow-up context. Intent routing remains application-owned; a broad LLM intent planner is not implemented. See `local-llm-validation.json` and `local-llm-demo.md` for actual results. Local inference has no per-call hosted API fee; hardware and electricity still apply.

Before allowing generated educational answers, distinguish the available chapter contents/lecture outlines from full explanatory source text. General explanations must be labelled as general knowledge when unsupported by retrieved full content.

## Shared response structure to introduce with generation

Use `answer`, `source_links`, `last_verified`, `actions`, and `confidence_or_limitations` for a future unified response envelope. Keep collection dates separate from `last_verified`; leave verification null when unknown. Current local generation returns validated `answer` and `source_ids`; the app independently owns actions, source links and HTML rendering. The complete response-envelope migration remains ahead.

## Later data and feature work

1. Review the supplied workbook's cohort/term applicability and verify timetable OCR rows, student sections and source corrections; then add academic calendar/exam records and notes/PYQs/lab manuals with provenance and permissions.
2. Add verified lab/contact/facilities/policy records and current notices/events with refresh timestamps and expiry handling.
3. Build cross-catalogue answers and universal search; add project/faculty explanations, structured plans and supported educational exercises.
4. Implement reminders only with explicit student approval and durable scheduling. No reminders are scheduled by the current menu.
5. Evaluate representative student conversations, then connect the Telegram token and rehearse the presentation.

These remain planned capabilities. The example timetable, credits and faculty placeholders in the brief are illustrative and must never be inserted as real records.
