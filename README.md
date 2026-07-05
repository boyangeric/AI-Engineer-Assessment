# Multi-Agent Security Policy Q&A (Azure AI)

RBA AI Engineer Assessment — Eric Li

A multi-agent RAG system that answers questions about enterprise security policies.
A **Microsoft Agent Framework** workflow routes typed Pydantic messages through
moderation, planning, retrieval, context reranking, answer generation, and one
faithfulness gate, grounded on **1,014 NIST SP 800-53 Rev 5 security controls** indexed in
**Azure AI Search**. Every LLM agent runs through **Azure OpenAI**
using the framework's native chat client, with explicit determinism controls
and a safe fallback on every failure path.

> **Assessment scope note:** the suggested `AYI-NEDJIMI/nist-csf-en` corpus has
> fewer than 110 rows, so this submission uses the official 1,014-record NIST
> SP 800-53 Rev 5 catalog to satisfy the brief's ≥500-record ingestion requirement.

```
question ─► Moderation ─► Planner ─► Retrieval ─► ContextRelevance ─► Response ─► Faithfulness ─► answer
             │ blocked                  │ no relevant                         │ failed
             └──────────────────────────┴─────────────────────────────────────┴────► Fallback
```

Every stage is a Microsoft Agent Framework `Executor` node. Planner, Response,
and the graders are LLM agents; Retrieval is a deliberately deterministic
Executor — the Planner already emits structured search steps, so an LLM there
would add latency and nondeterminism without extra reasoning. The three required
agents (Planner → Retrieval → Response) are all present and communicate through
typed Pydantic messages.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design, security, scalability and
governance discussion. Sample outputs live in [evaluation/results/](evaluation/results/).

## Dataset

The assessment suggests the Hugging Face `AYI-NEDJIMI/nist-csf-en` dataset, but it
contains fewer than 110 records while the assessment requires **≥ 500 ingested
records**. This project therefore uses the **NIST SP 800-53 Rev 5 control catalog**
(the canonical superset that NIST CSF maps to), fetched as official OSCAL JSON from
[usnistgov/oscal-content](https://github.com/usnistgov/oscal-content). After excluding
withdrawn controls, **1,014 records** (controls + enhancements, 20 families) are
ingested, each with a title, description and category as required.

## Prerequisites

- Python 3.10+
- An Azure subscription
- Azure CLI (`brew install azure-cli`) for scripted provisioning (or use the portal)

## Setup

### 1. Provision Azure resources

```bash
az login
./scripts/provision.sh          # creates: resource group, Azure OpenAI
                                # (gpt-5-mini + text-embedding-3-small), Azure AI Search
```

The script prints the endpoint/key values to put in `.env`. Portal alternative: create
an Azure OpenAI resource with the two deployments above and an Azure AI
Search service, then copy the endpoints and keys.

> **Semantic search is enabled by default.** Provisioning creates a Basic Azure AI
> Search service with the semantic ranker's free usage plan (1,000 semantic queries
> per month), and `.env.example` sets `USE_SEMANTIC_RANKER=true`. Each planner step
> runs a hybrid BM25 + vector query, and Azure applies its L2 semantic reranker to
> that initial result set. Set `SEMANTIC_SEARCH_PLAN=standard` only if pay-as-you-go
> semantic queries are needed beyond the monthly free allowance. If semantic ranking
> is unavailable, the search client logs the condition and retries as plain hybrid
> search; set `USE_SEMANTIC_RANKER=false` to select that mode explicitly.

