# Signal Telegram chatbot

Decision, 18 October 2026: Telegram is now the project interface. Website work is stopped; `frontend/` is retained only as the earlier prototype. No website deployment is needed. The existing academic extraction remains the shared source.

Current priority confirmed by the user: finish embeddings and local chatbot behaviour first. Telegram setup and deployment are a subsequent stage. The user will supply the token later; do not start live bot registration or polling in this stage.

## Flow

```text
Student's Telegram private chat
    -> python-telegram-bot long polling on the demo laptop
    -> seven-section persistent menu / contextual inline buttons / per-user course context
    -> exact curriculum lookup for courses, credits and semesters
    -> BGE-M3 query embedding + dense/BM25 rank fusion for study topics
    -> source-backed chapter, lecture, faculty and recorded project links
```

Qwen3 4B Instruct is connected locally through Ollama for explanations and resource summaries. Course/faculty/project facts and links remain source-rendered; general educational answers are labelled as local AI guidance. The adapter shares this pipeline with local chat. See `local-llm.md`; Telegram connection/deployment remains deferred.

## Commands

- `/start`, `/menu`, `/help`: seven-section main catalogue and examples.
- `/courses`: choose Years 1–4 or unassigned electives/options. A selected year shows every course with its code, grouped by semester. Long lists are sent in multiple messages.
- `/course ECC-106`: exact curriculum details, mapped syllabus topics and a course filter for later resource searches.
- `/faculty VLSI`: official research-profile links; does not assert supervision availability.
- `/projects VLSI`: matching recorded departmental projects; does not assert current openings.
- `/resources`, `/search`: prompt for a topic; arguments and direct questions are supported. Search currently covers the supported catalogue types, not all planned data sources.
- `/timetable`, `/notices`: explain that these data sources are not connected yet.
- `/clear`: clear the course filter.
- Plain text: “show me courses of 2nd year”, then a course name/code, then a topic number/name. Direct topic questions or `/ask convolution` retrieve book chapters and NPTEL lectures.

Year 1 is semesters 1–2, Year 2 is 3–4, Year 3 is 5–6, Year 4 is 7–8. No year is guessed from a course number. Source curriculum and syllabus codes remain distinct.

## Setup and presentation

Use Python 3.12 for the embedding environment. From the project root:

```powershell
python -m venv .venv-embeddings
.\.venv-embeddings\Scripts\python.exe -m pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128
.\.venv-embeddings\Scripts\python.exe -m pip install -r ingestion/requirements-embeddings.txt -r bot/requirements.txt
.\.venv-embeddings\Scripts\python.exe ingestion/bge_embeddings.py build --download
.\.venv-embeddings\Scripts\python.exe ingestion/evaluate_embeddings.py
.\.venv-embeddings\Scripts\python.exe -m bot.main --demo "Where should I learn convolution?" --course ECC-106
.\.venv-embeddings\Scripts\python.exe -m bot.local_chat
```

The CUDA wheel above is for the verified NVIDIA laptop. Choose an appropriate official PyTorch wheel on another machine. Model weights download once; later runs load the pinned model locally. See `bge-m3-embeddings.md` for indexing details.

On this configured laptop, use `./Start-Signal.ps1 -Warmup` for a presentation. It starts the project-local Ollama GPU runtime and loads both models before the conversation starts. Local generation can be disabled with `-NoLLM` or `SIGNAL_LLM=off`.

`bot.local_chat` is the current token-free testing interface. It uses the same `Conversation` navigation and `StudyAssistant` service as the future Telegram adapter, including exact curriculum lookups and cited semantic results. Local browsing loads no embedding model until a resource query is submitted. `/quit` exits. Telegram setup below is deferred until the local chatbot and retrieval are accepted.

When ready, create a bot through https://t.me/BotFather using `/newbot`. Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN` locally. The token is a credential and must not be committed or pasted into source files. Then:

```powershell
.\.venv-embeddings\Scripts\python.exe -m bot.main
```

Keep the laptop awake and connected to the internet for the presentation. Open the bot's Telegram link and press Start. No inbound port, public server, domain, TLS certificate or webhook is needed. Stop with Ctrl+C. Only one polling process should run for a bot token. Do not reuse a token with an active webhook unless intentionally migrating that bot.

The user will add the token later. Live Telegram registration/delivery cannot be verified until then. No outgoing Telegram messages have been sent during token-free development.

## Cost and data handling

Local BGE-M3 inference has no per-token API charge. Telegram long polling and the laptop demonstration require no hosting purchase; internet/electricity and any future paid generation model remain separate. A continuously available public bot would need an always-on host.

Course selection and cooldown state are held in memory per Telegram user and clear on restart. The application does not persist chat transcripts or log message bodies/token URLs. Telegram itself transports and stores chat messages under its own policies. Source files are local; only selected public resource references are sent in replies. Private chat use avoids mixing users' course filters in group conversations.

One semantic search runs at a time to protect laptop resources; concurrent users receive a retry message. Long questions are limited to 1,000 characters. Missing sources, unrelated topics, missing models and invalid commands have explicit responses. No paid model is invoked automatically.

## Validation

```powershell
python -m unittest discover -s ingestion -p test_bge_embeddings.py
python -m unittest bot.test_catalogue
.\.venv-embeddings\Scripts\python.exe -m unittest bot.test_bot
.\.venv-embeddings\Scripts\python.exe -m unittest bot.test_conversation
```

Local retrieval checks are recorded in `embedding-evaluation.json`: 21/22 expected chapters found first and 7/7 unrelated queries rejected in this developer-authored sample. The index suite has seven integrity/cache tests. Chatbot tests also cover natural-language year browsing, complete course lists, topic selections, session isolation, long Telegram replies and academic-year prompt grounding. Six real-model chatbot checks and a transcript are in `local-chatbot-checks.json` and `local-chatbot-demo.md`; the year → course → topic walkthrough is documented in `conversation-validation.md`. These are not proof of broad educational quality. Before choosing a paid alternative, have students review 20–30 representative questions with expected sources, compare hit@5 and irrelevant recommendations, and rerun the same set after any model switch.
