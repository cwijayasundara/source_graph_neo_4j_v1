from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AgentRunner(Protocol):
    """Runs one agent turn-loop and returns its structured JSON output."""

    async def run_structured(self, *, system: str, prompt: str, server: Any,
                             allowed_tools: list[str], model: str, max_turns: int,
                             schema: dict[str, Any]) -> dict[str, Any]:
        ...


class SdkAgentRunner:
    """Real runner: drives claude_agent_sdk.query() with the graph MCP server and a
    json_schema output_format, returning ResultMessage.structured_output.

    SDK verification (claude-agent-sdk==0.2.87):
    - ClaudeAgentOptions DOES support output_format (and setting_sources, tools, etc.)
    - ResultMessage DOES have structured_output (type: Any) and usage (type: dict | None)
    - Primary path taken: json_schema output_format -> ResultMessage.structured_output
      (no fallback text-parse needed because 0.2.87 natively supports structured output)

    Built-in tools are removed (tools=[]) so the agent can ONLY use graph tools, and
    no .claude settings are loaded (setting_sources=[]) for determinism."""

    def __init__(self) -> None:
        self.token_usage = {"input": 0, "output": 0}

    async def run_structured(self, *, system: str, prompt: str, server: Any,
                             allowed_tools: list[str], model: str, max_turns: int,
                             schema: dict[str, Any]) -> dict[str, Any]:
        try:
            from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

            options = ClaudeAgentOptions(
                system_prompt=system,
                mcp_servers={"graph": server} if server is not None else {},
                allowed_tools=allowed_tools,
                tools=[],                        # remove built-ins; graph tools only
                model=model,
                max_turns=max_turns,
                setting_sources=[],              # do not load .claude config
                output_format={"type": "json_schema", "schema": schema},
            )
            structured: dict[str, Any] = {}
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, ResultMessage):
                    structured = message.structured_output or {}
                    usage = message.usage or {}
                    # usage is dict[str, Any] | None in 0.2.87
                    self.token_usage["input"] += usage.get("input_tokens", 0) or 0
                    self.token_usage["output"] += usage.get("output_tokens", 0) or 0
            return structured
        except Exception:
            # Never raise on usage/parse failures — return empty dict
            return {}
