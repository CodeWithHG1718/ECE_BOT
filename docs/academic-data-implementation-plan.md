# Academic data implementation plan

Prepared 30 September 2026 for the ECE WhatsApp academic assistant.

Implementation direction, 18 October 2026: the user has replaced the website/WhatsApp interface with a Telegram chatbot and selected local `BAAI/bge-m3` embeddings. Complete and evaluate local retrieval/chatbot logic first; Telegram credentials, establishment and deployment are deferred. See `bge-m3-embeddings.md` and `telegram-implementation.md`. The original larger PostgreSQL/Qdrant architecture below is a future-scale plan, not a prerequisite for the single-laptop project demonstration.

Implementation update, 11 October 2026: the user selected the supplied curriculum as the project's primary catalogue and authorized reusing syllabus content by title/topic when course codes differ. The extracted dataset and reproducible pipeline are documented in `datafiles/academic/README.md`. Content associations retain both codes and coverage notes; they do not replace curriculum credits/semesters or claim an institute-issued equivalence. This update supersedes any implication below that a code difference alone must prevent using relevant syllabus content for project study guidance.

Dataset-stage status: 122 curriculum rows, 39 syllabus blocks, 38 directory-linked faculty profiles, 194 bibliography recommendations, 100 chapter references from eight publisher contents pages, and 693 lecture links from twelve NPTEL courses are extracted. The pipeline produces 2,094 embedding-ready chunks and a per-course resource coverage report. All 33 extraction/retrieval checks pass, and a full offline rebuild is reproducible. The local keyword lookup supports resource-guidance demonstrations; actual vectors, chatbot integration and deployment remain application work. No paid API calls have been made.

Build a versioned academic catalogue in PostgreSQL, preserve original sources on disk or in object storage, and index approved explanatory content in Qdrant. PostgreSQL owns identities, relationships, facts, verification status, and publication state. Qdrant is a rebuildable search index, not the authoritative record.

This document is an implementation plan. It does not import production data, certify the existing OCR output, or assume that the supplied syllabus applies to current students.

**1. Findings from the current files**

| Input | Observed contents | Consequence |
|---|---|---|
| `datafiles/master_timetable_by_year.json` | 221 rows: year I 46, II 46, III 59, IV 70; labelled Autumn 2026-27 | Treat these as recurring timetable entries, not 221 distinct courses or dated class occurrences. |
| Same timetable | 36 distinct course-code strings, including `OEC`; 26 rows without faculty, 52 without room, 134 without sections | Missing values need an explicit unknown status. Missing sections do not mean a class applies to everyone. |
| Same timetable | Multi-faculty strings with inconsistent order/spacing; an example name contains `26€C1` | Resolve people and group assignments through a review step before publishing. |
| `data/btech_ec_str_24.pdf` | 12 text-readable pages; semester structure, credits, contact hours, elective slots and assessment information | Extract tables with their semester, programme and document context. Filename year alone does not establish cohort applicability. |
| `data/btech_ec_syll_22.pdf` | 79 text-readable pages; older `ECN`, `CSN`, `MAN` and other codes; course descriptions, prerequisites, contents and books | Ingest as a separate source/version. Obtain evidence before linking it to current courses. |
| `data/I-Year_B.Tech._Electronics__Communication_Engineering_3.pdf` | Four pages without an extractable text layer | Keep the PDF and page/cell coordinates as evidence for OCR review. |

The code mismatch is substantive: structure PDF page 5 lists `ECC-203` as Electromagnetics and Radiating Systems, while the syllabus index lists `ECN-203` as Signals and Systems. The structure places Signals and Systems under `ECC-106`. Do not replace prefixes or equate courses by numeric suffix or title alone.

A preliminary exact-code comparison found no timetable codes in the syllabus's extracted code inventory. Nineteen timetable strings were absent from the structure inventory, including `TMI-103`, several `ECC-5xx` and HSS entries, and the `OEC` placeholder. This is a reconciliation queue, not proof that those entries are incorrect: electives, missing catalogues, revisions and OCR errors can all explain differences.

