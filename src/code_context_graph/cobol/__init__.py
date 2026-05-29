"""COBOL language support (isolated sub-package).

Importing this package registers the COBOL repo-level extractor with the
language registry. Re-exports the public API so callers can do
``from code_context_graph.cobol import CobolParser``."""
from __future__ import annotations

from pathlib import Path

from code_context_graph.cobol.mapping import (
    SUPPORTED_SCHEMA_VERSION,
    cobol_json_to_parse_results,
)
from code_context_graph.cobol.parser import COBOL_EXTENSIONS, CobolParser
from code_context_graph.language_registry import register_repo_extractor
from code_context_graph.models import ParseResult

__all__ = [
    "CobolParser",
    "COBOL_EXTENSIONS",
    "cobol_json_to_parse_results",
    "SUPPORTED_SCHEMA_VERSION",
]


def _cobol_repo_extractor(repo_root: Path) -> list[ParseResult]:
    return CobolParser.from_env(repo_root).parse_repo()


register_repo_extractor(_cobol_repo_extractor)
