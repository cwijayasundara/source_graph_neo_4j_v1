from __future__ import annotations

import json
from pathlib import Path

from code_context_graph.neo4j_client import Neo4jClient


ENRICHMENT_PROMPT = """\
You are a code analysis expert. Given the following code entity and its context,
provide semantic tags that describe its architectural role.

Entity: {qualified_name}
Kind: {kind}
Signature: {signature}
Docstring: {docstring}
File: {file_path}
Base classes: {base_classes}
Decorators: {decorators}

Respond with a JSON object containing:
- "patterns": list of design patterns this participates in (e.g., "Repository", "Factory", "Observer", "Strategy", "State Machine", "Builder")
- "layer": the architectural layer (e.g., "presentation", "business_logic", "data_access", "infrastructure", "orchestration", "domain_model")
- "concepts": list of domain concepts this represents (e.g., "log_parsing", "error_detection", "issue_management")
- "summary": one-sentence plain English description of what this does

Return ONLY valid JSON, no markdown fences.
"""


class SemanticEnricher:
    """Use an LLM to tag code entities with design patterns, architectural layers, and concepts."""

    def __init__(self, client: Neo4jClient, model: str = "gemini-3.5-flash") -> None:
        self.client = client
        self.model = model

    def enrich_all(self, limit: int = 50) -> int:
        entities = self.client.run(
            """
            MATCH (e:CodeEntity)
            WHERE e.kind IN ['Class', 'Function', 'Method', 'Module']
              AND e.semantic_layer IS NULL
            RETURN e.qualified_name AS qualified_name,
                   e.kind AS kind,
                   e.signature AS signature,
                   e.docstring AS docstring,
                   e.file_path AS file_path,
                   e.base_classes AS base_classes,
                   e.decorators AS decorators
            LIMIT $limit
            """,
            limit=limit,
        )

        if not entities:
            return 0

        from code_context_graph.gemini_llm import GeminiMessagesClient

        llm = GeminiMessagesClient()
        enriched = 0

        for entity in entities:
            prompt = ENRICHMENT_PROMPT.format(
                qualified_name=entity["qualified_name"],
                kind=entity["kind"],
                signature=entity.get("signature") or "N/A",
                docstring=entity.get("docstring") or "N/A",
                file_path=entity.get("file_path") or "N/A",
                base_classes=entity.get("base_classes") or "N/A",
                decorators=entity.get("decorators") or "N/A",
            )

            response = llm.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            try:
                tags = json.loads(text)
            except json.JSONDecodeError:
                continue

            self.client.run(
                """
                MATCH (e:CodeEntity {qualified_name: $qname})
                SET e.semantic_patterns = $patterns,
                    e.semantic_layer = $layer,
                    e.semantic_concepts = $concepts,
                    e.semantic_summary = $summary
                """,
                qname=entity["qualified_name"],
                patterns=tags.get("patterns", []),
                layer=tags.get("layer", "unknown"),
                concepts=tags.get("concepts", []),
                summary=tags.get("summary", ""),
            )
            enriched += 1

        return enriched