The official department Courses Offered page currently links documents with the same two structure/syllabus filenames. A currently linked document is not sufficient evidence that its content applies to every current cohort. Obtain the applicable curriculum notification, current course catalogue, or a documented department clarification.

**2. Storage boundaries**

| Store | What belongs here | Why |
|---|---|---|
| Original files / object storage | PDFs, HTML snapshots, page images, extracted text, checksums | Preserve evidence and allow re-extraction without crawling again. Start with local files; migrate to object storage when deployed. |
| PostgreSQL | Course/curriculum versions, syllabus sections, faculty, research areas, teaching assignments, timetable, student selections, evidence and review state | Exact lookups, joins, validation, history and corrections. |
| Qdrant | Embeddings plus identifiers/filter metadata for approved syllabus sections, academic resources and faculty research descriptions | Semantic retrieval for explanations and topic-to-course/faculty discovery. |
| JSON/CSV | Extraction interchange, review exports and ingestion reports | Useful pipeline artifacts; avoid maintaining independent editable masters alongside PostgreSQL. |

Keep Neo4j out of the first implementation. The relationships below can be represented with PostgreSQL join tables. Reconsider a graph database only after real query requirements demonstrate a need.

**3. Proposed relational model**

Use UUID primary keys, foreign keys and explicit uniqueness constraints. Every institute-owned record must carry or inherit an institute identifier; enforce same-institute joins with composite constraints where appropriate. Scope all queries by institute. Use JSONB for raw extraction payloads and flexible source expressions, not for relationships that need joins.

| Area | Tables and important fields |
|---|---|
| Institute context | `institutes(id, name, timezone)`, `departments(id, institute_id, code, name)`, `programs(id, institute_id, department_id, code, name)` |
| Academic time | `academic_terms(id, institute_id, academic_year, name, start_date, end_date)`, `cohorts(id, program_id, entry_year, curriculum_version_id)` |
| Sources | `source_documents(id, institute_id, canonical_url, document_type, authority_tier)`, `source_versions(id, document_id, checksum, file_path, published_at, retrieved_at, valid_from, valid_to, supersedes_id)` |
| Evidence | `evidence_spans(id, source_version_id, page_number, printed_page_label, section_path, bounding_box, quoted_text)`; HTML uses section/anchor locators. `record_evidence(entity_type, entity_id, field_name, evidence_span_id)` supports field-level citations; validate polymorphic targets or use explicit per-domain join tables. |
| Catalogue | `courses(id, institute_id, owning_department_id, identity_status)`, `course_versions(id, course_id, code, title, version_label, valid_from, valid_to, status)` |
| Curriculum | `curriculum_versions(id, program_id, label, applicability_text, status)`, `curriculum_entries(id, curriculum_version_id, semester_number, entry_type, course_version_id, elective_group_id, category, credits_min, credits_max, contact_hours_raw, assessment_raw)` |
| Elective rules | `elective_groups(id, curriculum_version_id, label, rule_expression)`, `elective_options(group_id, course_version_id)`; model slots and alternatives separately from actual courses. Preserve non-credit requirements as curriculum requirement entries. |
| Cross-version mapping | `course_relations(from_course_version_id, to_course_version_id, relation_type, review_status)` with evidence; relation types include equivalent, replaces, overlaps, prerequisite and corequisite. An overlap is not equivalence. |
| Syllabus | `syllabus_versions(id, course_version_id, source_version_id, applicability_status, objectives, prerequisite_status, prerequisites_raw)`, `syllabus_sections(id, syllabus_version_id, ordinal, title, body, contact_hours, evidence_span_id)` |
| Books and prerequisites | `course_resources(id, syllabus_version_id, resource_type, title, authors, edition, year, source_text)`; `prerequisite_rules(id, syllabus_version_id, rule_expression, rule_kind, review_status)`. Expressions preserve AND/OR alternatives and unresolved codes. |
| Faculty identity | `faculty(id, institute_id, official_profile_url, official_identifier, display_name)`, `faculty_aliases(faculty_id, alias, review_status)`, `faculty_appointments(id, faculty_id, department_id, designation, valid_from, valid_to)` |
| Faculty expertise | `research_areas(id, name, parent_id)`, `faculty_research_areas(faculty_id, research_area_id, original_wording, evidence_span_id, verified_at, status)` |
| Delivery | `course_offerings(id, course_version_id, academic_term_id, offering_label)`, `teaching_assignments(id, offering_id, faculty_id, role, session_type, valid_from, valid_to)` |
| Student groups | `student_groups(id, institute_id, cohort_id, term_id, group_type, label)`, `group_memberships(student_id, group_id, valid_from, valid_to)`, `offering_groups(offering_id, group_id)` |
| Schedule and places | `buildings`, `rooms`, `class_meetings(id, offering_id, weekday, start_time, end_time, room_id, valid_from, valid_to)`, `meeting_groups(meeting_id, group_id)`, `meeting_teachers(meeting_id, teaching_assignment_id)`, `schedule_exceptions(meeting_id, date, action, replacement_details)` |
| Personalization | `students(id, institute_id, whatsapp_identifier, program_id, cohort_id)`, `enrollments(student_id, offering_id, status)`, `student_preferences(student_id, preference_key, value, explicitly_provided_at)` |
| Pipeline control | `ingestion_runs`, `staged_records`, `review_issues`, `review_decisions`, `document_chunks`, `index_outbox`; retain parser/model versions, errors, timestamps, and source references. |

