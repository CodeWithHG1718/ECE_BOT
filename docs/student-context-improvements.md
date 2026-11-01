# ECEBOT critical retrieval and optional-course fixes

Implemented and verified locally on 1 November 2026. This report supersedes the earlier 49-row personal-timetable behavior: None now means compulsory courses only.

## Reproduced failures and root causes

1. **Faculty retrieval:** `tell me about Vinod Pankajakshan` and `what courses does he teach` both returned no deterministic result. Faculty detection depended on words such as professor/faculty/teaches; it missed a name-only query and the singular verb teach. Pronoun handling omitted he/she and direct faculty references. The screenshot therefore showed a model answer without institutional sources. Vinod's original structured profile already contains Teaching Engagements, Educational Details, Professional Background, Publications and Projects. The index builder additionally excluded teaching, education and experience sections. Teaching lookups scoped to the student's third-year timetable could not find his second-year ECC-201 assignment.
2. **Personal timetable:** the prior resolver returned 49 section-compatible third-year rows, including all HSS alternatives, unassigned OEC placeholders and talent-enhancement alternatives. This was not a compulsory-only personal timetable. The normalized source retains all 221 original timetable rows, including all 59 third-year rows; ingestion loss was not the reproduced cause. Structured chat retrieval now queries the schedule_events database and then applies course/section/semester filters, instead of depending on top-k vector passages or model reconstruction.
3. **Optional selections:** profiles had no HSS/OEC columns, validation, options or UI. Browser credentials used sessionStorage, preventing automatic restoration in a new tab. The catalogue contained ECO-101/ECO-102 and generic HSS slots, but no complete names for the four actual HSS codes in the uploaded third-year timetable.

## Data and schema

- Add nullable `hss_course` and `oec_course` columns to the existing profiles table. The additive compatibility migration preserves old profiles, conversations and messages and is safe to run repeatedly. Existing sessions default to None.
- Store canonical course codes; derive names from the shared catalogue on reads. Profile responses include `hss_course_name` and `oec_course_name`, avoiding duplicate name storage that could drift.
- Add `datafiles/academic/optional_course_catalogue.json` with four source-backed HSS identities. Their approved titles were checked against IIT Roorkee's [26 May 2025 approval notification, page 1](https://iitr.ac.in/Academics/static/Notifications/UG%20Notifications/151.2.8_2_HSS.pdf). Only codes actually present in the uploaded timetable are offered as HSS choices. Each record retains its official URL, page, locator and title evidence. The backend merges the supplement with the existing catalogue and seeds the canonical course table through its existing loader.
- OEC identities come from the uploaded ECE_Course_Structure.xlsx Open Electives sheet, already represented in the catalogue. Generic OEC/OEC-III placeholders are never treated as uniquely scheduled courses.
- Original timetable and faculty source records remain intact. No paid embedding rebuild is required for these deterministic services.

## Backend architecture and API

- `academic_context.py`: keep full-year requests complete, but personal requests now include compulsory/explicit-section courses and selected HSS/OEC codes only. Preserve source identifiers, times, rooms, faculty and session types. Resolve HSS/OEC references from the saved profile; include selected codes in exam/course context even when their timetable is absent. Sort day/time, preserve source alternatives, and annotate overlaps without inventing slots.
- `faculty_context.py`: exact/unique partial/initial-compatible and conservative typo matching; ambiguous names require clarification rather than mixing profiles. Resolve he/she/his/her/their and professor references against conversation history and course-faculty relationships. Assemble complete structured profiles instead of a top-k chunk subset. Join teaching assignments across all timetable years and explicit course-faculty records, separately label profile teaching engagements, and combine/deduplicate own-profile and department projects. Explicit full-information requests include every nonempty source section and projects.
- `electives.py`: source-backed HSS/OEC categories and options, year/semester availability filters, selected-course context and deterministic clash annotation.
- `GET /api/v1/profile-options?study_year=3&semester=5`: existing options plus optional_courses and semesters. Course options include canonical code, full title and schedule_available. No query parameters remains supported.
- `PUT /api/v1/sessions/{id}/profile`: optional nullable HSS/OEC codes. Validate category, course existence, year/semester, incompatible duplicate selections, and semester/year consistency. Existing request bodies remain valid.
- `GET /api/v1/sessions/{id}/profile`: restore stored codes and canonical names.
- `GET /api/v1/sessions/{id}/timetable`: authenticated personalized schedule using the same service as chat. Returns records, warnings and timezone.
- Existing chat routes and message presentation enums remain compatible. Default institution remains IIT Roorkee ECE. Institutional lookups do not require model availability or an internet search.
- `build_catalogue.py`: future index builds retain all nonempty faculty sections, including teaching/education/experience. Existing structured faculty retrieval does not wait for reindexing.

## Frontend flow

Academic setup and profile editing now include an optional semester and two optional dropdowns labelled HSS Course and OEC Course. Both default to None. Options use `COURSE_CODE : Complete Course Name`, load from the API, and refresh/reset on year or semester changes. Invalid selections are also rejected server-side. Students can skip both fields.

The saved profile appears in the sidebar with selected codes and a View my timetable action. New timetable requests immediately use the latest saved selections; historical chat messages remain snapshots of their original request. Browser credentials migrate from sessionStorage to localStorage, while the academic profile stays in the existing database. New tabs and browser sessions restore the same anonymous profile until browser storage is cleared. Profile editing restores the prior choices.

