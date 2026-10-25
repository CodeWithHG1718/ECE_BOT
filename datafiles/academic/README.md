# ECE academic retrieval dataset

Original academic-source collection extracted 11 October 2026; the workbook, timetable and course-instructor additions were integrated 25 October 2026. The local dataset is source-backed and uses BGE-M3; no paid APIs have been called and no vectors have been uploaded.

The supplied curriculum is the primary course catalogue, as requested. Older syllabus content is attached using course titles and topics even when codes differ. Original source codes remain available for citations. For example, `ECC-106` uses the Signals and Systems content labelled `ECN-203`; `ECC-203` uses Engineering Electromagnetics and Antenna Theory. These content associations do not overwrite curriculum credits, semesters or assessment rules.

## Files to use

| File | Contents |
|---|---|
| `course_catalogue.json` | Primary application entry point: 120 course-code identities, with PDF curriculum occurrences, workbook records, syllabus IDs and any user-supplied instructor notes. |
| `course_structure.json` | All 122 curriculum rows, eight semester totals, requirements, elective lists, credits, contact hours and raw assessment cells. |
| `syllabus_courses.json` | 39 full course blocks: objectives, prerequisites as stated in the source, ordered topics/lab content, reading lists and page evidence. |
| `course_content_mappings.json` | 29 curriculum codes connected to syllabus content, with the reason and coverage type. |
| `course_mapping_review.csv` | One row per curriculum identity, including unavailable and partial content matches. |
| `faculty_profiles.json` | All 38 faculty cards linked by the official directory; profile sections, expertise, public official contact fields, education, research, publications, teaching history and 174 profile project entries where listed. |
| `workbook_course_records.json` | 127 supplied workbook rows from six course-bearing sheets, with source sheet/cell evidence; applicability is unverified. |
| `timetable_records.json` | 221 normalized recurring OCR entries with source page evidence and separate student-section/course-batch fields. |
| `course_faculty_records.json` | Team-supplied professor note for ECT-108, linked to Saurabh Khanna's public faculty profile and labelled unverified for the current offering. |
| `../course_faculty_assignments.json` | Editable source for the team-supplied course/professor note. |
| `department_projects.json` | 229 departmental project entries, retaining named faculty, title, sponsor, co-PI and year as printed. These overlap with profile projects and must not be counted as 403 distinct projects. |
| `department_research.json` | Research-group/lab descriptions, associated tables and other public research pages. |
| `book_references.json` | 194 syllabus book recommendations, retaining source edition/year wording and course relationships. Repeated recommendations are not claimed to be distinct books. |
| `book_contents.json` | 100 chapter references from eight publisher contents pages, with edition, subtopics where available, and exact source locators. One ambiguous chapter is excluded from embeddings. |
| `nptel_references.json` | Twelve official course outlines with 693 lecture titles, units, instructors and video links. |
| `resource_coverage.json` | Book and lecture coverage for each course identity; missing resources remain explicit. |
| `topic_resource_map.json` | Generated after BGE indexing: all 120 course identities, all 232 source syllabus topics, 180 mapped curriculum/topic pairs, and the 52 syllabus topics not mapped to a primary curriculum course. Each mapped topic has up to three chapter and lecture candidates, with course-level syllabus book recommendations, source evidence, and explicit missing-syllabus/no-match statuses. Automated candidate ranking is not an academic review. |
| `embedding_chunks.jsonl` | 2,443 records with `chunk_id`, `text`, source evidence and metadata. |
| `embedding_texts.jsonl` | Matching `{id, input}` records if the embedding client only needs the text. Join results back by ID. This is not an OpenAI Batch API request file. |
| `validation_report.json` | Extraction coverage and citation checks, plus limitations. Passing checks do not certify academic equivalence. |
| `study_lookup_examples.json` | Offline retrieval examples for convolution, Boolean algebra, combinational logic and waveguides. |
| `*.pdf.pages.json` | Full page text and table grids, including bounding boxes, for extraction review. |
| `sources/`, `*_source_manifest.json` | Checksummed official snapshots, retrieval times and original local-source identities. |

## Embedding use

1. Read `embedding_chunks.jsonl` line by line.
2. The project uses local `BAAI/bge-m3` embeddings. No paid embedding API is required. Do not send the entire metadata object as embedding text.
3. The current SQLite vector index is `vectors/bge-m3.sqlite3`; run `python ingestion/run_pipeline.py` after changing source records or chunks. This command regenerates normalized records and chunks, embeds the current corpus, builds `topic_resource_map.json`, and checks that each source entity is present in the index.
4. Retrieve with `institute_id=iit-roorkee` and the relevant `document_type` and `curriculum_codes`. NPTEL records separately identify the resource's teaching institute.
5. Cite the PDF page or official webpage from `metadata.evidence`. NPTEL lecture records also include direct lecture URLs.

