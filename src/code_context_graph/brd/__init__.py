"""BRD (Business Requirements Document) generator.

Public entrypoint: `generate_brd(repo_id, *, max_retries=2, force_map_reduce=False)`.
"""
from code_context_graph.brd.pipeline import generate_brd
from code_context_graph.brd.schema import BRDResult, Rating, Strategy

__all__ = ["generate_brd", "BRDResult", "Rating", "Strategy"]
