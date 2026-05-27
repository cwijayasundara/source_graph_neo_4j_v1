from __future__ import annotations

from code_context_graph.neo4j_client import Neo4jClient


class CodeGraphQueries:
    """Pre-built Cypher queries for common code navigation questions."""

    def __init__(self, client: Neo4jClient) -> None:
        self.client = client

    @staticmethod
    def _repo_filter(alias: str, repo: str | None) -> str:
        return f"AND properties({alias}).repo = $repo" if repo else ""

    @staticmethod
    def _params(repo: str | None, **params: object) -> dict[str, object]:
        if repo:
            params["repo"] = repo
        return params

    def what_calls(self, function_name: str, repo: str | None = None) -> list[dict]:
        """Find all callers of a given function/method."""
        return self.client.run(
            f"""
            MATCH (caller:CodeEntity)-[:CALLS]->(target:CodeEntity)
            WHERE (target.simple_name = $name OR target.qualified_name = $name)
            {self._repo_filter("caller", repo)}
            RETURN caller.qualified_name AS caller,
                   caller.kind AS kind,
                   caller.file_path AS file
            ORDER BY caller.file_path
            """,
            **self._params(repo, name=function_name),
        )

    def what_does_it_call(self, function_name: str, repo: str | None = None) -> list[dict]:
        """Find all functions/methods called by a given function."""
        return self.client.run(
            f"""
            MATCH (caller:CodeEntity)-[:CALLS]->(callee:CodeEntity)
            WHERE (caller.simple_name = $name OR caller.qualified_name = $name)
            {self._repo_filter("caller", repo)}
            RETURN callee.qualified_name AS callee,
                   callee.kind AS kind,
                   callee.file_path AS file
            ORDER BY callee.qualified_name
            """,
            **self._params(repo, name=function_name),
        )

    def impact_analysis(self, entity_name: str, depth: int = 3, repo: str | None = None) -> list[dict]:
        """What breaks if I change this? Follow CALLS edges up to N hops."""
        return self.client.run(
            """
            MATCH path = (target:CodeEntity)<-[:CALLS*1..%(depth)d]-(affected:CodeEntity)
            WHERE (target.simple_name = $name OR target.qualified_name = $name)
            %(repo_filter)s
            RETURN DISTINCT affected.qualified_name AS affected,
                   affected.kind AS kind,
                   affected.file_path AS file,
                   length(path) AS distance
            ORDER BY distance, affected.file_path
            """ % {"depth": depth, "repo_filter": self._repo_filter("affected", repo)},
            **self._params(repo, name=entity_name),
        )

    def class_hierarchy(self, class_name: str, repo: str | None = None) -> list[dict]:
        """Get the full inheritance tree for a class."""
        return self.client.run(
            f"""
            MATCH path = (child:CodeEntity)-[:INHERITS*1..5]->(parent:CodeEntity)
            WHERE (child.simple_name = $name OR child.qualified_name = $name)
            {self._repo_filter("child", repo)}
            RETURN [n IN nodes(path) | n.qualified_name] AS chain
            """,
            **self._params(repo, name=class_name),
        )

    def module_dependencies(self, module_name: str, repo: str | None = None) -> list[dict]:
        """What does this module import?"""
        return self.client.run(
            f"""
            MATCH (m:CodeEntity)-[:IMPORTS]->(dep:CodeEntity)
            WHERE (m.simple_name = $name OR m.qualified_name = $name)
            {self._repo_filter("m", repo)}
            RETURN dep.qualified_name AS dependency,
                   dep.kind AS kind
            ORDER BY dep.qualified_name
            """,
            **self._params(repo, name=module_name),
        )

    def who_imports_this(self, module_name: str, repo: str | None = None) -> list[dict]:
        """What modules import this one?"""
        return self.client.run(
            f"""
            MATCH (importer:CodeEntity)-[:IMPORTS]->(target:CodeEntity)
            WHERE (target.simple_name = $name
               OR target.qualified_name = $name
               OR target.qualified_name STARTS WITH $name)
            {self._repo_filter("importer", repo)}
            RETURN DISTINCT importer.qualified_name AS importer,
                   importer.file_path AS file
            ORDER BY importer.file_path
            """,
            **self._params(repo, name=module_name),
        )

    def full_request_path(self, entry_point: str, repo: str | None = None) -> list[dict]:
        """Trace the call chain from an entry point (e.g., CLI command) through the codebase."""
        return self.client.run(
            f"""
            MATCH path = (entry:CodeEntity)-[:CALLS*1..8]->(deep:CodeEntity)
            WHERE (entry.simple_name = $name OR entry.qualified_name = $name)
            {self._repo_filter("entry", repo)}
            RETURN [n IN nodes(path) | n.qualified_name] AS call_chain,
                   length(path) AS depth
            ORDER BY depth
            """,
            **self._params(repo, name=entry_point),
        )

    def co_changed_files(self, module_name: str, repo: str | None = None) -> list[dict]:
        """Files that frequently change together with this one."""
        return self.client.run(
            f"""
            MATCH (a:CodeEntity)-[r:CO_CHANGED_WITH]-(b:CodeEntity)
            WHERE (a.simple_name = $name OR a.qualified_name = $name)
            {self._repo_filter("a", repo)}
            RETURN b.qualified_name AS co_changed_module,
                   b.file_path AS file,
                   r.times AS times_together,
                   r.confidence AS confidence
            ORDER BY r.times DESC
            """,
            **self._params(repo, name=module_name),
        )

    def file_owners(self, file_path: str, repo: str | None = None) -> list[dict]:
        """Who are the primary authors of this file?"""
        return self.client.run(
            f"""
            MATCH (e:CodeEntity)-[r:AUTHORED_BY]->(a:Author)
            WHERE e.file_path = $path
            {self._repo_filter("e", repo)}
            RETURN a.name AS author,
                   a.email AS email,
                   r.rank AS rank
            ORDER BY r.rank
            """,
            **self._params(repo, path=file_path),
        )

    def complex_functions(self, min_complexity: int = 5, repo: str | None = None) -> list[dict]:
        """Find the most complex functions in the codebase."""
        return self.client.run(
            f"""
            MATCH (e:CodeEntity)
            WHERE e.complexity >= $min_complexity
              AND e.kind IN ['Function', 'Method']
            {self._repo_filter("e", repo)}
            RETURN e.qualified_name AS function,
                   e.complexity AS complexity,
                   e.file_path AS file,
                   e.start_line AS line
            ORDER BY e.complexity DESC
            """,
            **self._params(repo, min_complexity=min_complexity),
        )

    def search(self, query: str) -> list[dict]:
        """Full-text search across entity names and docstrings."""
        return self.client.run(
            """
            CALL db.index.fulltext.queryNodes('entity_search', $search_term)
            YIELD node, score
            RETURN node.qualified_name AS name,
                   node.kind AS kind,
                   node.file_path AS file,
                   score
            ORDER BY score DESC
            LIMIT 20
            """,
            search_term=query,
        )

    def graph_stats(self) -> dict:
        """Summary statistics of the code graph."""
        counts = self.client.run(
            """
            MATCH (e:CodeEntity)
            RETURN e.kind AS kind, count(e) AS count
            ORDER BY count DESC
            """
        )
        rel_counts = self.client.run(
            """
            MATCH ()-[r]->()
            RETURN type(r) AS rel_type, count(r) AS count
            ORDER BY count DESC
            """
        )
        return {"entity_counts": counts, "relationship_counts": rel_counts}