These are logical entities; implement them in the sequence below instead of building every future feature at once.

Important modelling rules:

- A course is a catalogue identity; a course version is a specific definition; an offering is that version taught in one academic term. Faculty belong to teaching assignments, not a permanent `faculty_name` column on the course.
- Create separate provisional identities for incompatible or unresolved codes. Merge identities only after review. A search alias must not silently establish academic equivalence.
- A course may serve several programmes and be taught by faculty outside ECE. Store the owning department and the consuming programme separately.
- Multiple instructors, sections and lab batches require join rows. Do not store comma-separated lists as canonical values.
- Credits and assessment schemes can depend on curriculum/version. Preserve source assertions separately when structure and syllabus disagree; publish a reconciled value only for its verified context.
- Preserve expressions such as `2/2`, `3/4`, percentage ranges and alternative project pathways. Do not convert them into single numbers without documented interpretation.
- Differentiate prerequisites explicitly stated as NIL, prerequisites not stated, and prerequisites not yet verified. Suggested preparation is a separate recommendation, not an official prerequisite.
- Store verification status, evidence, effective dates and review timestamps for published facts. Official origin and accurate extraction are separate checks.
- Enforce nonnegative credits/hours, end-after-start times, valid enum values, and appropriate compound uniqueness. Use foreign keys for relational consistency. Cross-row timetable overlap checks need dedicated validation; a row-level CHECK is insufficient.
- Do not make an entire faculty or room globally unavailable after detecting one conflict. Flag specific overlapping sessions for review, allowing verified shared sessions and co-teaching.

**4. Ingestion and publication workflow**

```text
Original PDF / official webpage
    -> immutable source version + checksum
    -> page text / table extraction / OCR where necessary
    -> typed staging records with evidence spans
    -> validation + identity resolution + conflict review
    -> approved PostgreSQL records
    -> transactional indexing outbox
    -> approved chunks in Qdrant
```

Use the states `extracted -> validated -> needs_review/approved -> published -> superseded`. A validator passing is not itself human verification of ambiguous facts. Preserve rejected candidates and their reasons for audit and parser improvement.

