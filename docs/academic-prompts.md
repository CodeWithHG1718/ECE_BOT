# IIT Roorkee study-guidance templates

`bot/prompts.py` contains shared context and a grounded answer-model template used by `bot/local_llm.py`. The scope is IIT Roorkee, B.Tech ECE, with requested academic year 2026 by default. Academic year and study year are separate fields.

## Current behaviour

- Exact course lists, credits and semesters come directly from the structured curriculum, not vector similarity or generated guesses.
- Course topics come from associated syllabus sections, keeping the original source code and page even when the curriculum code differs.
- Search embeds the study topic. Explicit qualifiers such as “at IIT Roorkee in 2026” stay in session context rather than diluting the semantic query. The local collection is already scoped to this IIT Roorkee project; there is no live web search.
- The supplied curriculum is `btech_ec_str_24.pdf` and the related syllabus is `btech_ec_syll_22.pdf`. Their applicability to 2026 has not been verified. Collection date is not an effective academic date.

Example student requests:

1. “Show me courses of 2nd year at IIT Roorkee in 2026.”
2. “Which topics should I study in Network Theory?”
3. “Suggest lectures and chapters on convolution.”
4. “Which faculty work on VLSI?”

## Connected local answer model

`build_answer_messages(question, evidence, study_year=2, course='ECC-205')` builds system/user messages with the question, institute, programme, academic year, study year, selected code, source limitations and evidence. It accepts an explicit academic year and recognises a year stated in the question. Pass complete structured curriculum rows for course lists, or retrieved chunks with their metadata and source locators for resource questions.

The system template requires all matching course codes, source citations, explicit missing evidence, no fabricated current teaching assignments, and no silent replacement of curriculum codes by older syllabus codes. Retrieved text is treated as data, not instructions. These instructions guide the model; accuracy still needs evaluation against the sources.

The builder itself makes no request. `OllamaChat` sends the messages only to a local loopback Ollama service running `qwen3:4b-instruct`. It supplies at most four deduplicated visible sources and two short prior turns for explanations. A 4,096-token context and 450-token generation limit bound memory and latency.

Generated JSON is checked for usable text, valid source IDs, completion and unsafe/unverified model-produced links; source URLs are rendered from the catalogue. Explanations are labelled as general study guidance, since the available contents/lecture outlines are not full textbooks. Faculty/project availability and course facts bypass generation. Schema validation cannot establish factual or mathematical correctness; student-facing answers still require academic evaluation.

Numbered-unit questions use a separate syllabus-overview mode: the actual mapped unit text is supplied as evidence and its source ID is required in the response. This mode asks what to study, without inventing technical rules from a topic list. The app displays the original syllabus code and page link alongside the overview.
