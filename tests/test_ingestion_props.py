"""_load_entity prop-building — runs without Neo4j via a fake client."""
from __future__ import annotations

from pathlib import Path

from code_context_graph.ingestion import CodeGraphIngester
from code_context_graph.models import CodeEntity, EntityKind


class FakeClient:
    def __init__(self):
        self.entities = []

    def merge_entity(self, qualified_name, label, props):
        self.entities.append((qualified_name, label, props))


def test_load_entity_includes_is_external():
    client = FakeClient()
    ingester = CodeGraphIngester(client, Path("."))
    ingester._load_entity(CodeEntity(
        kind=EntityKind.PROGRAM, qualified_name="EXTSUB", simple_name="EXTSUB",
        file_path="", start_line=0, end_line=0, is_external=True,
    ))
    _, label, props = client.entities[0]
    assert label == "Program"
    assert props["is_external"] is True
