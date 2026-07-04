"""Evaluation harness: relevance and grounding quality over the test queries.

Two graders per query:
1. Deterministic groundedness — are all citations really retrieved controls,
   and how much of the answer's vocabulary is covered by the cited evidence
   (token-overlap score)?
2. LLM-judge (same deployment, temperature 0, structured output) — 1-5 rubric
   for retrieval relevance and answer groundedness.

Results are written to evaluation/results/ as per-query JSON plus report.md.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from .agents.factory import make_agent, make_chat_client, parse_structured
from .config import PROJECT_ROOT, Settings
from .logging_setup import log_event
from .orchestrator import Orchestrator, QueryTrace
from .schemas import JudgeScore

logger = logging.getLogger(__name__)

QUERIES_PATH = PROJECT_ROOT / "evaluation" / "test_queries.json"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"

JUDGE_INSTRUCTIONS = """\
You are a strict evaluator of a retrieval-augmented security policy assistant.
You will receive: the user question, the retrieved security controls, and the
final answer. Score on a 1-5 scale:
- retrieval_relevance: how relevant the retrieved controls are to the question
  (5 = all directly relevant, 1 = unrelated).
- groundedness: how strictly the answer is supported by the retrieved controls
  (5 = every claim traceable to a control, 1 = mostly unsupported).
For a fallback answer ("could not find relevant information"), score groundedness 5
if declining was the correct behaviour for the question, otherwise 1.
Return a one-sentence justification.
"""

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def citation_overlap_score(trace: QueryTrace) -> dict[str, Any]:
    """Deterministic grounding signals for one query trace."""
    answer = trace.answer
    retrieved_ids = {
        d.control_id.upper() for d in (trace.retrieval.documents if trace.retrieval else [])
    }
    citations_valid = all(c.upper() in retrieved_ids for c in answer.citations)

    cited_docs = [
        d
        for d in (trace.retrieval.documents if trace.retrieval else [])
        if d.control_id.upper() in {c.upper() for c in answer.citations}
    ]
    evidence_tokens: set[str] = set()
    for doc in cited_docs:
        evidence_tokens |= _tokens(doc.title) | _tokens(doc.content)
    answer_tokens = _tokens(answer.answer)
    overlap = (
        len(answer_tokens & evidence_tokens) / len(answer_tokens) if answer_tokens else 0.0
    )
    return {
        "citations_valid": citations_valid,
        "num_citations": len(answer.citations),
        "token_overlap": round(overlap, 3),
    }


async def judge_trace(trace: QueryTrace, settings: Settings) -> JudgeScore:
    judge = make_agent(
        make_chat_client(settings),
        name="judge",
        instructions=JUDGE_INSTRUCTIONS,
        response_format=JudgeScore,
    )
    retrieved = (
        "\n".join(
            f"- {d.control_id} {d.title}: {d.content[:400]}"
            for d in trace.retrieval.documents
        )
        if trace.retrieval and trace.retrieval.documents
        else "(no documents retrieved)"
    )
    prompt = (
        f"Question: {trace.question}\n\nRetrieved controls:\n{retrieved}\n\n"
        f"Final answer:\n{trace.answer.answer}\n\nCitations: {trace.answer.citations}"
    )
    response = await judge.run(prompt)
    return parse_structured(response, JudgeScore)


async def run_evaluation(settings: Settings) -> Path:
    queries = json.loads(QUERIES_PATH.read_text())
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    orchestrator = Orchestrator(settings)

    rows: list[dict[str, Any]] = []
    for entry in queries:
        query = entry["query"]
        log_event(logger, "evaluating query", query=query)
        trace = await orchestrator.run_query(query)
        deterministic = citation_overlap_score(trace)
        judge = await judge_trace(trace, settings)

        record = {
            "query": query,
            "expect_fallback": entry.get("expect_fallback", False),
            "trace": trace.to_dict(),
            "deterministic_checks": deterministic,
            "llm_judge": judge.model_dump(),
        }
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:60]
        (RESULTS_DIR / f"{slug}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False)
        )
        rows.append(record)

    report_path = RESULTS_DIR / "report.md"
    report_path.write_text(_render_report(rows))
    return report_path


def _render_report(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Evaluation Report",
        "",
        "| Query | Grounded | Citations valid | Token overlap | Judge: relevance | Judge: groundedness |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        answer = r["trace"]["answer"]
        checks = r["deterministic_checks"]
        judge = r["llm_judge"]
        lines.append(
            f"| {r['query']} | {answer['grounded']} | {checks['citations_valid']} "
            f"| {checks['token_overlap']} | {judge['retrieval_relevance']}/5 "
            f"| {judge['groundedness']}/5 |"
        )
    lines += ["", "## Judge justifications", ""]
    for r in rows:
        lines.append(f"- **{r['query']}** — {r['llm_judge']['justification']}")
    lines.append("")
    return "\n".join(lines)
