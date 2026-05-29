"""Code Context Graph package.

Importing the package wires up optional language extractors (e.g. COBOL) into the
language registry so the core pipeline stays language-agnostic."""
from __future__ import annotations

from code_context_graph import cobol as _cobol  # noqa: F401  registers COBOL extractor
