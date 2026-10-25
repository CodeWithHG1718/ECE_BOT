# ECE_BOT — Signal, IIT Roorkee ECE Companion

ECE_BOT is a student-facing study assistant for the Electronics and Communication Engineering (ECE) department at IIT Roorkee. The project is being built as a Telegram chatbot, but the current development and presentation interface is local chat on a Windows computer. The goal is a dependable academic guide: show the right course, point to useful topics and resources, and explain what the sources do and do not support.

This guide is the teammate handoff for the project as it stands. It distinguishes working features from extracted data that has not yet been connected to the chatbot.

## Current status

| Area | Status |
|---|---|
| Local chatbot | Implemented in **bot/local_chat.py**; course browsing and resource search run on the project computer. |
| Embeddings and search | BAAI/bge-m3 is pinned and runs locally. Search combines dense vector similarity with BM25 keyword ranking and reciprocal-rank fusion. |
| Vector index | A resumable SQLite index is included in the repository alongside its source chunks. |
| Answer model | Qwen3 4B Instruct runs locally through Ollama for explanations, study guidance and casual help-seeking chat. It is not a paid API. |
| Academic catalogue | Structured course, syllabus, resource, faculty and department-project data is available, with citations and source metadata. |
| Telegram adapter | Implemented in **bot/main.py**, but the project has not been connected to a BotFather token or run as a live bot. |
| Timetable | 221 OCR-extracted Autumn 2026–27 entries are available through deterministic year, day, course, timetable-batch and student-section lookup. OCR/source applicability still needs academic review. |
| Website | The earlier website prototype was abandoned. It is excluded from this Telegram chatbot repository. |
| GitHub | The private **ECE_BOT** repository is connected as **origin**. This local update has not yet been committed or pushed. |

The current product is a **local demonstration**, not a production student service. Telegram deployment, continuously available hosting, student accounts, and live timetable updates are future work.

## What the chatbot can do today

- Show all collected ECE courses by study year and semester, with course codes.
- Show collected syllabus topics for a selected course.
- Search the local catalogue for study resources and return book chapter contents and NPTEL lecture links.
- Find faculty by recorded research interests and find recorded department projects.
- Answer exact curriculum-code, semester and credit questions from structured data.
- Generate optional general explanations and study guidance using the local Qwen model.
- Abstain when the local catalogue does not contain a sufficiently close resource match.
- Use the same conversation logic from local chat and the Telegram adapter.

The main menu has seven sections: Academics; Courses & Learning; Faculty & Research; Projects & Career; Department & Campus; Notices & Updates; AI Assistant. Several entries in those sections currently explain that their data or feature has not been connected. A menu item does not mean that the underlying service is complete.

## What is in the dataset

Latest recorded catalogue build:

| Dataset | Collected content |
|---|---:|
| Curriculum rows | 122 |
| Combined PDF/workbook course-code identities | 120 |
| User-supplied workbook rows / distinct codes | 127 / 111 |
| User-supplied course instructor notes | 1 (ECT-108 / Saurabh Khanna; current offering unverified) |
| Full syllabus course blocks | 39 |
| Curriculum identities associated with syllabus content | 29 |
| Faculty profiles from the linked department directory | 38 |
| Recorded department-project entries | 229 |
| Project entries recorded on faculty profile pages | 174; these overlap with department project entries |
| Syllabus book recommendations | 194 |
| Book contents | 100 chapter references from 8 selected books |
| NPTEL outlines | 12 courses and 693 lecture references |
| Embedding chunks | 2,443 |
| Timetable records | 221 rows across Years I–IV, Autumn 2026–27 |

The academic dataset was last recorded as extracted on 11 October 2026. The supplied workbook is imported with sheet/cell evidence but has no stated effective cohort or publication date; its applicability still needs academic review. The timetable rows came from a separate four-page scanned PDF and were extracted with OCR. The chatbot now renders exact matching records as **recurring weekly entries**, not dated class occurrences or verified student assignments. Some timetable rows lack a room, faculty member, or section, and OCR may misread codes or names. Missing values stay explicit; section-specific answers are withheld if the source does not record a section.