Each staging record should include `source_version_id`, locator, raw text, parsed fields, parser version, extraction method, warnings, candidate entity matches, and review status. An LLM may propose structured fields; it must not supply missing values from memory. Preserve nulls and require supporting source spans.

For each fetch, record retrieval time separately from publication/effective time. Deduplicate unchanged content by checksum. Re-importing the same source/parser combination should not create duplicate academic facts. Retain prior versions and use explicit supersession rather than destructive replacement.

Keep source trust configurable by claim type. An official timetable supports who teaches a particular term; an official faculty profile supports stated research interests; an approved curriculum supports programme requirements. A new retrieval timestamp does not automatically outrank an older, explicitly applicable source.

**5. Implementation sequence and deliverables**

| Step | Work | Completion evidence |
|---|---|---|
| 1. Register and audit inputs | Create source manifest, checksums, extraction runs and staging schema. Import the existing timetable JSON into staging without overwriting it. Attach the four-page PDF as its candidate source and verify the relationship. | Reproducible 221-row import; report missing fields, suspicious names, duplicate candidates and unmatched codes. |
| 2. Extract course structure | Parse programme/year/semester boundaries, course rows, electives, credits, contact hours and footnotes from the 12-page structure PDF. Resolve table continuation and merged cells. | Reviewed semester catalogue; every row linked to a source span; totals reconciled under the stated alternatives or explicitly flagged. |
| 3. Resolve curriculum applicability | Obtain effective cohort information and catalogue coverage for current timetable codes. Review the 19 initially unmatched strings against source pages and additional official documents. | Every timetable code mapped to a verified course version, elective placeholder or unresolved issue. No silent prefix substitutions. |
| 4. Extract syllabus | Parse the 79-page document by course block, then objectives, prerequisites, ordered content sections, hours and resources. Join continuations across pages. Seek the applicable newer syllabus. | Legacy content retained with its own identities; current syllabus links verified or explicitly unavailable. A coverage report distinguishes full course blocks from index-only mentions. |
| 5. Build faculty catalogue | Start with the official ECE faculty directory; visit linked profiles and research-group pages. Extract names, appointments, official contact/profile links and stated research interests. Resolve timetable people, including external departments. | Every active timetable name resolved or quarantined; each published expertise tag has a source. Historical teaching records remain distinct from current assignments. |
| 6. Publish timetable relationships | Create term offerings, teachers, groups and recurring meetings. Resolve rooms and term validity; add holiday/change exceptions when sourced. | Queries return verified teachers/classes for a known student group and term; missing scope/rooms remain visible as unknown. |
| 7. Add retrieval and read APIs | Create approved chunks, Qdrant metadata filters, exact database services and mixed-question orchestration. | A syllabus explanation cites the applicable version; a current-faculty answer comes from assignments; a mixed answer uses both routes without changing exact facts. |
| 8. Evaluate and maintain | Build a small reviewed question set, version-update tests, review reports, backup/restore and reindex procedures. | Gates in section 9 pass; source refresh and correction ownership are documented. |

The immediately useful deliverables are `course_structure.json`, `syllabus_courses.json`, `faculty_profiles.json`, `course_mapping_review.csv`, and an ingestion report. These should be generated interchange artifacts with evidence and status fields. PostgreSQL becomes the maintained source of truth after review.

Use a simple CLI plus CSV/JSON review initially. Build a Next.js review dashboard only if the review workload justifies it. The highest priority is obtaining and verifying applicable syllabus content, not building an admin interface.

Suggested implementation layout:

```text
data/                         existing original PDFs; preserve
datafiles/                    existing timetable extraction; preserve
docs/                         this plan and review guidance
ingestion/
  sources.py                  manifests, fetches, snapshots, checksums
  course_structure.py         curriculum table extraction
  syllabus.py                 course blocks and content sections
  faculty.py                  official directory/profile extraction
  timetable.py                import existing JSON and resolve relationships
  validation.py               schema, totals, matches, conflicts
  publish.py                  approved data and indexing outbox
schemas/                      typed extraction contracts
migrations/                   PostgreSQL migrations
reports/                      coverage, conflicts and review exports
app/services/                 exact academic lookup services
app/retrieval/                chunking, indexing, search and citations
tests/fixtures/               representative reviewed source extracts
```

