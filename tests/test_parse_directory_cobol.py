"""parse_directory appends COBOL ParseResults from CobolParser. No JVM."""
from __future__ import annotations

from pathlib import Path

from code_context_graph import parser as parser_mod
from code_context_graph.models import EntityKind, ParseResult, CodeEntity
from code_context_graph.parser import parse_directory


def test_parse_directory_includes_cobol(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("def f():\n    return 1\n")
    (tmp_path / "PAY.cbl").write_text("       IDENTIFICATION DIVISION.\n")

    fake_result = ParseResult(
        file_path="PAY.cbl",
        entities=[CodeEntity(kind=EntityKind.PROGRAM, qualified_name="PAY",
                             simple_name="PAY", file_path="PAY.cbl",
                             start_line=1, end_line=1)],
        relationships=[],
    )

    class FakeCobolParser:
        def __init__(self, *a, **k): pass
        def parse_repo(self): return [fake_result]

    monkeypatch.setattr(parser_mod.CobolParser, "from_env",
                        classmethod(lambda cls, root: FakeCobolParser()))

    results = parse_directory(tmp_path)
    kinds = {e.kind for r in results for e in r.entities}
    assert EntityKind.PROGRAM in kinds        # COBOL appended
    assert any(r.file_path.endswith("app.py") for r in results)  # python still parsed
