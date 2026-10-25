# Local answer model: setup, optimisation and verification

## Installed stack

- Answer model: `qwen3:4b-instruct`, Q4_K_M, about 2.5 GB of model files.
- Model digest observed: `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`.
- Retriever: existing BGE-M3 weights and completed index; no re-embedding was required.
- Runtime: official Ollama 0.24.0 standalone Windows package in `.cache/ollama-v0.24.0`.
- API: `http://127.0.0.1:11435` for the project runtime, leaving the system Ollama service on 11434 separate.
- The existing installed Ollama copy lacked the standard CUDA inference libraries and detected CPU only. The verified portable runtime detects the RTX 4060 and offloads all 37 Qwen layers to CUDA.

The runtime archive was verified against the official release SHA-256:
`40c523d3eeba6f4647c5ca58fe47f15b8dee79f7675ebf573458890064f424c7`.

## Run

```powershell
.\Start-Signal.ps1 -Warmup
```

The launcher starts a hidden local Ollama server if needed. Warm-up loads BGE-M3 and Qwen before showing the menu; omitting `-Warmup` keeps course browsing immediate and loads models on demand. `/quit` ends the chat; the local server remains available and model weights expire from memory after ten idle minutes.

Try: `DSP` → `Explain the second unit` → `Make it simpler`. Other examples: `Explain convolution`, `Give a numerical example: convolve [1, 2] with [1, 1]`, or choose Study Planner / Skill Roadmaps.

Use `./Start-Signal.ps1 -NoLLM` for the deterministic catalogue/retrieval path. No API key, paid subscription or Telegram token is needed for local testing.

Configuration uses process environment variables:

- `SIGNAL_LLM=off` disables generation.
- `SIGNAL_OLLAMA_URL` may select another local HTTP loopback port; remote endpoints are rejected. When unset, the portable runtime's port is selected if installed, otherwise 11434.

The launcher configures the project service for one loaded model, one parallel request, a 4,096-token context and flash attention. Cloud access is disabled for that service. It restores the calling shell's temporary environment settings afterwards.

## How answers work

1. Exact navigation, codes, credits, semesters, faculty/project records and known missing data bypass generation.
2. BGE-M3 searches the existing collection. Numbered syllabus explanations search the unit title rather than embedding the full instruction and long unit description; follow-ups reuse that topic.
3. Qwen receives up to four deduplicated sources that correspond to the visible resource list. General explanations can use two bounded prior turns, held in the individual chat's memory.
   Numbered syllabus questions also receive the actual unit outline as a separate source. They produce a syllabus study guide with its own source link, rather than inferring technical requirements from a list of topics.
4. The response must contain valid JSON, usable text and known source IDs. Invented model-generated URLs and incomplete responses are rejected; HTML is escaped.
5. Course suggestions can search the expanded workbook/curriculum embeddings. Course lists and timetable rows are rendered from structured records; timetable answers do not call Qwen.
6. The application supplies the actual source links. Failures fall back to source-backed results; there is no paid/cloud fallback.

Context is 4,096 tokens, generation is capped at 450 tokens, and successful responses use a bounded 32-entry in-memory LRU cache. Existing BGE query/filter caches remain active. `/clear` removes conversational state; changing courses/years clears stale topic history.

These checks do not prove mathematical or factual correctness. Review of the initial unrestricted summaries found an unsupported project-status statement and a sampling misconception. Faculty/project generation was removed, and numbered-unit explanations now use a narrower syllabus-overview prompt with an explicit outline source; the live sample checks include the observed misconception. The local model can handle informal help-seeking and small talk when the request is not a structured course/timetable lookup; structured facts still come from the application. General explanations are model-generated educational guidance rather than official IIT Roorkee answers or full-textbook quotations. Current-session applicability of the supplied curriculum remains unverified. The timetable is an OCR-derived recurring Autumn 2026–27 extract; unrecorded student sections, rooms, faculty and timetable changes remain unknown. Notices, notes/PYQs and reminder scheduling are still separate unfinished features.

## Verification

```powershell
.\.venv-embeddings\Scripts\python.exe -m unittest bot.test_bot bot.test_catalogue bot.test_conversation bot.test_local_llm
.\.venv-embeddings\Scripts\python.exe -m bot.validate_local_llm
```

See `local-llm-validation.json` for the latest actual timings and `local-llm-demo.md` for the responses. The initial cold-start measurements are retained in `local-llm-validation-initial.json`; that initial run loaded both models on demand and took about 46 seconds for the first generated response. Warm-up moves this loading before the demonstration starts. Subsequent generated answers in that run took roughly 2–3.4 seconds; cached responses were substantially faster. These are laptop/sample measurements, not guaranteed latency or a comprehensive educational evaluation.

## Reproduce on another machine

Runtime and model caches are intentionally ignored by Git. Download the matching official standalone ZIP, verify the SHA-256 above and extract it into `.cache/ollama-v0.24.0`; obtain the model with `ollama pull qwen3:4b-instruct`. The runtime uses the normal Ollama model cache. The Python environment and BGE index must also be prepared as documented in `bge-m3-embeddings.md`.

Official references: [model](https://ollama.com/library/qwen3:4b-instruct), [Ollama Windows setup](https://docs.ollama.com/windows), [runtime release](https://github.com/ollama/ollama/releases/tag/v0.24.0), [chat API](https://docs.ollama.com/api/chat), [structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
