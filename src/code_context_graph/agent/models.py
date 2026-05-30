from __future__ import annotations

import os

# Single global model var (override per-role below). Must be a Claude model id.
GLOBAL_ENV = "CODE_GRAPH_LLM_MODEL"

_ROLE_ENV = {
    "brd": "BRD_AGENT_MODEL",
    "enrichment": "ENRICHMENT_MODEL",
    "ask": "ASK_MODEL",
    "advisor": "ADVISOR_MODEL",
}

# Hardcoded Claude fallbacks (tiers): cheap Haiku for high-volume roles, Sonnet for
# BRD synthesis/judge, Opus for the advisor (capable guidance, used sparingly).
_DEFAULTS = {
    "brd": "claude-sonnet-4-6",
    "enrichment": "claude-haiku-4-5-20251001",
    "ask": "claude-haiku-4-5-20251001",
    "advisor": "claude-opus-4-8",
}


def resolve_model(role: str) -> str:
    """Resolve the Claude model for a role.

    Precedence: per-role override env var -> global CODE_GRAPH_LLM_MODEL ->
    hardcoded Claude default for the role (Sonnet if role unknown).
    """
    role_env = _ROLE_ENV.get(role)
    if role_env and os.getenv(role_env):
        return os.environ[role_env]
    if os.getenv(GLOBAL_ENV):
        return os.environ[GLOBAL_ENV]
    return _DEFAULTS.get(role, "claude-sonnet-4-6")
