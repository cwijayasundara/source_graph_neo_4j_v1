"""COBOL support: maps the ccg-cobol-extractor JSON contract into ParseResults.
The JSON contract is the only coupling surface with the Java extractor.
(The subprocess driver that produces this JSON is added in a later task.)"""
from __future__ import annotations

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