**6. Faculty specialization and course relationships**

Keep three independent statements:

1. **Teaches:** a verified faculty member is assigned to an offering in a particular term, potentially only for certain groups or session types.
2. **Researches:** an official profile or group page explicitly names a research area; store the original wording and a normalized topic.
3. **May be relevant to a project:** a generated recommendation based on the student's stated topic and sourced research evidence. Label it as a suggestion; do not imply supervision availability.

Never infer specialization just because someone teaches a subject. Never infer that someone teaches this term from an undated teaching list. Publications may supply additional evidence of research activity, but keep that distinct from an explicitly declared specialization.

Resolve names using official profile identifiers/URLs and reviewed aliases. Fuzzy similarity proposes candidates only. Preserve diacritics and initials; quarantine OCR contamination. Co-teachers with reversed order are the same assignment set after identity resolution.

Use the official directory as the discovery source, then profiles for details. Cover non-ECE faculty teaching ECE programme courses through their own official department profiles. Fetch only public academic information needed by the assistant; no personal-data enrichment is necessary.

**7. Retrieval and chatbot query design**

Store canonical chunk text in PostgreSQL (`document_chunks`) and vectors in Qdrant. Chunk by a syllabus content section, experiment, or faculty research section; carry the course title/code and heading for context. Start around 300-600 tokens for long prose, then tune against retrieval results. Preserve short tables and complete prerequisite rules rather than splitting them arbitrarily.

Qdrant payload fields should include `chunk_id`, `institute_id`, `course_version_id`, `syllabus_version_id`, `faculty_id` where relevant, `document_type`, `source_version_id`, `authority_tier`, `publication_status`, `applicability_status`, and `index_revision`. Keep page/section evidence available through the canonical chunk. Index fields used frequently in filters.

Apply institute, publication and applicable version filters before ranking. If the curriculum/version is ambiguous, resolve it through student context or ask a short clarification. Do not retrieve legacy material as the current official syllabus merely because it is semantically similar. Offer historical material explicitly labelled when useful.

Use exact code/alias lookup before semantic search. For conceptual content, combine lexical matching and embedding similarity, then rerank a small candidate set. Choose the embedding model using a small ECE evaluation set; preserve its model identifier, dimensions and chunking version. A model change requires a controlled rebuild, not mixed incompatible vectors.

| Student question | Execution |
|---|---|
| What is my next class? | PostgreSQL: verified enrollment/group, term dates, institute timezone, meetings and exceptions. |
| Who teaches ECC-203 this term? | PostgreSQL: resolved course version -> offering -> group/session-specific teaching assignments. |
| What are the credits and prerequisites? | PostgreSQL: applicable curriculum and syllabus rules; distinguish unknown from none. |
| What does this professor specialize in? | PostgreSQL: sourced research tags; optionally summarize approved profile text with citations. |
| Explain a topic in my syllabus. | Resolve course/version in PostgreSQL, retrieve relevant approved content, generate a cited explanation. |
| Where is my next lab, and what should I prepare? | Schedule/location lookup followed by retrieval for that course/lab. Return separate evidence for place and preparation. |
| Who could guide a project on a topic? | Retrieve relevant research evidence, resolve verified faculty identities, explain topic matches without claiming availability. |

The router must support mixed intents and missing context. Use parameterized service queries with validated arguments; do not execute arbitrary model-generated SQL. Exact factual templates can be rendered without an LLM. Retrieved documents are evidence, not instructions for the assistant.

A syllabus lists what is taught; it usually does not contain enough material to explain every concept. Basic grounded Q&A needs an additional approved corpus of lecture notes, lab manuals or other appropriately usable learning resources. Keep generic conceptual references separate from institute-specific facts and cite them accordingly.

