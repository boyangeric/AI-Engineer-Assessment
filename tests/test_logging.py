"""Structured logging should be auditable without polluting CLI output."""

import json
import logging

from policy_qa.utils.logging_setup import log_event, setup_logging


def test_structured_logs_go_to_file_without_console_noise(tmp_path, capsys):
    log_path = tmp_path / "policy-qa.jsonl"
    setup_logging("INFO", log_file=log_path, log_to_console=False)

    log_event(logging.getLogger("policy_qa.test"), "stage complete", input="q", output="a")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert capsys.readouterr().err == ""
    record = json.loads(log_path.read_text().strip())
    assert record["message"] == "stage complete"
    assert record["input"] == "q"
    assert record["output"] == "a"