The timetable review notes 26 rows without faculty, 52 without a room, and 134 without student sections; the academic-data plan also flags 19 course-code strings for reconciliation. Missing values must remain unknown. In the timetable schema, a course-cell label such as “Batch 1” is separate from student cohort labels such as “26EC1”.

Important source limits:

- The supplied curriculum structure and the older syllabus use different course-code versions. Keep the curriculum code and source syllabus code separate. Use the curriculum for exact credits and semesters; use a syllabus association only for the supported study-topic mapping.
- The curriculum and syllabus files do not prove that their contents apply to every current student cohort. The bot reports this limitation rather than treating a file year as proof of current applicability.
- Book data consists of recommended-reading records and selected publishers’ tables of contents. It is a guide to where a student might read, not full textbook text and not a basis for claiming that the chatbot has read the book.
- Faculty research interests are not evidence of current teaching, supervision availability, or open positions.
- Department-project entries are collected records, not proof that a project is currently active or accepting students.
- The catalogue is an offline collection. General web search and automatic refresh are not connected.

Original source snapshots, checksums, extracted records and coverage notes are in **datafiles/academic/**. The course workbook is **datafiles/ECE_Course_Structure.xlsx**. The input PDFs are in **data/**. The OCR timetable export is in **datafiles/master_timetable_by_year.json** and **datafiles/master_timetable.csv**; normalized, source-backed records are in **datafiles/academic/timetable_records.json**.

## How the system fits together

    Curriculum/syllabus PDFs + supplied course workbook + timetable OCR + department/resource sources
                                    |
                                    v
    Source snapshots + checksums + extraction scripts + explicit course mappings
                                    |
                                    v
    Structured JSON catalogue and source-backed embedding chunks
                                    |
                                    v
    Pinned local BGE-M3 model creates 1,024-dimensional document/query vectors
                                    |
                                    v
    SQLite index + exact filters + dense similarity + BM25 keyword ranking
                                    |
                                    v
    Application renders exact catalogue facts, deterministic timetable results and sourced resource links
                                    |
                       optional local Qwen3 answer
                                    |
                  local chat now; Telegram later

Exact facts such as course codes, credits, semesters, menu navigation, and missing-data messages are handled by application code. The embedding model finds relevant passages; it does not decide official course facts. Qwen is used for limited conversational explanations and study advice. The application validates the generated response and attaches source links itself. There is no automatic fallback to a paid or remote model.

The current retriever uses BGE-M3 dense embeddings and BM25 keyword scores fused with reciprocal-rank fusion. It filters by institute, course and source type, then deduplicates resources. The SQLite index is small enough for this project and does not need PostgreSQL, Qdrant, or another hosted database.

## Repository layout

- **bot/** — catalogue renderer, conversation flow, study assistant, local Qwen client, local chat, Telegram adapter, and automated checks.
- **ingestion/** — source extraction, catalogue generation, BGE-M3 index build/search, evaluation scripts and package requirements.
- **data/** — primary curriculum PDFs and the scanned timetable PDF.
- **datafiles/academic/** — extracted academic catalogue, source manifests, source snapshots, embedding chunks, validation reports and SQLite vector index.
- **datafiles/ECE_Course_Structure.xlsx** — supplied workbook; imported with sheet and cell evidence, pending academic applicability review.
- **datafiles/course_faculty_assignments.json** — team-supplied course/professor note; the import and UI explicitly mark it unverified for a current offering.
- **datafiles/master_timetable_by_year.json** and **datafiles/master_timetable.csv** — OCR timetable export. The bot uses normalized records from **datafiles/academic/timetable_records.json**.
- **ingestion/import_course_workbook.py** and **ingestion/import_timetable.py** — source-aware workbook and timetable importers.
- **bot/timetable.py** — exact timetable filtering and rendering; schedule answers bypass the LLM and semantic retrieval.
- **docs/** — product roadmap, model and data design, prompts, validation reports, local setup and Telegram plan.
- **Start-Signal.ps1** — Windows launcher for the local chatbot.
- **.env.example** — placeholders for the Telegram token and optional Azure embedding configuration. A real **.env** file must stay private and is ignored by Git.

The Python environment, downloaded model weights, local Ollama runtime, logs, site prototype and temporary extraction output are not included. The SQLite index is included to make a fresh clone usable without re-embedding the whole collection.

## Run locally on Windows

Requirements: Windows PowerShell, Python 3.12, internet for first-time package/model downloads, and enough disk space for the Python environment and model files. A supported NVIDIA GPU improves speed, but BGE-M3 can use CPU with slower searches. Qwen can also run on CPU, with slower generation. The laptop used for the current demonstration has an RTX 4060 Laptop GPU with 8 GB VRAM.

Once the private GitHub repository is available, clone it and open PowerShell in the new folder. Replace the owner placeholder with the team’s GitHub account or organization:

    git clone https://github.com/<team-owner>/ECE_BOT.git
    cd ECE_BOT

### 1. Create the Python environment

Open PowerShell in the cloned project folder:

    py -3.12 -m venv .venv-embeddings
    .\.venv-embeddings\Scripts\python.exe -m pip install --upgrade pip

Install a PyTorch build that matches the computer. For NVIDIA CUDA, use the commands produced by the [official PyTorch installation selector](https://pytorch.org/get-started/locally/). For a CPU-only computer, select the CPU build there. Install PyTorch before the project packages.

    .\.venv-embeddings\Scripts\python.exe -m pip install -r ingestion/requirements.txt -r ingestion/requirements-embeddings.txt -r bot/requirements.txt

### 2. Download BGE-M3 and prepare the local index

The repository includes the current SQLite index. This first command downloads the pinned BGE-M3 model into the ignored local **.cache** directory and checks or rebuilds the index using that model identity. With an unchanged source catalogue and matching dependencies, existing vectors are reused.

    .\.venv-embeddings\Scripts\python.exe ingestion/bge_embeddings.py build --download

After changing collected files, mappings, chunking, or resource imports, use the full pipeline command instead. It rebuilds normalized source records, embeds every eligible chunk, creates the per-topic resource map, and checks source/index/map coverage:

    .\.venv-embeddings\Scripts\python.exe ingestion/run_pipeline.py

On a fresh machine, add **--download** to let Hugging Face fetch BGE-M3. The vector cache resumes interrupted work and reuses unchanged text. To refresh the saved book/NPTEL source snapshots, use **--reextract-resources**; **--reextract** also refreshes the saved curriculum and faculty extraction.

### Optional: use your Azure OpenAI embedding deployment

The Azure adapter uses the deployment from the Azure portal and writes a separate 1,536-dimensional index, so Azure vectors never mix with the local 1,024-dimensional BGE-M3 index. The completed Azure index is included in the repository so a clone can reuse the document vectors without re-embedding the entire collection. Azure still needs a valid API key to embed each student's query. The local `.env` is initialized with the resource endpoint and deployment name. Keep the key in **AZURE_OPENAI_API_KEY** in **D:\outreach\.env**; do not paste it into chat or commit it. To rebuild after source changes, run:

    .\.venv-embeddings\Scripts\python.exe ingestion\run_pipeline.py --provider azure

Azure's `/openai/v1/embeddings` endpoint is used with the deployment name as the model field. The pipeline batches requests and retries temporary rate-limit/service errors. Azure usage is billed to your subscription; the deployment's TPM setting limits throughput, not spend. The chatbot selects the Azure index when **SIGNAL_EMBEDDING_PROVIDER=azure** is set in **.env**.

The model is **BAAI/bge-m3**, pinned to the revision recorded in **ingestion/bge_embeddings.py**. Its model card lists the MIT licence, 1,024 output dimensions and an 8,192-token maximum sequence length: [BGE-M3 model card](https://huggingface.co/BAAI/bge-m3).

### 3. Start the chatbot

For deterministic catalogue answers and retrieval, without generated responses:

    .\Start-Signal.ps1 -NoLLM

For the normal local presentation with optional Qwen answers, install [Ollama](https://ollama.com/download), download the model once, then warm up both models before showing the menu:

    ollama pull qwen3:4b-instruct
    .\Start-Signal.ps1 -Warmup

The selected Qwen model is the 4B Instruct Q4_K_M variant, approximately 2.5 GB to download. Its Ollama model page lists the Apache 2.0 licence: [Qwen3 4B Instruct](https://ollama.com/library/qwen3:4b-instruct). Ollama and the model run locally; do not sign into a cloud model or configure an API key for this project’s local mode.

Try this flow:

    Show me courses of 2nd year at IIT Roorkee in 2026
    ECC-201
    Which topics should I study?
    2
    Explain the second unit
    Make it simpler

Other useful inputs include **DSP**, **convolution**, **/courses 1-4**, **/faculty VLSI**, **/projects VLSI**, **/clear**, **menu**, and **/quit**. Local resource browsing loads BGE when the first search is made; **-Warmup** loads it before the menu.