### 2. Install and configure

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env            # fill in the values printed by provision.sh
```

`.env.example` is a template only. Real Azure credentials stay in local
`.env`, which is gitignored and must not be committed.

### 3. Ingest the dataset

```bash
policy-qa ingest
# Ingested 1014 records into index 'security-policies'.
```

## Usage

All runtime commands load configuration from `.env`. Run `policy-qa --help` or
`policy-qa <command> --help` for the generated Typer help.

### Ask one question

```bash
policy-qa ask "What controls apply to API security?"
```

By default, `ask` prints a human-readable answer with citations, grounding
status, confidence, latency, and available quality scores. Add `--json` to print
the complete query trace instead:

```bash
policy-qa ask "Summarise the requirements for access control" --json
```

### Interactive session

Both forms below start a session that reuses the same Azure clients across
questions. Enter `exit`, `quit`, or `q` to stop.

```bash
policy-qa
# equivalent to:
policy-qa interactive
```

### Ingest and evaluate

```bash
policy-qa ingest      # download, transform, embed, and upload the NIST catalog
policy-qa evaluate    # run evaluation/test_queries.json and rewrite evaluation/results/
```

### Interviewer handoff

Do not share a live `.env` from your personal subscription in the repository or
in email. The intended handoff bundle is:

- source code
- `README.md`
- `.env.example`
- `ARCHITECTURE.md`
- committed sample outputs in `evaluation/results/`

If the reviewer needs to run the system end to end, use one of these options:

- best: ask them to create their own Azure resources and fill in `.env` from the template
- acceptable: provide short-lived, least-privilege credentials for a disposable assessment resource group, then rotate or delete them after review

Do not share production credentials, owner-level subscription access, or any
non-expiring personal secrets.

Human-readable `ask` output (abridged):

```
================================================================================
POLICY AI SEARCH ASSISTANT
================================================================================
User Query : What controls apply to API security?
Status     : SUCCESS
--------------------------------------------------------------------------------

ANSWER:

Controls from the provided set that apply to API security (supported aspects only):
- Protect API traffic confidentiality and integrity with cryptography ... (SC-8(1)).
- Log, review, and analyze API-related audit activity ... (AU-6).
- Apply least privilege to API access, components, and interfaces ...
  (AC-6, SA-8(14), SA-17(7)).

--------------------------------------------------------------------------------
📊 RETRIEVAL & GROUNDING TELEMETRY
--------------------------------------------------------------------------------
[+] Source Citations : SC-8(1), AU-6, AC-6, SA-8(14), SA-17(7)
[+] Grounding Status : VERIFIED (Grounded: True)
[+] Confidence Level : HIGH
[+] Latency Profile  : 45,347 ms
[+] Quality Metrics  :
    - Context Relevance : 0.94 (avg graded relevance)
    - Faithfulness Score: 1.00 (higher is more grounded)
```

This abridged example uses content and metrics from the committed evaluation
run, formatted as the CLI presents them. Latency and model wording can vary with
Azure model capacity.

Structured JSON logs are written to `logs/policy-qa.jsonl` by default, one line per
agent hop and tagged with a per-query correlation ID. This keeps CLI output clean while
retaining the required input/output audit trail:

```bash
tail -f logs/policy-qa.jsonl
```

Set `LOG_TO_CONSOLE=true` to also emit the same JSON logs to stderr.

### Prompt-injection defence

The project handles both direct and indirect prompt injection. The first
moderation node rejects user attempts to override or extract system instructions
before planning or search runs. Retrieved index text is also treated as untrusted:
one shared builder XML-escapes every field, encloses each result in a numbered
`<document>` boundary, and labels the block as reference data. The responder and
grading prompts explicitly prohibit following instructions inside those boundaries.
Escaping prevents a malicious indexed value from closing its boundary and becoming
an apparent instruction. Azure OpenAI's platform content filter remains an
additional layer, and focused tests exercise tag and attribute breakout payloads.

### Quality gates

Thresholds are environment-tunable. Azure's semantic reranker uses its native
0–4 score; the LLM graders use 0–1 scores.

| Variable | Default | Scale | Gate |
|---|---:|---:|---|
| `RERANKER_THRESHOLD` | 1.5 | 0–4 | when semantic scores are present, no result at or above this value short-circuits context grading |
| `CONTEXT_RELEVANCE_SCORE_THRESHOLD` | 0.5 | 0–1 | documents graded below this value are dropped; none left → safe fallback |
| `FAITHFULNESS_SCORE_THRESHOLD` | 0.7 | 0–1 | an answer below this value is withheld → safe fallback |

## Evaluation

`policy-qa evaluate` runs the five test queries in
[evaluation/test_queries.json](evaluation/test_queries.json) — the four use-case
queries from the assessment plus one out-of-scope query that must trigger the safe
fallback. Each query is scored by:

1. **Deterministic checks** — citation validity (citations ⊆ retrieved controls) and
   answer/evidence token overlap.
2. **LLM judge** (fixed structured rubric) — retrieval relevance and
   groundedness, 1–5.

Committed results: [evaluation/results/report.md](evaluation/results/report.md).

## Tests

```bash
pytest        # OSCAL transform (≥500 records, schema completeness), contracts,
              # fallback paths, and every conditional edge in the graph (test_routing.py)
