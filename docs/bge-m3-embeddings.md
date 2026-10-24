# BGE-M3 embedding and retrieval pipeline

Selected model: `BAAI/bge-m3`, original Hugging Face revision `5617a9f61b028005a4858fdac845db406aefb181`.

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
- Only collected chapter contents, syllabus sections, faculty evidence and lecture outlines are indexed. This is not a full-text textbook QA system. Source staging status remains staging; generating an embedding does not approve academic applicability.

## Files

Input: `datafiles/academic/embedding_chunks.jsonl` (2,094 source-backed chunks).

Generated index: `datafiles/academic/vectors/bge-m3.sqlite3`. The SQLite store is sufficient for this small single-laptop demo; the original source JSON remains authoritative. Exhaustive cosine scoring avoids approximate-search recall loss at this scale. A production database/vector service can be added later if usage justifies it.

Tables contain a content-addressed vector cache, the active document snapshot and a model/source manifest. Cache keys include embedding text, provider, model revision/digest, dimensions, prompt, normalization and relevant library versions. A metadata-only change reuses the vector while publishing updated citations. Changed text generates a new vector. Removed chunks disappear from the active snapshot on rebuild.

Every completed batch is committed to the cache. The active snapshot changes only after the complete build succeeds. Interrupted builds resume without re-encoding cached content. Query startup rejects stale source checksums and incompatible model identities. Query-time identity checks prevent a changed Ollama tag from being mixed with older vectors. HF loading is pinned and local-only after setup.

## Running

See `telegram-implementation.md` for environment installation. No embedding API key is needed.

```powershell
.\.venv-embeddings\Scripts\python.exe ingestion/bge_embeddings.py build --download
.\.venv-embeddings\Scripts\python.exe ingestion/bge_embeddings.py build
.\.venv-embeddings\Scripts\python.exe ingestion/bge_embeddings.py search "convolution and LTI response" --course ECC-106 --type book_chapter
.\.venv-embeddings\Scripts\python.exe ingestion/evaluate_embeddings.py
.\.venv-embeddings\Scripts\python.exe -m bot.main --demo "convolution" --course ECC-106
```

`--download` permits the first Hugging Face download; later commands are local-only. The project-local model cache and Python environment are excluded from version control. Rebuilds use small batches of eight; reduce the batch size on smaller machines. The tokenizer guard protects against oversized future chunks. If much larger books are added, first implement paragraph/section-aware token chunking with modest overlap and source page locators, then rebuild and reevaluate.

For an Ollama-only alternative, pull `bge-m3:567m` and pass `--provider ollama` to both `build` and `search`. This produces a different model identity and must not be mixed with the HF snapshot. The current Telegram runner uses the default HF provider.

## Evaluation and paid fallback

`test_bge_embeddings.py` uses fake vectors strictly to test integrity and recovery mechanics. `evaluate_embeddings.py` runs real BGE-M3 embeddings on 6 development queries, 16 held-out chapter queries, and 7 unrelated queries; its report is `docs/embedding-evaluation.json`. It is a small developer-authored smoke set, not a broad accuracy benchmark.

The completed run found the expected chapter at rank 1 for 21/22 positive queries (15/16 held-out), and abstained on all 7 unrelated queries. The indirect phrase “Circuits that combine gates without storing any state” produced no chapter above the cutoff; the full chatbot did return a relevant Combinational Circuits lecture. Do not claim universal semantic understanding. Review indirect paraphrases and lecture ordering with students before public use.

The first baseline is preserved in `embedding-evaluation-baseline.json`: it returned irrelevant results for a nonsense token and ranked the filter-design chapter third. The higher cutoff and plural normalization corrected those development issues before the held-out set was run. A measured cached repeat lookup took 0.0035 seconds on this laptop; this excludes model startup and is not a service-level guarantee.

Final validation: 7 index integrity/cache tests and 16 chatbot/catalogue tests passed. Six additional real-model chatbot checks passed; the readable transcript is `docs/local-chatbot-demo.md`. Telegram was not contacted. The installed tokenizer, model, index and query provider all use the pinned BGE-M3 configuration.

Before spending on another model, review 20–30 realistic ECE queries with expected chapters/lectures/faculty. Include paraphrases, acronyms, code mismatches, multi-topic requests and topics missing from the catalogue. Measure hit@5, incorrect recommendations, abstention and latency. Missing source material must be fixed in the data rather than by buying a different model.

A paid provider can implement the same `identity()` / `encode(texts)` boundary, with its own dimensions and vector serialization configuration. Build a separate complete index and use that model for queries too; never compare or combine vectors from different models directly. No automatic paid fallback is configured. Local BGE-M3 has no per-token API fee; future hosted inference, electricity and generation API costs are separate.

Official references: https://huggingface.co/BAAI/bge-m3 ; https://www.sbert.net/docs/package_reference/sentence_transformer/model.html ; https://docs.ollama.com/api/embed .
