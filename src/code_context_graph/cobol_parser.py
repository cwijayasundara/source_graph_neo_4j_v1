"""COBOL support: maps the ccg-cobol-extractor JSON contract into ParseResults.
The JSON contract is the only coupling surface with the Java extractor.
(The subprocess driver that produces this JSON is added in a later task.)"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from code_context_graph.models import (
    CodeEntity,
    CodeRelationship,
    EntityKind,
    ParseResult,
    RelKind,
)

SUPPORTED_SCHEMA_VERSION: int = 1


def _entity_from_json(d: dict) -> CodeEntity:
    return CodeEntity(
        kind=EntityKind(d["kind"]),
        qualified_name=d["qualifiedName"],
        simple_name=d["simpleName"],
        file_path=d.get("filePath", ""),
        start_line=d.get("startLine", 0),
        end_line=d.get("endLine", 0),
        is_external=d.get("isExternal", False),
    )


def _relationship_from_json(d: dict) -> CodeRelationship:
    return CodeRelationship(
        source_qname=d["sourceQname"],
        target_qname=d["targetQname"],
        kind=RelKind(d["kind"]),
        file_path=d.get("filePath"),
        line=d.get("line"),
        metadata=d.get("metadata") or {},
    )


def cobol_json_to_parse_results(payload: dict) -> list[ParseResult]:
    version = payload.get("schemaVersion")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported COBOL extractor schemaVersion {version!r}; "
            f"expected {SUPPORTED_SCHEMA_VERSION}"
        )
    results: list[ParseResult] = []
    for f in payload.get("files", []):
        results.append(ParseResult(
            file_path=f["filePath"],
            entities=[_entity_from_json(e) for e in f.get("entities", [])],
            relationships=[_relationship_from_json(r) for r in f.get("relationships", [])],
        ))
    return results


logger = logging.getLogger(__name__)

COBOL_EXTENSIONS = {".cbl", ".cob", ".cobol", ".cpy"}
_SKIP_PARTS = {".git", "node_modules", "__pycache__", "venv", ".venv"}


class CobolParser:
    """Drives the ccg-cobol-extractor JAR over a repo and maps its JSON output."""

    def __init__(
        self,
        repo_root: Path,
        *,
        jar_path: str | None,
        copybook_dirs: tuple[str, ...] = (),
        source_format: str = "FIXED",
        timeout: int = 600,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.jar_path = jar_path
        self.copybook_dirs = copybook_dirs
        self.source_format = source_format
        self.timeout = timeout

    @classmethod
    def from_env(cls, repo_root: Path) -> "CobolParser":
        copy_raw = os.getenv("CCG_COBOL_COPYBOOK_DIRS", "")
        copybook_dirs = tuple(d for d in (s.strip() for s in copy_raw.split(",")) if d)
        return cls(
            repo_root,
            jar_path=os.getenv("CCG_COBOL_EXTRACTOR_JAR"),
            copybook_dirs=copybook_dirs,
            source_format=os.getenv("CCG_COBOL_FORMAT", "FIXED"),
        )

    def discover_files(self) -> list[Path]:
        out: list[Path] = []
        for p in sorted(self.repo_root.rglob("*")):
            if p.suffix.lower() not in COBOL_EXTENSIONS:
                continue
            dir_parts = p.relative_to(self.repo_root).parts[:-1]  # exclude filename
            if any(part in _SKIP_PARTS or part.startswith(".") for part in dir_parts):
                continue
            out.append(p)
        return out

    def parse_repo(self) -> list[ParseResult]:
        files = self.discover_files()
        if not files:
            return []
        if not self.jar_path or not Path(self.jar_path).exists():
            logger.warning(
                "Found %d COBOL file(s) but the COBOL extractor JAR is unavailable "
                "(CCG_COBOL_EXTRACTOR_JAR=%r). Skipping COBOL.",
                len(files), self.jar_path,
            )
            return []
        payload = self._run_extractor()
        results = cobol_json_to_parse_results(payload)
        for f in payload.get("files", []):
            if f.get("parseStatus") == "error":
                logger.warning("COBOL parse error in %s: %s", f.get("filePath"), f.get("error"))
        return results
