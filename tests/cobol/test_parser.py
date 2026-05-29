"""CobolParser discovery, config, and graceful absence. No JVM."""
from __future__ import annotations

import logging
from pathlib import Path

from code_context_graph.cobol import CobolParser, COBOL_EXTENSIONS


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "A.cbl").write_text("       IDENTIFICATION DIVISION.\n")
    (tmp_path / "src" / "COPYBK.cpy").write_text("       01 WS-X PIC 9.\n")
    (tmp_path / "src" / "ignore.py").write_text("x = 1\n")
    return tmp_path


def test_extensions_cover_cobol():
    assert {".cbl", ".cob", ".cpy"} <= COBOL_EXTENSIONS


def test_discover_files_finds_only_cobol(tmp_path):
    repo = _make_repo(tmp_path)
    parser = CobolParser(repo, jar_path=None)
    found = {p.name for p in parser.discover_files()}
    assert found == {"A.cbl", "COPYBK.cpy"}


def test_discover_files_skips_hidden_and_vendor_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "GOOD.cbl").write_text("       IDENTIFICATION DIVISION.\n")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "SKIP.cbl").write_text("x\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "VENDOR.cbl").write_text("x\n")
    parser = CobolParser(tmp_path, jar_path=None)
    found = {p.name for p in parser.discover_files()}
    assert found == {"GOOD.cbl"}


def test_parse_repo_returns_empty_when_no_cobol(tmp_path):
    (tmp_path / "only.py").write_text("x = 1\n")
    parser = CobolParser(tmp_path, jar_path="/nonexistent.jar")
    assert parser.parse_repo() == []


def test_parse_repo_skips_gracefully_when_jar_missing(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="code_context_graph.cobol.parser")
    repo = _make_repo(tmp_path)
    parser = CobolParser(repo, jar_path="/nonexistent/ccg-cobol-extractor.jar")
    assert parser.parse_repo() == []  # COBOL present but no JAR -> skip, no raise
    assert any("extractor" in rec.message.lower() for rec in caplog.records)


def test_java_executable_prefers_java_home(tmp_path):
    jdk = tmp_path / "jdk"
    (jdk / "bin").mkdir(parents=True)
    java_bin = jdk / "bin" / "java"
    java_bin.write_text("")  # existence is enough
    parser = CobolParser(tmp_path, jar_path=None, java_home=str(jdk))
    assert parser._java_executable() == str(java_bin)


def test_java_executable_falls_back_to_path(tmp_path):
    parser = CobolParser(tmp_path, jar_path=None, java_home="/no/such/jdk")
    assert parser._java_executable() == "java"


def test_parse_repo_skips_gracefully_when_java_unavailable(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="code_context_graph.cobol.parser")
    (tmp_path / "A.cbl").write_text("       IDENTIFICATION DIVISION.\n")
    jar = tmp_path / "extractor.jar"
    jar.write_text("")  # jar exists, so we get past the jar check
    parser = CobolParser(tmp_path, jar_path=str(jar))
    monkeypatch.setattr(CobolParser, "_java_works", staticmethod(lambda java: False))
    assert parser.parse_repo() == []  # JAR present but no working Java -> skip, no raise
    assert any("java" in rec.message.lower() for rec in caplog.records)
