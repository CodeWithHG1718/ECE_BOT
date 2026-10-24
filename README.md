# Signal — ECE study companion

Current scope: complete the local chatbot and BGE-M3 retrieval before Telegram setup/deployment. The earlier website prototype is inactive.

Product direction: **ECE Companion**, a seven-section department assistant. The main menu now follows Academics, Courses & Learning, Faculty & Research, Projects & Career, Department & Campus, Notices & Updates, and AI Assistant. See the [product roadmap](docs/ece-companion-roadmap.md) for implemented capabilities and remaining work. Missing data is labelled explicitly; the menu does not imply that every service is already available.

## Try the local chatbot

```powershell
./Start-Signal.ps1
```

Or run `.\.venv-embeddings\Scripts\python.exe -X utf8 -m bot.local_chat` from this directory. No API key or Telegram token is needed. Try this conversation:

```text
Show me courses of 2nd year at IIT Roorkee in 2026
Which topics should I study?
ECC-201
2
```

The bot lists all course codes and names under Semesters 3 and 4, then shows course topics. Selecting topic 2 retrieves resources for Random Processes and Noise Models. `menu` shows the guide; `/clear` resets selections; `/quit` exits. `/courses 1-4` lists all four years. Browsing does not load the embedding model; resource search loads it when needed.

For the presentation, run `./Start-Signal.ps1 -Warmup` to load BGE-M3 and Qwen before the menu appears. Try `DSP`, `Explain the second unit`, then `Make it simpler`. The launcher starts the local Ollama service if necessary. `-NoLLM` keeps catalogue browsing and source retrieval while disabling generation.

The academic year (2026) is separate from study year (1–4). The bot explicitly reports that the supplied curriculum/syllabus applicability to 2026 is unverified. See [academic prompt templates](docs/academic-prompts.md) for the grounding rules.

## Set up on another Windows computer

Use Python 3.12. The checked-in SQLite index and extracted catalogue let you skip re-embedding for a normal run; the pinned BGE-M3 model files still need to be downloaded once. Open PowerShell in the project folder:

```powershell
py -3.12 -m venv .venv-embeddings
.\.venv-embeddings\Scripts\python.exe -m pip install --upgrade pip
```

For an NVIDIA GPU, install the matching PyTorch CUDA wheel from the [official PyTorch selector](https://pytorch.org/get-started/locally/), then install the project packages and download the pinned embedding model:

```powershell
.\.venv-embeddings\Scripts\python.exe -m pip install -r ingestion/requirements-embeddings.txt -r bot/requirements.txt
.\.venv-embeddings\Scripts\python.exe ingestion/bge_embeddings.py build --download
```

The `build --download` command checks the saved index and downloads BGE-M3 into the local `.cache` if needed. On a CPU-only computer, PyTorch can run the same pipeline more slowly; install its CPU wheel from the PyTorch selector instead. Then launch the chatbot:

```powershell
.\Start-Signal.ps1
```

To enable the optional local answer model, install [Ollama](https://ollama.com/download), pull Qwen once, and start Signal with model warm-up:

```powershell
ollama pull qwen3:4b-instruct
.\Start-Signal.ps1 -Warmup
```

Ollama and Qwen are optional. Without them, course browsing and BGE-backed resource search still work. Everything runs on the computer; there is no OpenAI key, embedding API fee, Telegram token, or hosted server requirement for local use. First-time downloads need an internet connection. Model files, the Python environment, runtime logs, and secrets stay out of Git. See [BGE-M3 setup](docs/bge-m3-embeddings.md) and [local answer model setup](docs/local-llm.md) for details.

## Pipeline

```text
Source PDFs / official pages / publisher contents / NPTEL outlines
    -> validated structured catalogue + evidence-preserving chunks
    -> local BAAI/bge-m3, 1,024 dimensions, pinned original weights
    -> resumable SQLite index + normalized vector matrix + BM25
    -> exact course routing / filtered hybrid retrieval / source deduplication
    -> local Qwen3 4B Instruct for explanations and resource summaries
    -> study-guidance chatbot with application-rendered source links
    -> Telegram adapter (connection and deployment deferred)
```

Qwen3 4B Instruct now runs locally through Ollama alongside BGE-M3. General explanations, examples and plans are labelled as local AI guidance. Course facts, faculty/project records, missing-data responses and source URLs stay in the catalogue renderer. The system does not claim full textbook access or confirmed faculty supervision availability. See [local LLM setup and validation](docs/local-llm.md).

- [Embedding setup and design](docs/bge-m3-embeddings.md)
- [Chatbot and later Telegram setup](docs/telegram-implementation.md)
- [Real retrieval evaluation](docs/embedding-evaluation.json)
- [Actual local chatbot transcript](docs/local-chatbot-demo.md)
- [Course and project/faculty navigation walkthrough](docs/menu-model-walkthrough.md)
- [Actual local LLM conversation](docs/local-llm-demo.md)
- [Local LLM timings and checks](docs/local-llm-validation.json)
- [Original data and extraction notes](datafiles/academic/README.md)

The model and index run locally. No paid embedding or generation calls are made. Secrets belong only in ignored environment files, when integration begins.
