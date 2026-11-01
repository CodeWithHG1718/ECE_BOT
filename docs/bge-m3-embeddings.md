# Embedding and retrieval pipeline

The current local `.env` selects Azure OpenAI `text-embedding-3-small` for document and live query embeddings. BGE-M3 remains a fully local alternative, pinned to Hugging Face revision `5617a9f61b028005a4858fdac845db406aefb181`. Keep Azure and BGE vectors, indexes and query models separate.

The default provider uses Sentence Transformers on CUDA when available and CPU otherwise. The tested laptop has an NVIDIA RTX 4060 Laptop GPU with 8 GB VRAM. Ollama is supported as an alternative provider, but this machine's installed Ollama runtime detected only CPU; direct PyTorch confirmed CUDA availability. We did not change the system Ollama installation.

## Choices

- 1,024-dimensional dense embeddings, L2-normalized and stored as little-endian float32 vectors. No dimensionality reduction: do not treat this model as a Matryoshka model without separate evidence/evaluation.
- Float32 inference prioritises reproducibility and precision for this small dataset. Memory use includes weights, activations and batching; a table's weight-size estimate is not a total VRAM requirement.
- Maximum input length 8,192 tokens, but focused existing chunks are retained (at most 1,835 characters in the current export). Oversized inputs fail explicitly. The indexer never silently truncates a book or syllabus.
- No instruction/query prefix. Queries and documents use the identical model configuration.
- Hybrid retrieval: normalized dense cosine similarity and BM25 keyword retrieval fused with reciprocal rank fusion. This preserves technical terms while permitting semantic paraphrases. BGE-M3 learned sparse and ColBERT heads are not enabled by this dense Sentence Transformers implementation.
- Institute, source-type and exact curriculum-code filters run before ranking. Duplicate entity/type results collapse to a single cited result. Default minimum dense similarity is 0.45: calibrated on the small development set, not a confidence probability or a validated universal cutoff. Light plural normalization fixes keyword mismatches such as `filter`/`filters`.
- NumPy float32 matrix scoring replaces Python loops in the installed runtime. A 128-query LRU cache reuses query embeddings; a 32-entry filter cache reuses BM25 corpus statistics. Caches are memory-only and clear on restart. The study assistant retrieves chapters and lectures separately so one source type cannot crowd out the other.
- Curriculum facts use exact catalogue lookup. Older syllabus code mappings never overwrite current curriculum facts.
- All collected source-backed records are indexed: curriculum/workbook rows, syllabus objectives and topics, all syllabus book references, selected book-chapter contents, NPTEL lecture outlines, faculty/research/project entries, timetable rows and the team-supplied course-professor note. This is not a full-text textbook QA system. Source staging status remains staging; generating an embedding does not approve academic applicability. One publisher chapter label marked ambiguous is intentionally excluded rather than embedding a potentially false citation.

## Files

Input: `datafiles/academic/embedding_chunks.jsonl` (3,312 source-backed chunks), including 808 draft ETE schedule rows across 639 course codes and 61 Autumn 2026–27 calendar records. Detailed ETE assignments cover November 13–21; the broad calendar period runs November 13–24, so detailed assignments for November 23–24 remain unresolved. The page-2 records include timetable changes, UG-I compensatory dates, events/non-teaching days, the teaching-day chart and 11 holidays. Exact course/date answers use deterministic lookups. ETE roster pages 31–33 are excluded from records and embeddings. A checksummed JSON snapshot of schedule-only records supports clean-clone rebuilds; the original PDF is ignored by Git.

Generated local index: `datafiles/academic/vectors/bge-m3.sqlite3` (1,024 dimensions). It is a separate offline option. The SQLite store is sufficient for this small single-laptop demo; the original source JSON remains authoritative. Exhaustive cosine scoring avoids approximate-search recall loss at this scale. A production database/vector service can be added later if usage justifies it.

