"""_run_extractor builds the right command and parses stdout. No real JVM."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from code_context_graph.cobol import CobolParser, SUPPORTED_SCHEMA_VERSION


def test_run_extractor_builds_command_and_parses(tmp_path, monkeypatch):
    jar = tmp_path / "ccg-cobol-extractor.jar"
    jar.write_text("")  # existence check only
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        payload = {"schemaVersion": SUPPORTED_SCHEMA_VERSION, "files": []}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    parser = CobolParser(
        tmp_path, jar_path=str(jar),
        copybook_dirs=(str(tmp_path / "cpy"),), source_format="FIXED",
    )
    payload = parser._run_extractor()

    assert payload["schemaVersion"] == SUPPORTED_SCHEMA_VERSION
    cmd = captured["cmd"]
    assert cmd[0] == "java" and "-jar" in cmd and str(jar) in cmd
    assert "--source-dir" in cmd and str(tmp_path) in cmd
    assert "--format" in cmd and "FIXED" in cmd
    assert "--copybook-dir" in cmd and str(tmp_path / "cpy") in cmd


def test_run_extractor_raises_on_nonzero(tmp_path, monkeypatch):
    jar = tmp_path / "x.jar"
    jar.write_text("")

    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(2, cmd, output="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    parser = CobolParser(tmp_path, jar_path=str(jar))
    with pytest.raises(RuntimeError, match="boom"):
        parser._run_extractor()


def test_run_extractor_raises_on_invalid_json(tmp_path, monkeypatch):
    jar = tmp_path / "x.jar"
    jar.write_text("")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="not json{", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    parser = CobolParser(tmp_path, jar_path=str(jar))
    with pytest.raises(RuntimeError, match="invalid JSON"):
        parser._run_extractor()


def test_run_extractor_raises_on_timeout(tmp_path, monkeypatch):
    jar = tmp_path / "x.jar"
    jar.write_text("")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, timeout=1, output="", stderr="partial")

    monkeypatch.setattr(subprocess, "run", fake_run)
    parser = CobolParser(tmp_path, jar_path=str(jar), timeout=1)
    with pytest.raises(RuntimeError, match="timed out"):
        parser._run_extractor()
