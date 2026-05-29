"""End-to-end COBOL extraction through the real JAR. Skips cleanly without JVM/JAR.

This exercises the full Python -> ccg-cobol-extractor.jar -> JSON -> ParseResult
contract against the real ProLeap-based extractor. It is gated so the default test
run (no JVM on PATH, or JAR not built) skips it rather than failing.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from code_context_graph.cobol import CobolParser

JAR = os.getenv(
    "CCG_COBOL_EXTRACTOR_JAR",
    "tools/cobol-extractor/target/ccg-cobol-extractor.jar",
)


def _java_works() -> bool:
    """True only if a JVM can actually run. On macOS ``/usr/bin/java`` is a stub
    that exists even with no JDK installed, so checking PATH alone is not enough —
    we must confirm ``java -version`` succeeds."""
    java = shutil.which("java")
    if not java:
        return False
    try:
        return subprocess.run(
            [java, "-version"], capture_output=True, timeout=30
        ).returncode == 0
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _java_works(), reason="no working JVM"),
    pytest.mark.skipif(not Path(JAR).exists(), reason="extractor JAR not built"),
]


def test_cross_program_call_resolves_and_missing_is_external():
    repo = Path("tests/integration/fixtures/cobol")
    parser = CobolParser(repo, jar_path=JAR, source_format="FIXED")
    results = parser.parse_repo()

    entities = {e.qualified_name: e for r in results for e in r.entities}
    rels = [
        (rel.source_qname, rel.target_qname, rel.kind.value)
        for r in results
        for rel in r.relationships
    ]

    assert "CALLER" in entities and "CALLEE" in entities
    assert entities["CALLEE"].is_external is False  # resolved cross-file
    assert entities["MISSINGSUB"].is_external is True  # unresolved -> stub
    assert ("CALLER", "CALLEE", "CALLS") in rels