When PostgreSQL publication changes, write an outbox event in the same transaction. A retryable worker upserts/removes Qdrant points using stable chunk IDs. Before answer generation, recheck retrieved IDs against active approved PostgreSQL records so indexing lag cannot expose superseded content. Make the index rebuildable from canonical records.

**8. Personalization, maintenance and extension**

Registration should collect institute, programme, cohort, section, applicable lab groups and elective choices explicitly. Do not infer elective enrollment from year alone. Keep identity/contact information separate from the public academic retrieval corpus; do not embed phone numbers or chat histories by default. Provide correction/deletion controls and restrict administrative writes.

For a multi-institute future, use institute-scoped constraints and access checks from the start. A shared Qdrant collection requires mandatory institute filters; this must be enforced by the retrieval service, not chosen by the LLM.

Recommended refresh policy: check curriculum/syllabus on official revisions and before each term, faculty profiles periodically (initially monthly), and timetables at term start plus a frequent change check while teaching is active. Configure cadence to the source and permit manual correction. Show the effective term/date and last verified time where relevant.

Future lab mapping can add `labs`, `experiments`, `concepts`, `skills` and their join tables. Future comparison attributes should record whether a value is official, staff-rated or model-estimated, along with its rubric, evidence and version. Do not publish unsupported workload/difficulty ratings as official facts.

**9. Acceptance gates**

- Re-importing an unchanged file creates no duplicate courses, meetings or assignments.
- Every published deterministic fact has evidence and verified applicability; unresolved fields produce an explicit unavailable/clarification response.
- `ECC-203` never resolves to `ECN-203` solely because their numbers match. A legacy syllabus never silently supplies the current prerequisite list.
- A verified course version can appear in multiple curricula and offerings without duplicating its identity. Two curricula can retain different requirements.
- Elective placeholders are distinguishable from actual chosen courses. Missing sections do not generate a personalized schedule.
- Multi-teacher entries resolve correctly, and names contaminated by section codes remain in review.
- Course/semester credit totals and source assessment rules reconcile, or discrepancies are visible and block the affected claim.
- Next-class tests cover term boundaries, weekends, timezone, cancellations, replacements and individual lab groups. Unknown calendar coverage is disclosed.
- Research-interest answers cite actual evidence and never treat a teaching assignment as proof of specialization.
- Retrieval tests cover wrong version, wrong institute, withdrawn source, no relevant evidence, exact course-code queries and mixed intents.
- On a small manually reviewed evaluation set, deterministic answers match approved data exactly; unsupported-answer cases abstain; retrieved citations actually support the answer. Record retrieval misses separately from generation errors.
- A corrected source can be published, old vectors invalidated, and previous data inspected without losing history. Backups can restore canonical data and rebuild the index.

**10. Sources for implementation**

The local inventory and counts above were inspected directly; this is a targeted assessment, not a complete audit of every PDF row. Official pages checked during planning:

- [IIT Roorkee ECE Courses Offered](https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/Academics/Courses%20Offered.html) provides the structure and syllabus discovery links.
- [Official structure PDF](https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/static/Courses%20Offered/B.Tech/btech_ec_str_24.pdf) and [official syllabus PDF](https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/static/Courses%20Offered/B.Tech/btech_ec_syll_22.pdf) expose the code/version discrepancy described above.
- [ECE faculty directory](https://www.iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/People/Faculty/FACULTY%20MEMBERS.html) and [research groups](https://www.iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/Research/Research%20Groups.html) are discovery sources for the faculty ingestion step; a complete faculty extraction has not been performed.
- [PostgreSQL constraints](https://www.postgresql.org/docs/current/ddl-constraints.html) documents primary/foreign keys, uniqueness and the limits of row-level checks.
- [Qdrant filtering](https://qdrant.tech/documentation/search/filtering/) documents metadata filtering and payload indexes supporting the proposed retrieval isolation.