Faculty responses now render titled sections and source-linked teaching/project records. Timetable columns begin with day and time, retain horizontal scrolling for all details, and mark clashes with shading and an explicit Clash column. Existing independent sidebar/main scrolling remains intact.

## Verified results

### Automated integration/regression suite

` .venv-embeddings/Scripts/python.exe -m pytest backend/tests -q `: **40 passed**. Coverage includes all original API checks plus:

- Complete third-year results and all 221 original timetable rows compared against their original source fields.
- Personal timetable variants with None selections, exact source-row equality, dates/weekdays and empty days.
- All four optional-course combinations, persisted codes/names, changes and removals, dedicated authenticated timetable endpoint, HSS class/faculty follow-up, unavailable OEC warnings, invalid categories/codes/duplicates and semester refresh.
- Six actual Vinod faculty queries, source-exact requested sections, profile teaching engagements plus ECC-201 timetable linkage, all nonempty sections for complete details, three deduplicated projects across profile/department records, and ambiguous partial-name handling.
- Clash detection, adjacent non-clashing sessions, duplicate-row removal and additive profile-migration preservation/idempotence.
- Course search, typos, abbreviations, multiple courses, personalized ETE, large timetable inputs and existing learning behavior.

TypeScript `npx tsc --noEmit`: **passed**. `git diff --check`: **passed**. The Python test run reports one existing Starlette/httpx deprecation warning.

### Live browser tests

`apps/web/tests/electives-faculty.e2e.cjs`: **passed** against the running website and API, with no mocked API data. Verified defaults, optional fields, actual labels, all four selections, source-exact timetable rows and fields, real HSS clashes, missing OEC slots, faculty follow-ups, changed courses, new-tab restoration, semester refresh, six professor queries, complete sections/projects and mobile profile navigation.

`apps/web/tests/academic.e2e.cjs`: **passed** after updating its personal-timetable expectation to the new compulsory-only behavior. Verified real model learning response, existing course/exam lookups, 33-conversation sidebar scrolling, boundary scroll containment, independent main scrolling, mobile overflow and absence of browser errors.

Concrete Year 3 / 24EC1 / Autumn results:

| Query/profile | Result |
|---|---|
| 3rd year timetable | All 59 original third-year rows, including all alternatives |
| My timetable, None/None | 13 compulsory/section-assigned rows |
| HSS-302, OEC None | 18 rows: 13 compulsory + all five HSS-302 source rows |
| OEC ECO-101 only | 13 compulsory rows + explicit ECO-101 schedule-unavailable notice |
| HSS-302 + ECO-101 | 18 source rows + explicit missing OEC schedule notice |
| HSS changed to HSS-305 | 21 rows; previous HSS removed |
| ETE with None selections | Four matching core-course entries |
| Vinod teaching | ECC-201 timetable assignment plus all seven profile teaching engagements |
| Vinod complete information | All 11 nonempty profile sections and three merged projects |

Real source clashes are shown for HSS-302 versus ECC-303 on Thursday at 15:00 and ECC-351 at 16:05. These are possible clashes because source batch alternatives are preserved.

## Screenshots

- [Academic profile with optional selections](../tmp/elective-profile.png)
- [Personal timetable with highlighted overlaps](../tmp/elective-timetable.png)
- [Complete faculty information](../tmp/faculty-details.png)
- [Loaded mobile academic profile](../tmp/elective-mobile.png)

## Modified files

Backend: `backend/app/main.py`, `backend/app/db.py`, `backend/app/data.py`, `backend/app/academic_context.py`, new `backend/app/electives.py`, new `backend/app/faculty_context.py`.

Frontend: `apps/web/app/page.tsx`, `apps/web/app/globals.css`, `apps/web/lib/api.ts`, `apps/web/lib/types.ts`.

Data/indexing: new `datafiles/academic/optional_course_catalogue.json`, `ingestion/build_catalogue.py`.

Proof: `backend/tests/test_student_context.py`, `apps/web/tests/electives-faculty.e2e.cjs`, `apps/web/tests/academic.e2e.cjs`, this report. Prior configuration/API-test changes are preserved.

To run browser tests, install Playwright and Chromium or set SIGNAL_PLAYWRIGHT_PATH to an existing Playwright module directory. Start the frontend on 3000 and backend on 8000. Each test uses its own anonymous profile; test conversations remain in the local database. The general academic browser suite also makes one real configured-model call.

## Remaining source limitations

- ECO-101/ECO-102 have catalogue identities but no named timetable slots in the uploaded data. Generic OEC blocks cannot be assigned to either course safely. Selections persist and are reported as unavailable; no timing or teacher is invented. Their individual registration/department eligibility restrictions are not documented by the uploaded catalogue.
- HSS options are limited to named, approved codes matching the actual year-specific timetable. Other years/semesters with insufficient named offering data have no speculative choices. No Spring timetable is uploaded.
- Unspecified HSS/tutorial batch alternatives are preserved and identified as such; the system cannot infer a student's batch registration. Timetable data is a weekly pattern, not live cancellation information. ETE records remain draft.
- HSS teachers outside the uploaded ECE faculty directory can be identified from their teaching rows, but a detailed biography is not fabricated when no profile exists.
- Profile teaching engagements may use historical course codes; these are presented separately from the supplied timetable and are not silently aliased to modern codes.
- The current structured services work without the vector index. Existing vector completeness/provider limitations still apply to unrelated passage-search requests. The next index build will include the previously omitted faculty section types.
