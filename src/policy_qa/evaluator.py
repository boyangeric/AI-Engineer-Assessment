"""Evaluation harness: relevance and grounding quality over the test queries.

Two graders per query:
1. Deterministic groundedness — are all citations really retrieved controls,
   and how much of the answer's vocabulary is covered by the cited evidence
   (token-overlap score)?
2. LLM-judge (same pinned deployment and structured output contract) — 1-5
   rubric for retrieval relevance and answer groundedness.

Results are written to evaluation/results/ as per-query JSON plus report.md.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from .agents import build_chat_client, build_deterministic_agent, parse_structured
from .config import PROJECT_ROOT, Settings
from .utils.text import normalize_control_id, tokenize_words
from .utils.logging_setup import log_event
from .prompts import load_prompt
from .orchestrator import Orchestrator
from .tracing import QueryTrace
from .schemas import JudgeScore

logger = logging.getLogger(__name__)

QUERIES_PATH = PROJECT_ROOT / "evaluation" / "test_queries.json"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"


def compute_grounding_checks(trace: QueryTrace) -> dict[str, Any]:
    """Deterministic grounding signals for one query trace."""
    answer = trace.answer
    evidence = (
        trace.reranked.documents
        if trace.reranked
        else (trace.retrieval.documents if trace.retrieval else [])
    )
    retrieved_ids = {normalize_control_id(d.control_id) for d in evidence}
    cited_ids = {normalize_control_id(c) for c in answer.citations}
    citations_valid = cited_ids <= retrieved_ids if answer.citations else None

    cited_docs = [d for d in evidence if normalize_control_id(d.control_id) in cited_ids]
    evidence_tokens: set[str] = set()
    for doc in cited_docs:
        evidence_tokens |= tokenize_words(doc.title) | tokenize_words(doc.content)
    answer_tokens = tokenize_words(answer.answer)
    overlap = (
        len(answer_tokens & evidence_tokens) / len(answer_tokens) if answer_tokens else 0.0
    )
    return {
        "citations_valid": citations_valid,
        "num_citations": len(answer.citations),
        "token_overlap": round(overlap, 3),
        "grounded_answer_has_citations": not answer.grounded or bool(answer.citations),
    }


async def judge_trace(trace: QueryTrace, settings: Settings) -> JudgeScore:
    judge = build_deterministic_agent(
        build_chat_client(settings),
        settings,
        name="judge",
        instructions=load_prompt("judge"),
        response_format=JudgeScore,
    )
    retrieved = (
        "\n".join(
            f"- {d.control_id} {d.title}: {d.content[: settings.judge_evidence_chars]}"
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
    runner = Orchestrator(settings)

    rows: list[dict[str, Any]] = []
    for entry in queries:
        query = entry["query"]
        log_event(logger, "evaluating query", query=query)
        trace = await runner.run_query(query)
        deterministic = compute_grounding_checks(trace)
        judge = await judge_trace(trace, settings)
        expect_fallback = entry.get("expect_fallback", False)
        retrieved_documents = (
            trace.retrieval.documents if trace.retrieval is not None else []
        )

        record = {
            "query": query,
            "expect_fallback": expect_fallback,
            "retrieval_configuration": {
                "semantic_ranker_requested": settings.use_semantic_ranker,
                "semantic_ranker_exercised": any(
                    document.reranker_score is not None
                    for document in retrieved_documents
                ),
            },
            "outcome_correct": (
                trace.error is None
                and trace.answer.grounded == (not expect_fallback)
                and deterministic["grounded_answer_has_citations"]
                and deterministic["citations_valid"] is not False
            ),
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


def _grade_score(trace: dict[str, Any], stage: str, key: str) -> str:
    """Last in-pipeline grading score for the report, '-' when the stage never ran."""
    grades = trace.get(stage) or []
    return f"{grades[-1][key]:.2f}" if grades else "-"


def _render_report(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Evaluation Report",
        "",
        f"**Outcome checks passed: {sum(r['outcome_correct'] for r in rows)}/{len(rows)}**",
        "",
        "| Query | Semantic ranker exercised | Outcome correct | Grounded | Citations valid | Token overlap | Faithfulness | Judge: relevance | Judge: groundedness |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        trace = r["trace"]
        answer = trace["answer"]
        checks = r["deterministic_checks"]
        judge = r["llm_judge"]
        lines.append(
            f"| {r['query']} "
            f"| {r['retrieval_configuration']['semantic_ranker_exercised']} "
            f"| {r['outcome_correct']} | {answer['grounded']} "
            f"| {checks['citations_valid'] if checks['citations_valid'] is not None else 'N/A'} "
            f"| {checks['token_overlap']} "
            f"| {_grade_score(trace, 'faithfulness', 'faithfulness_score')} "
            f"| {judge['retrieval_relevance']}/5 "
            f"| {judge['groundedness']}/5 |"
        )
    lines += ["", "## Judge justifications", ""]
    for r in rows:
        lines.append(f"- **{r['query']}** — {r['llm_judge']['justification']}")
    lines.append("")
    return "\n".join(lines)
