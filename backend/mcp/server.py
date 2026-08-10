"""MCP tool registration entry point."""

from backend.mcp.tool_registry import ToolRegistry


def init_mcp_tools() -> ToolRegistry:
    registry = ToolRegistry()

    from backend.mcp.tools import code_tools, column_tools, dba_tools, name_tools, orm_tools, qa_tools, survey_tools

    survey_tools.register_all(registry)
    column_tools.register_all(registry)
    name_tools.register_all(registry)
    code_tools.register_all(registry)
    orm_tools.register_all(registry)
    qa_tools.register_all(registry)
    dba_tools.register_all(registry)
    return registry
