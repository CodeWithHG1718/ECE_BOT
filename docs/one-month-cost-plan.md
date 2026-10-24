# ECE chatbot: final one-month budget proposal

**18 October 2026 scope update:** the user selected local `BAAI/bge-m3` embeddings and a Telegram interface, with local chatbot completion/evaluation before connection or deployment. Embedding API spend is now INR 0 for the local implementation. The older model/API allocation and rates below are historical planning notes, not a current purchase recommendation. Any future paid generation or embedding provider must be verified and selected before purchase. See `bge-m3-embeddings.md` and `telegram-implementation.md`.

Updated 4 October 2026. This replaces earlier cost plans based on a student rollout or full textbook question answering.

Confirmed scope: develop and deploy an ECE academic assistant for a professor's presentation, with repeated team testing. Books support study guidance: relevant topics, verified chapters/sections and lecture recommendations. No student-scale rollout is planned. Available project budget: INR 8,000 maximum. Website or Telegram can be used; interface choice remains open.

## Recommended components and model rates

Use text-embedding-3-small for document/resource descriptions and incoming questions; Qdrant plus PostgreSQL keyword/exact lookups for search; GPT-6 Luna for natural-language academic responses and study recommendations. A structured resource list or exact timetable response can be rendered without generation. No separate paid search model is necessary.

Official standard text prices checked 4 October 2026:

| Component | USD rate | INR planning equivalent |
|---|---:|---:|
| text-embedding-3-small | USD 0.02 / 1 million input tokens | INR 2.28 / million tokens |
| GPT-6 Luna input | USD 0.10 / 1 million input tokens | INR 11.40 / million tokens |
| GPT-6 Luna output | USD 0.50 / 1 million output tokens | INR 57.00 / million tokens |

Sources: [embedding model](https://developers.openai.com/api/docs/models/text-embedding-3-small), [answer model](https://developers.openai.com/api/docs/models/gpt-6-luna).

The INR estimates assume INR 95/USD plus a 20% allowance for applicable taxes, FX and payment costs, giving INR 114/USD. This is a planning conversion, not a live exchange-rate quote. Actual invoice prices and account/model availability must be checked when provisioning. These estimates use standard API generation and our own retrieval, without paid built-in search or other tools. Any reasoning tokens count toward billed output. No caching discounts are assumed.

## Budget list for submission

| Budget item | Purpose | Allocation |
|---|---|---:|
| Initial API allowance | INR 1,000 for generation/testing, INR 400 for preparation and retries, INR 100 for embeddings; shared provider balance | INR 1,500 |
| Additional API reserve | More testing, longer prompts/answers and repeated evaluation after changes | INR 2,000 |
| Optional paid hosting reserve | Use only if free deployment does not perform adequately during rehearsals; obtain the live quote first | INR 1,500 |
| General contingency/uncommitted balance | Unexpected expenses or additional approved project work; keep unspent if unnecessary | INR 3,000 |
| Website/backend | Render Free within included usage | INR 0 initially |
| PostgreSQL | Neon Free within account limits | INR 0 initially |
| Vector search | Qdrant Cloud Free within account limits | INR 0 initially |
| Telegram channel, if selected | Official Bot API, normal messaging | INR 0 |
| Domain and HTTPS | Included hosting subdomain and TLS | INR 0 |
| Resource catalogue | Existing syllabus, verified book metadata, public lecture links and short reviewed topic descriptions | INR 0 additional content purchase |
| Extraction and backups | Existing laptop, local extraction tools, versioned exports and independent backup copy | INR 0 additional |
| **Maximum budget** | **INR 1,500 initial allocation plus INR 6,500 held in reserve** | **INR 8,000** |

The budget is an allocation, not a forecast that all INR 8,000 will be spent. Prepaid API credits and token usage are the same expenditure: do not count both separately. The initial cash target is up to INR 1,500, subject to the provider's checkout credit requirements. Keep reserves outside provider accounts until required.

Free choices are based on [Render documentation](https://render.com/docs/free), [Neon Free plan](https://neon.com/blog/neon-free-plan-1-gb-per-project), [Qdrant pricing](https://qdrant.tech/pricing/), and [Telegram messaging documentation](https://core.telegram.org/bots/faq). Provider accounts, payment method for the paid API, and deployment credentials still need to be configured. No accounts have been created or services purchased by this planning work.

## Repeated and excess usage

Illustrative test workload: 5,000 total input tokens and 1,000 total billed output tokens per query, with one generation call. Input includes instructions, retrieved resource descriptions and bounded conversation history. Output includes any internal reasoning. This example is not a measured average or a guaranteed cap.

Cost per query = (5,000 x USD 0.10 + 1,000 x USD 0.50) / 1,000,000 = USD 0.001, approximately INR 0.114.

| Generated test/demo queries | Estimated generation cost |
|---:|---:|
| 1,000 | INR 114 |
| 5,000 | INR 570 |
| 10,000 | INR 1,140 |
| 20,000 | INR 2,280 |

These totals exclude extraction experiments, retries, extra model calls and query embeddings. Query embeddings are small: 5,000 questions at 100 tokens each add approximately INR 1.14. Embedding 1 million catalogue tokens costs about INR 2.28 per pass; 5 million costs INR 11.40. Full books are not required for the confirmed guidance feature.

Excess use means additional metered tokens, not a new model subscription. For example, 5,000 queries with 5,000 input tokens and 10,000 billed output tokens each cost approximately INR 3,135 for generation. Long reasoning can therefore use a reserve much faster than the ordinary example. Multiple calls and retries multiply work; record usage and set limits.

Use INR 1,500 as the initial API allocation. The separate INR 2,000 API reserve permits a planned combined API maximum of INR 3,500. Other reserves remain uncommitted; transferring them to APIs should be an explicit team budget decision. These allocations do not themselves enforce a billing limit.

Implement server-side usage accounting, maximum input/output sizes, a bounded retry count, access limits and a cutoff near the current funded allocation. Keep some headroom for in-flight requests and currency/tax differences. Configure provider alerts, but do not assume an alert is a hard stop. Reuse stored embeddings and regenerate only changed entries.

## Other project requirements and presentation limits

- Existing laptops, internet and student development effort are assumed. New hardware, salaries, textbook purchases/licences, printing and travel are outside this service estimate.
- Prepare verified mappings of course/topic to book edition, chapter/section and lecture URL. Human review is required to avoid guessed chapter numbers or unsuitable resources.
- Preserve source and export files locally and keep an independent backup. Record citation links, editions, verification dates and course applicability.
- Use a free hosting address; a custom domain, WhatsApp provider subscription, GPU, fine-tuning, paid OCR and a paid reranker are unnecessary for the confirmed demo scope.
- Free hosting/database quotas are finite. Render Free sleeps after 15 idle minutes and may take about one minute to wake; runtime filesystem writes are ephemeral. Neon and Qdrant keep canonical data/indexes outside the web process. If Telegram is deployed on sleeping web hosting, use a webhook.
- Run a full rehearsal before the presentation and open the app before starting. Keep a local copy and a short screen recording as fallbacks. A local copy using a hosted LLM still needs internet.
- The optional INR 1,500 hosting reserve is a purchasing allowance, not a guaranteed all-provider price or an availability guarantee. Recheck a suitable paid configuration if needed and stay within the total cap.

Recorded recommendation: text-embedding-3-small, Qdrant plus keyword/exact search, GPT-6 Luna, free initial deployment. INR 1,500 initial API allowance; INR 6,500 reserves; INR 8,000 total maximum. No full-textbook tutoring or production student traffic is assumed.