Azure index: `datafiles/academic/vectors/azure-text-embedding-3-small.sqlite3` (1,536 dimensions). It has its own model manifest/cache and is never mixed with the BGE-M3 index. The current app needs a valid Azure API key for live query embeddings; Azure rebuilds need it too. Configure `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`, and `SIGNAL_EMBEDDING_PROVIDER=azure` in the ignored project `.env`. Run `python ingestion/run_pipeline.py --provider azure` after changing source records or chunks. The endpoint is the Azure resource root; the API key is read locally and is never written to the index or logs. Azure v1 uses `POST /openai/v1/embeddings` and the deployment name as `model`. See [Microsoft's Azure embedding guide](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/embeddings).

Generated topic map: `datafiles/academic/topic_resource_map.json`. It accounts for all 120 course identities, all 232 source-syllabus topics, the 180 curriculum/topic pairs with a supported course link, and 52 older syllabus topics that remain unmapped. Twenty-nine curriculum identities have detailed mapped syllabus content; 91 have no detailed syllabus in the supplied files. The current map finds chapter or lecture candidates for 90 topic rows and records no collected topical match for 142. It lists course-level bibliography references and records up to three chapter and NPTEL candidates per topic. Unmapped-source candidate searches are explicitly labelled unverified. Candidate ranking is automatic and is not academic approval. The chatbot shows candidate counts when a student opens a course, searches the selected topic again, and can return a syllabus book reference when a matching chapter contents page is unavailable.

Tables contain a content-addressed vector cache, the active document snapshot and a model/source manifest. Cache keys include embedding text, provider, model revision/digest, dimensions, prompt, normalization and relevant library versions. A metadata-only change reuses the vector while publishing updated citations. Changed text generates a new vector. Removed chunks disappear from the active snapshot on rebuild.

Every completed batch is committed to the cache. The active snapshot changes only after the complete build succeeds. Interrupted builds resume without re-encoding cached content. Query startup rejects stale source checksums and incompatible model identities. Query-time identity checks prevent a changed Ollama tag from being mixed with older vectors. HF loading is pinned and local-only after setup.

## Running

See `telegram-implementation.md` for environment installation. The current Azure provider needs an API key for live semantic searches and Azure rebuilds. To avoid hosted embedding charges, select BGE-M3 and rebuild its separate index and topic map with `--provider huggingface`.

```powershell
.\.venv-embeddings\Scripts\python.exe ingestion/run_pipeline.py --provider azure
.\.venv-embeddings\Scripts\python.exe ingestion/run_pipeline.py --provider huggingface --download
.\.venv-embeddings\Scripts\python.exe ingestion/run_pipeline.py --provider huggingface
.\.venv-embeddings\Scripts\python.exe ingestion/bge_embeddings.py search "convolution and LTI response" --provider huggingface --course ECC-106 --type book_chapter
.\.venv-embeddings\Scripts\python.exe ingestion/evaluate_embeddings.py
.\.venv-embeddings\Scripts\python.exe -m bot.main --demo "convolution" --course ECC-106
```

`--download` permits the first Hugging Face download; subsequent BGE embedding runs are local. The project-local model cache and Python environment are excluded from version control. Azure indexing uses batches up to 64 in this project; BGE uses batches up to eight. Reduce batch size on smaller machines. The tokenizer guard protects against oversized future chunks. If much larger books are added, first implement paragraph/section-aware token chunking with modest overlap and source page locators, then rebuild and reevaluate.

`run_pipeline.py` is the normal end-to-end rebuild command after source or mapping changes. It normalizes sources into evidence-backed chunks, incrementally builds a SQLite index for the selected provider, pre-embeds unique syllabus-topic queries, writes the topic/resource coverage map, and checks source-to-index alignment. Use `--provider azure` for the configured deployment or `--provider huggingface --download` for BGE-M3. Azure requests are metered; BGE-M3 embedding calls are local and have no API charge. Use `--reextract-resources` to re-parse saved publisher and NPTEL snapshots, or `--reextract` to refresh the saved curriculum/faculty extraction as well.

For an Ollama-only alternative, pull `bge-m3:567m` and run the pipeline with `--provider ollama`. This produces a different model identity and must not be mixed with other indexes. The current local and Telegram adapters select the provider in `.env`.

## Evaluation and paid fallback

`test_bge_embeddings.py` uses fake vectors strictly to test integrity and recovery mechanics. `evaluate_embeddings.py` runs real BGE-M3 embeddings on 6 development queries, 16 held-out chapter queries, course-catalogue, timetable and professor lookup examples, and unrelated queries; its report is `docs/embedding-evaluation.json`. It is a small developer-authored smoke set, not a broad accuracy benchmark.

The completed run found the expected chapter at rank 1 for 21/22 positive queries (15/16 held-out), and abstained on all 7 unrelated queries. The indirect phrase “Circuits that combine gates without storing any state” produced no chapter above the cutoff; the full chatbot did return a relevant Combinational Circuits lecture. Do not claim universal semantic understanding. Review indirect paraphrases and lecture ordering with students before public use.

The first baseline is preserved in `embedding-evaluation-baseline.json`: it returned irrelevant results for a nonsense token and ranked the filter-design chapter third. The higher cutoff and plural normalization corrected those development issues before the held-out set was run. A measured cached repeat lookup took 0.0035 seconds on this laptop; this excludes model startup and is not a service-level guarantee.

Historical BGE validation: 7 index integrity/cache tests and 16 chatbot/catalogue tests passed. Six additional real-model chatbot checks passed; the readable transcript is `docs/local-chatbot-demo.md`. This records the earlier local BGE-M3 configuration, not the current Azure-selected provider. Telegram was not contacted.

Before spending on another model, review 20–30 realistic ECE queries with expected chapters/lectures/faculty. Include paraphrases, acronyms, code mismatches, multi-topic requests and topics missing from the catalogue. Measure hit@5, incorrect recommendations, abstention and latency. Missing source material must be fixed in the data rather than by buying a different model.

The current Azure provider and local BGE-M3 implement the same `identity()` / `encode(texts)` boundary with separate dimensions and caches. Build a complete index per provider and use the same model for queries; never compare or combine vectors from different models directly. No automatic provider fallback is configured. Azure embedding calls are metered; local BGE-M3 has no per-token API fee. Chat generation with local Qwen is a separate cost path.

Official references: https://huggingface.co/BAAI/bge-m3 ; https://www.sbert.net/docs/package_reference/sentence_transformer/model.html ; https://docs.ollama.com/api/embed .
