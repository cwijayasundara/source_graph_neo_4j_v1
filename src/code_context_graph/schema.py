from __future__ import annotations

CONSTRAINTS = [
    "CREATE CONSTRAINT entity_qname IF NOT EXISTS FOR (e:CodeEntity) REQUIRE e.qualified_name IS UNIQUE",
    "CREATE CONSTRAINT file_path IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE",
    "CREATE CONSTRAINT author_email IF NOT EXISTS FOR (a:Author) REQUIRE a.email IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX entity_kind IF NOT EXISTS FOR (e:CodeEntity) ON (e.kind)",
    "CREATE INDEX entity_file IF NOT EXISTS FOR (e:CodeEntity) ON (e.file_path)",
    "CREATE INDEX entity_name IF NOT EXISTS FOR (e:CodeEntity) ON (e.simple_name)",
    "CREATE FULLTEXT INDEX entity_search IF NOT EXISTS FOR (e:CodeEntity) ON EACH [e.simple_name, e.qualified_name, e.docstring]",
]

CLEAR_GRAPH = "MATCH (n) DETACH DELETE n"

MERGE_ENTITY = """
MERGE (e:CodeEntity {qualified_name: $qualified_name})
SET e += $props,
    e:%(label)s
"""

MERGE_FILE = """
MERGE (f:File {path: $path})
SET f.line_count = $line_count
"""

MERGE_RELATIONSHIP = """
MATCH (src:CodeEntity {qualified_name: $source_qname})
MATCH (tgt:CodeEntity {qualified_name: $target_qname})
MERGE (src)-[r:%(rel_type)s]->(tgt)
SET r += $props
"""

MERGE_RELATIONSHIP_TO_UNRESOLVED = """
MATCH (src:CodeEntity {qualified_name: $source_qname})
MERGE (tgt:CodeEntity {qualified_name: $target_qname})
ON CREATE SET tgt.kind = 'External', tgt:External
MERGE (src)-[r:%(rel_type)s]->(tgt)
SET r += $props
"""

MERGE_AUTHOR = """
MERGE (a:Author {email: $email})
SET a.name = $name,
    a.commit_count = $commit_count
"""

MERGE_AUTHORED_BY = """
MATCH (e:CodeEntity {file_path: $file_path})
MATCH (a:Author {email: $email})
WHERE e.kind IN ['Module', 'File']
MERGE (e)-[r:AUTHORED_BY]->(a)
SET r.rank = $rank
"""

MERGE_CO_CHANGE = """
MATCH (a:CodeEntity {qualified_name: $qname_a})
MATCH (b:CodeEntity {qualified_name: $qname_b})
WHERE a.kind = 'Module' AND b.kind = 'Module'
MERGE (a)-[r:CO_CHANGED_WITH]-(b)
SET r.times = $times,
    r.confidence = $confidence
"""