All records are staging data. The demo can use them with their source and coverage labels; production publication needs the review workflow described in the implementation plan. Use structured curriculum fields for exact semester/credit answers. Use mapped syllabus topics and resource records for study guidance. Do not describe historical profile teaching entries as current-term assignments, or a project match as confirmed supervision availability.

The chunker limits body segments to about 1,800 characters and carries course/faculty context in every part. It does not claim a measured token count. Contact fields are retained in the structured faculty catalogue but omitted from the text chosen for expertise embeddings. Large publication sections are split into bounded chunks.

## Reproduce

From the project root, with Python and `ingestion/requirements.txt` installed:

```powershell
python ingestion/build_catalogue.py --reextract
python ingestion/validate_catalogue.py
python ingestion/lookup_resources.py "combinational logic" --course ECC-104
```

All three commands work offline after the saved sources exist. To rebuild only mappings/chunks, run `python ingestion/build_catalogue.py`.

`python ingestion/build_catalogue.py --reextract-resources` re-parses the saved publisher and NPTEL HTML snapshots before rebuilding. `--reextract` refreshes the curriculum PDFs and faculty records as well, then re-parses publisher/NPTEL snapshots and rebuilds. These flags use only saved snapshots; fetch or refresh a source separately with the documented fetch tools if its saved copy needs updating. Re-run the BGE-M3 index build after changing embedding chunks.

Validation on 11 October 2026 passed all 33 checks. A second full offline rebuild produced identical bytes across 24 generated JSON/JSONL/CSV files.

The local chatbot combines BGE-M3 dense embeddings with BM25 and reciprocal-rank fusion for resource, course and timetable retrieval. Timetable replies use exact filters over the normalized records instead of generated schedule facts. A missing lecture match stays empty; for example, the collected digital-circuits lecture titles do not contain the exact words “Boolean algebra”, although the book contents do. Try “combinational logic” to test both resource types. When a course syllabus lists a book but its chapter contents were not collected, the chatbot can still cite that book as a syllabus recommendation and clearly labels that it has no chapter-level contents.

`ingestion/fetch_sources.py <official-url>` saves a public source; `--refresh` fetches it again. `ingestion/crawl_faculty.py` discovers the directory's profile links and linked research pages. Downloads do not require an LLM API key. Keep original PDFs and saved snapshots: they are the evidence needed to reproduce citations.

Edit mappings in `ingestion/course_content_mappings.json`, not the generated copy. The five image-only appendix pages were visually transcribed into `ingestion/scanned_syllabus_transcription.json`. Syllabus pages 73-74 duplicate the Embedded System Design block on pages 68-69; they are accounted for without duplicating the course. A damaged SM Charts paragraph was recovered from page 73.

## Coverage and remaining work

- All 12 curriculum pages and all 79 syllabus pages are accounted for. The local PDFs match the files currently linked by the official department Courses Offered page byte for byte.
- The faculty directory contains 38 linked cards although the homepage advertises 40/41 faculty. This dataset covers the directory, without inventing the missing people. Individual profiles can omit projects or be out of date.
- The curriculum contains elective slots, project pathways and course options with no detailed syllabus in the supplied PDF. These remain in the primary catalogue with an explicit content status. A missing match is not filled by course-number similarity.
- The four-page scanned timetable and the pre-existing timetable JSON/CSV remain unchanged. They are not used to infer research expertise or current teaching from profile history.
- Book contents cover eight selected books, not all 194 bibliography entries. All bibliography references are embedded, but chapter matching is available only for collected contents pages. They support finding chapters, not answering from full textbook text. Alternate editions retain their own numbering: the collected Mano contents are sixth edition while the syllabus recommends fourth edition. Balanis's saved contents page lists chapters 2–16 only; absent chapters are not invented. A duplicated Razavi chapter-17 label is retained for review and excluded from embeddings.
- The twelve NPTEL outlines cover signals, devices, digital circuits, DSP, VLSI, control, communication, electrical circuits, antennas, electromagnetics and microwave topics. Remaining course-resource gaps are listed in `resource_coverage.json` and the topic-level `topic_resource_map.json`. Videos and transcripts are not ingested.
- Faculty extraction retains all 510 headings and their content plus public profile-header details and links. Linked personal sites and CV contents have not been recursively collected. Profile contact details are excluded from expertise embedding text.
- Next application work is creating vectors, connecting retrieval to a chatbot and adding the presentation interface. No paid API calls or deployment are included in this dataset stage.

Source discovery: [ECE department](https://ece.iitr.ac.in/), [faculty directory](https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/People/Faculty/FACULTY%20MEMBERS.html), [courses offered](https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/Academics/Courses%20Offered.html). Exact retrieved URLs and checksums are in the manifests.