**Start-Signal.ps1** prefers the project’s optional Ollama runtime if present, otherwise it uses an installed local Ollama service. Model calls are restricted to a local loopback address. If Ollama or Qwen is absent, course browsing and deterministic resource search remain available. The assistant does not require **OPENAI_API_KEY**.

## What to buy and expected cost

### Recommended budget for the current presentation build

**Required purchases now: ₹0.** The current implementation uses local models and an existing laptop. It does not require paid LLM calls, paid embedding calls, a vector-database subscription, a domain, a web host, or a Telegram hosting provider for a scheduled laptop presentation.

| Item | Needed now? | Current planned cost | Notes |
|---|---:|---:|---|
| BGE-M3 embeddings | Yes, model download | ₹0 API spend | Runs locally; download the model once. |
| Qwen3 4B Instruct | Optional | ₹0 per local inference | Local Ollama model; download once. |
| OpenAI or other hosted LLM API | No | ₹0 | GPT-6 Luna and paid embeddings are not connected. Do not buy API credits for the current local stack. |
| Telegram bot token | Later | ₹0 | Create it with BotFather when local behaviour is accepted; keep the token in **.env**. |
| Telegram Bot Platform | Later | ₹0 for ordinary bot use | Telegram describes its bot platform as free for developers. A bot process still needs an always-on computer or host to answer at all times. See [Telegram bot platform](https://core.telegram.org/bots). |
| SQLite / vector database | Yes, SQLite | ₹0 | The local SQLite index is already part of the project. No hosted database is needed for the demo. |
| Hosting | No for presentation | ₹0 | Run on the team laptop during the presentation. Public 24/7 access later needs an always-on host; choose and price it only after measuring model memory and uptime needs. |
| New hardware | No, if using an existing computer | ₹0 assumed | The tested laptop has an 8 GB NVIDIA GPU. CPU works more slowly; test the actual presentation computer. |
| Claude Code subscriptions | Optional developer tooling | Not a chatbot runtime cost | The team previously quoted ₹4,800 for two subscriptions. If that remains in the budget, it leaves ₹3,200 from the ₹8,000 cap. These subscriptions do not run Signal and are not required to build or present the current local demo. |

The earlier plan to spend roughly ₹3,000 on GPT-6 Luna and ₹300 on an embedding API has been superseded by local Qwen and BGE-M3. Do not treat those older API estimates in **docs/one-month-cost-plan.md** as the active purchase list. If the team later chooses a hosted model, verify its live model price, enable usage limits/alerts and record the provider and monthly cap before using it.

For the current scope, the sensible plan is to hold the ₹8,000 budget rather than preload API balances. If two Claude Code subscriptions are still approved at the team’s quoted ₹4,800 total, keep the remaining ₹3,200 uncommitted until a measured need for hosting or a paid model appears. No cloud spend is required to complete the local demo.

## What is complete and what remains

### Completed

- Seven-section menu and shared conversation flow for local chat and Telegram.
- Course browsing grouped by year/semester and exact code/credit/semester lookup.
- Syllabus topic selection, course filters and source-backed resource recommendations.
- Per-course coverage map for each collected syllabus topic, with chapter/lecture candidates, syllabus reading-list references, and explicit missing-data statuses.
- Syllabus book recommendations are returned when exact chapter contents are not available; the bot distinguishes bibliographic references from collected table-of-contents chapter matches.
- Faculty research-interest retrieval and recorded department-project retrieval.
- One-command source-to-chunks-to-BGE-index-to-topic-map pipeline, hybrid rank fusion, SQLite persistence, pinned model revision, resumable indexing and source-to-index checks.
- Optional local Qwen3 answer model, bounded prompts/output, source-ID validation, local response cache and no paid-model fallback.
- Windows launcher with optional warm-up and no-LLM mode.
- Academic source snapshots, checksums, extracted JSON data, course mappings and retrieval/model demo reports.
- Telegram bot adapter and per-user in-memory conversation state. The adapter has not been connected to a live token.

### Next work, in order

1. **Review timetable OCR and workbook applicability.** Compare each timetable year page with the source PDF and each workbook row with its owner/academic source. Correct OCR errors, keep unknown rooms/faculty/groups unknown, preserve sheet/page evidence, and establish which cohort and term these files apply to. Do not imply a timetable row applies to a student when its section is missing.
2. **Extend timetable acceptance coverage.** The exact lookup, multi-turn year/section flow and key no-fabrication cases are implemented and tested. Add reviewed examples for every weekday, overlaps, missing room/faculty, term scoping and source-corrected OCR. Keep timetable answers out of semantic/LLM generation.
3. **Run and extend chatbot evaluation.** Ask ECE students/teammates to prepare 20–30 representative questions and expected source/course. Measure resource, course and timetable retrieval separately, along with incorrect recommendations, correct abstention, citation validity and latency. Include code mismatches, abbreviations, indirect descriptions and out-of-scope questions.
4. **Connect Telegram after the local flow is accepted.** Create the bot with [@BotFather](https://t.me/BotFather), put **TELEGRAM_BOT_TOKEN=...** in a local **.env**, and run the adapter. Never paste the token into chat or commit it. Test in a private conversation with **/start**, menu buttons, courses, search, **/clear**, long responses, invalid input and simultaneous users.
5. **Rehearse locally before the professor presentation.** Warm up models before the first question; check the Wi-Fi and laptop power settings; keep the no-LLM path available; prepare a short sample conversation and a screenshot/recording in case the network or local model is slow.
6. **Decide on 24/7 hosting only if the scope changes.** Benchmark memory, cold-start time, request concurrency and monthly uptime first. Select a provider only after those measurements; keep the local demo as a fallback.

### Later improvements

- Add verified academic calendar/exam dates, current notices, official notes/PYQs, lab manuals and lab/contact/policy data with source and date tracking.
- Add supported cross-catalogue queries and a genuinely unified search. Current natural-language search does not cover every one of the seven menu sections.
- Improve the course-to-syllabus mappings with academic review where code, title, cohort or course scope differs.
- Add review/expiry dates for timetable and notice records and a clear way to refresh or correct them.
- Improve educational answer quality using a reviewed ECE question set. A small local test set is a smoke check, not proof that generated answers are correct.
- If students use Telegram at scale, add a privacy notice, rate limits, durable data policies, service monitoring and a documented incident/contact process before launch.

## How to test

Run these commands from the project root after setting up the Python environment.

### Automated checks

    .\.venv-embeddings\Scripts\python.exe -m unittest discover -s ingestion -p test_bge_embeddings.py

    .\.venv-embeddings\Scripts\python.exe -m unittest bot.test_bot bot.test_catalogue bot.test_conversation bot.test_local_llm

The checks cover index integrity and cache behaviour, exact curriculum lookup, conversational navigation, missing-data responses, Telegram adapter behaviour with mocks, local model request validation and source citation handling. They do not call Telegram or a paid API.

Run the extraction/data validator after changing source extraction or course mappings:

    .\.venv-embeddings\Scripts\python.exe ingestion/validate_catalogue.py

### Real retrieval evaluation

This loads the local BGE model, searches the indexed data, and writes the detailed result to **docs/embedding-evaluation.json**:

    .\.venv-embeddings\Scripts\python.exe ingestion/evaluate_embeddings.py

The latest real-model report records book/lecture checks plus course and timetable retrieval cases separately. It is a small developer-authored smoke set, not a general benchmark; inspect **docs/embedding-evaluation.json** for the current ranks and results. Re-evaluate after changing source mappings, chunking, embedding provider or threshold.

### Local model and conversation smoke check

With Ollama running and **qwen3:4b-instruct** installed:

    .\.venv-embeddings\Scripts\python.exe -m bot.validate_local_llm

The recorded local-LLM run predates the new workbook and timetable flow. Re-run it after the timetable/navigation changes if Ollama is available. It checks application behaviour, not the correctness of every generated educational claim. Review generated ECE answers against course sources.

### Manual acceptance flow

1. Start with **.\Start-Signal.ps1 -Warmup**.
2. Ask for Year 2 courses and confirm the full semester-grouped list contains course codes.
3. Select a course and ask for its topics; select a topic and check that resource links name their source.
4. Ask for an exact credit/semester fact and ensure it comes from the catalogue.
5. Ask for VLSI faculty or projects and confirm they are described as research/recorded projects, not current teaching/openings.
6. Ask an unrelated question, such as a recipe, and confirm the bot abstains.
7. Use **/clear**, then ask a new topic and make sure old course context is gone.
8. Ask for `/timetable`, choose a year, then a recorded student section when prompted. Verify exact rows, source-missing values, and that course-cell batches are not treated as student sub-batches. Year IV has no student-section mapping in this OCR source, so the response must say it cannot personalize those entries.
9. Ask “I’m a second-year student from ECE-3 batch; show my timetable” and confirm it resolves to section **25EC3** from the selected year. Ask “Who is the professor for ECT-108?” and check that the answer labels the name as team-supplied and unverified for the current offering.

For each change, re-run the relevant automated checks and the affected manual cases. Before a student pilot or public release, have an ECE instructor review the timetable, mappings, citations and generated-answer examples.

## Data and privacy rules

- Keep **.env**, Telegram tokens and any future API keys out of Git. **.env.example** contains placeholders only.
- Do not put student roll numbers, private class rosters, chat histories, phone numbers or private course groups into embedding text.
- Preserve source URL, retrieval date, source version/checksum, page/section locator and applicability status for academic facts.
- Treat missing data as unknown. Never infer that a class, faculty assignment, room, elective or sub-batch applies to a student from a partial record.
- Keep faculty research interests separate from term teaching assignments.
- Do not represent a book contents page as full-text access to the book.
- The repository contains collected academic source snapshots and publisher contents metadata. Keep the GitHub repository private unless the team reviews the source licences, redistribution rights and personal-data implications first.
- Telegram messages pass through Telegram’s service if the bot is connected; the project code does not persist chat transcripts. Review the privacy flow before inviting students.

The BGE-M3 model card lists an MIT licence, and the selected Qwen model page lists Apache 2.0. Follow those licences and check the licences/terms for source documents and datasets separately. Model licences do not automatically grant redistribution rights for the collected source material.

## GitHub handoff

The checkout points to the private **ECE_BOT** repository through **origin**. Changes in the current working tree are local and unpushed. Once they are reviewed and committed, push the intended branch with:

    gh auth login -h github.com
    git push origin main

Keep the repository private until the academic source files have been reviewed for redistribution rights.

## Project documents

- Product direction and delivery plan: **docs/ece-companion-roadmap.md**
- Detailed academic data plan and timetable findings: **docs/academic-data-implementation-plan.md**
- Local BGE-M3 design and evaluation: **docs/bge-m3-embeddings.md**
- Local Qwen setup and limitations: **docs/local-llm.md**
- Telegram adapter and later setup: **docs/telegram-implementation.md**
- IIT Roorkee prompt rules: **docs/academic-prompts.md**
- Source catalogue and extraction notes: **datafiles/academic/README.md**
- Embedding evaluation: **docs/embedding-evaluation.json**
- Local model validation: **docs/local-llm-validation.json**
- Prior API-oriented cost plan (historical; superseded for the current local stack): **docs/one-month-cost-plan.md**
