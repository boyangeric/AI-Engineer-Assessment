"""Command-line interface: ingest | ask | evaluate."""

from __future__ import annotations

import asyncio
import json

import typer

from .config import Settings
from .logging_setup import setup_logging

app = typer.Typer(help="Multi-agent security policy Q&A on Azure AI.", no_args_is_help=True)


def _settings() -> Settings:
    settings = Settings.from_env()
    setup_logging(
        settings.log_level,
        log_file=settings.log_file,
        log_to_console=settings.log_to_console,
    )
    return settings


@app.command()
def ingest() -> None:
    """Download NIST SP 800-53 Rev 5, build the index and ingest all records."""
    from .ingestion.ingest import run_ingestion

    settings = _settings()
    count = run_ingestion(settings)
    typer.echo(f"Ingested {count} records into index '{settings.search_index_name}'.")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Security policy question"),
    json_output: bool = typer.Option(False, "--json", help="Print the full trace as JSON"),
) -> None:
    """Ask a question through the Planner -> Retrieval -> Response pipeline."""
    from .orchestrator import Orchestrator

    settings = _settings()
    trace = asyncio.run(Orchestrator(settings).run_query(question))

    if json_output:
        typer.echo(json.dumps(trace.to_dict(), indent=2, ensure_ascii=False))
        return

    typer.echo(f"\nQ: {trace.question}\n")
    if trace.retrieval:
        typer.echo("Retrieved controls:")
        for doc in trace.retrieval.documents:
            typer.echo(f"  - {doc.control_id}  {doc.title}  (similarity {doc.similarity:.2f})")
        typer.echo("")
    typer.echo(f"A: {trace.answer.answer}\n")
    typer.echo(f"Citations: {', '.join(trace.answer.citations) or '-'}")
    typer.echo(
        f"Grounded: {trace.answer.grounded} | Confidence: {trace.answer.confidence} "
        f"| {trace.duration_ms} ms"
    )


@app.command()
def evaluate() -> None:
    """Run the evaluation suite over the test queries and write a report."""
    from .evaluation import run_evaluation

    settings = _settings()
    report_path = asyncio.run(run_evaluation(settings))
    typer.echo(f"Evaluation complete. Report: {report_path}")


if __name__ == "__main__":
    app()
