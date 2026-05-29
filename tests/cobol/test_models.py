"""COBOL additions to the shared data model — runs without Neo4j."""
from __future__ import annotations

from code_context_graph.models import CodeEntity, EntityKind


def test_cobol_entity_kinds_exist():
    assert EntityKind.PROGRAM.value == "Program"
    assert EntityKind.SECTION.value == "Section"
    assert EntityKind.PARAGRAPH.value == "Paragraph"
    assert EntityKind.COPYBOOK.value == "Copybook"


def test_entity_is_external_defaults_false():
    e = CodeEntity(
        kind=EntityKind.PROGRAM,
        qualified_name="PAYROLL",
        simple_name="PAYROLL",
        file_path="src/PAYROLL.cbl",
        start_line=1,
        end_line=10,
    )
    assert e.is_external is False


def test_entity_is_external_settable():
    e = CodeEntity(
        kind=EntityKind.PROGRAM,
        qualified_name="EXTSUB",
        simple_name="EXTSUB",
        file_path="",
        start_line=0,
        end_line=0,
        is_external=True,
    )
    assert e.is_external is True
