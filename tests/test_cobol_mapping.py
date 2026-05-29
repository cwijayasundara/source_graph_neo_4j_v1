"""COBOL JSON contract -> ParseResult mapping. Pure, no JVM, no Neo4j."""
from __future__ import annotations

import pytest

from code_context_graph.cobol_parser import (
    SUPPORTED_SCHEMA_VERSION,
    cobol_json_to_parse_results,
)
from code_context_graph.models import EntityKind, RelKind


def _payload(files):
    return {"schemaVersion": SUPPORTED_SCHEMA_VERSION, "files": files}


def test_maps_program_and_contains():
    payload = _payload([{
        "filePath": "src/PAYROLL.cbl",
        "parseStatus": "ok",
        "error": None,
        "entities": [
            {"kind": "Program", "qualifiedName": "PAYROLL", "simpleName": "PAYROLL",
             "filePath": "src/PAYROLL.cbl", "startLine": 1, "endLine": 420, "isExternal": False},
            {"kind": "Paragraph", "qualifiedName": "PAYROLL.MAIN", "simpleName": "MAIN",
             "filePath": "src/PAYROLL.cbl", "startLine": 30, "endLine": 60, "isExternal": False},
        ],
        "relationships": [
            {"sourceQname": "PAYROLL", "targetQname": "PAYROLL.MAIN", "kind": "CONTAINS",
             "filePath": "src/PAYROLL.cbl", "line": 30, "metadata": {}},
        ],
    }])
    results = cobol_json_to_parse_results(payload)
    assert len(results) == 1
    r = results[0]
    assert r.file_path == "src/PAYROLL.cbl"
    prog = next(e for e in r.entities if e.qualified_name == "PAYROLL")
    assert prog.kind is EntityKind.PROGRAM
    assert r.relationships[0].kind is RelKind.CONTAINS


def test_maps_external_stub_and_call_metadata():
    payload = _payload([{
        "filePath": "src/A.cbl", "parseStatus": "ok", "error": None,
        "entities": [
            {"kind": "Program", "qualifiedName": "A", "simpleName": "A",
             "filePath": "src/A.cbl", "startLine": 1, "endLine": 9, "isExternal": False},
            {"kind": "Program", "qualifiedName": "EXTSUB", "simpleName": "EXTSUB",
             "filePath": "", "startLine": 0, "endLine": 0, "isExternal": True},
        ],
        "relationships": [
            {"sourceQname": "A", "targetQname": "EXTSUB", "kind": "CALLS",
             "filePath": "src/A.cbl", "line": 5, "metadata": {"type": "call"}},
        ],
    }])
    results = cobol_json_to_parse_results(payload)
    stub = next(e for e in results[0].entities if e.qualified_name == "EXTSUB")
    assert stub.is_external is True
    assert results[0].relationships[0].metadata == {"type": "call"}


def test_error_file_yields_empty_entities():
    payload = _payload([{
        "filePath": "src/BAD.cbl", "parseStatus": "error",
        "error": "syntax error at line 12", "entities": [], "relationships": [],
    }])
    results = cobol_json_to_parse_results(payload)
    assert results[0].entities == []
    assert results[0].relationships == []
    assert results[0].file_path == "src/BAD.cbl"


def test_empty_files_payload_returns_empty_list():
    assert cobol_json_to_parse_results(_payload([])) == []


def test_schema_version_mismatch_raises():
    with pytest.raises(ValueError, match="schemaVersion"):
        cobol_json_to_parse_results({"schemaVersion": 999, "files": []})
