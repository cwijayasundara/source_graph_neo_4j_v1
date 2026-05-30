"""BRD (Business Requirements Document) generator.

Public entrypoint: `generate_brd_graph_sync(repo_id, *, client=None, repo_path=None,
max_retries=None, model=None, max_turns=None, max_subsystems=None, storage=None)`.
"""
from code_context_graph.brd.pipeline import generate_brd_graph_sync
from code_context_graph.brd.schema import BRDResult, Rating, Strategy

__all__ = ["generate_brd_graph_sync", "BRDResult", "Rating", "Strategy"]
