"""parse_directory appends repo-extractor (e.g. COBOL) results. No JVM."""
from __future__ import annotations

from pathlib import Path

import code_context_graph.parser as parser_mod
from code_context_graph.models import CodeEntity, EntityKind, ParseResult
from code_context_graph.parser import parse_directory


def test_parse_directory_includes_repo_extractor_results(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("def f():\n    return 1\n")

    fake = ParseResult(
        file_path="PAY.cbl",
        entities=[CodeEntity(kind=EntityKind.PROGRAM, qualified_name="PAY",
                             simple_name="PAY", file_path="PAY.cbl",
                             start_line=1, end_line=1)],
        relationships=[],
    )
    # parser.py calls run_repo_extractors(repo_root); stub it at that seam.
    monkeypatch.setattr(parser_mod, "run_repo_extractors", lambda root: [fake])

    results = parse_directory(tmp_path)
    kinds = {e.kind for r in results for e in r.entities}
    assert EntityKind.PROGRAM in kinds
    assert any(r.file_path.endswith("app.py") for r in results)