```

## Project layout

```
src/policy_qa/
├── config.py                     # env-var configuration, fail-fast validation
├── utils/                        # dependency-free helpers usable by any layer
│   ├── logging_setup.py          # structured JSON logging + correlation ids
│   ├── text.py                   # tokenizing, control-id normalization,
│   │                             # prompt-injection escaping
│   └── retry.py                  # shared transient-error retry policy (tenacity)
├── schemas/                      # typed inter-agent contracts, split by domain
│   ├── records.py                # PolicyRecord (index document shape)
│   ├── planning.py               # QueryIntent, SearchStep, QueryPlan
│   ├── retrieval.py              # RetrievedDocument, RetrievalResult, RerankedContext
│   ├── answers.py                # FinalAnswer, DraftAnswer, safe-fallback factories
│   ├── grading.py                # relevance/faithfulness grades, JudgeScore
│   └── moderation.py             # moderation verdict + edge message
├── ingestion/
│   ├── catalog_download.py       # fetch + cache the OSCAL 800-53 catalog
│   ├── catalog_transform.py      # OSCAL JSON → flat policy records
│   └── pipeline.py               # create index, embed, upload (≥500 gate)
├── search/
│   ├── index_schema.py           # Azure AI Search index definition
│   ├── embeddings.py             # Azure OpenAI query/document embeddings
│   └── search_service.py         # hybrid search + semantic reranker integration
├── agents/                       # one workflow node per module
│   ├── agent_factory.py          # agent construction, deterministic options
│   ├── prompt_blocks.py          # shared prompt blocks with injection defence
│   ├── moderation.py             # content moderation gate (first node)
│   ├── planner.py                # Planner Agent executor
│   ├── retrieval.py              # deterministic, concurrent Retrieval Agent executor
│   ├── relevance_grader.py       # LLM context relevance reranker (batched)
│   ├── responder.py              # Response Agent executor
│   ├── faithfulness_grader.py    # single faithfulness quality gate
│   ├── meta_knowledge.py         # deterministic self-description, no LLM call
│   └── safe_fallback.py          # reason-specific safe answers, no LLM call
├── prompts/                      # versioned prompt files, one per agent/grader
├── graph.py                      # workflow topology: gates, quality loops, edges
├── orchestrator.py               # runtime facade: clients, error guard, tracing
├── tracing.py                    # typed per-run state + per-query trace record
├── evaluator.py                  # eval harness (deterministic + LLM judge)
├── report.py                     # human-readable CLI report formatting
└── cli.py                        # policy-qa ingest | ask | interactive | evaluate
```

## Costs and teardown

The Basic Search service is billable while provisioned; model and embedding usage
for the sample evaluation is small. When finished:

```bash
./scripts/teardown.sh
```

## Limitations

- gpt-5-family reasoning models fix `temperature`/`top_p`; pinned deployments,
  structured outputs and exact
  retrieval improve stability, but responses are not bit-identical.
- gpt-4o-mini / gpt-4.1-mini were blocked for new deployments ("deprecating state")
  at build time, hence gpt-5-mini; the model is swappable via one env var.
- Semantic ranking uses the service's 1,000-query monthly free allowance by default;
  sustained usage requires the `standard` semantic billing plan.
- The corpus is a public catalog standing in for private enterprise policy; swapping
  the ingestion module is the only change needed for a different corpus.

## Future work

- Add a dedicated conversational route for greetings, follow-up questions and
  limited policy-related chit-chat, while keeping factual policy answers grounded
  in retrieved evidence.
- Build a labelled query-to-control relevance dataset and tune the semantic
  reranker, context-relevance and faithfulness thresholds against precision,
  recall and fallback rates instead of relying on manually selected defaults.
- Introduce Corrective RAG (CRAG): assess retrieval quality, rewrite weak queries,
  retry retrieval and use a controlled secondary source before returning the safe
  fallback.
- Improve retrieval with policy-aware query expansion, control-family filters and
  offline comparison of hybrid, semantic and vector-only search configurations.
- Add multi-turn session context with explicit limits so follow-up questions can
  resolve prior references without allowing conversation history to override
  system instructions or retrieved policy text.
- Use a separate model or human-reviewed benchmark for evaluation to reduce
  self-grading bias, and track quality, latency and cost regressions in CI.
- Add an authenticated API layer, container deployment, managed identity,
  telemetry dashboards and automated deployment checks for production operation.
